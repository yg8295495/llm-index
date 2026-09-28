#!/usr/bin/env python3
"""LMArena Text Elo 数据入库脚本

从 data/raw/lmarena_text_elo_2026-06-17.txt 提取数据,
映射 LMArena 模型名到 DB model_id + reasoning_level,
写入 benchmark_evals 表 (benchmark="lmarena_text", score_type="elo")。

映射策略 (自动化优先):
  1. 别名表精确匹配
  2. 规则匹配 (厂商前缀 + 名称归一化 + 推理级别推断)
  3. 模糊匹配 (display_name 相似度)
  4. 未匹配标 needs_manual_review

Usage:
    python3 scripts/ingest_lmarena.py [--dry-run]
"""

import argparse
import sqlite3
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DB_PATH = Path(__file__).parent.parent / "data" / "llm_index.db"
LMARENA_PATH = (
    Path(__file__).parent.parent / "data" / "raw" / "lmarena_text_elo_2026-06-17.txt"
)

# LMArena 名称 → (model_id, reasoning_level) 的显式映射
# 用于无法自动推断的情况
EXPLICIT_MAP: Dict[str, Tuple[str, str]] = {
    # Claude — LMArena 用 opus-4-6/4-7/4-8 格式, DB 用 opus-4.6/4.7/4.8
    "claude-fable-5": ("anthropic/claude-fable-5", "adaptive-max"),
    "claude-opus-4-6-thinking": ("anthropic/claude-opus-4.6", "adaptive-max"),
    "claude-opus-4-7-thinking": ("anthropic/claude-opus-4.7", "adaptive-max"),
    "claude-opus-4-8-thinking": ("anthropic/claude-opus-4.8", "adaptive-max"),
    "claude-opus-4-6": ("anthropic/claude-opus-4.6", "non-reasoning-high"),
    "claude-opus-4-7": ("anthropic/claude-opus-4.7", "non-reasoning-high"),
    "claude-opus-4-8": ("anthropic/claude-opus-4.8", "adaptive-max"),
    "claude-opus-4-5-20251101-thinking-32k": ("anthropic/claude-opus-4.5", "reasoning"),
    "claude-opus-4-5-20251101": ("anthropic/claude-opus-4.5", "non-reasoning"),
    "claude-sonnet-4-6": ("anthropic/claude-sonnet-4.6", "adaptive-max"),
    "claude-sonnet-4-5-20250929-thinking-32k": ("anthropic/claude-4.5-sonnet", "reasoning"),
    "claude-sonnet-4-5-20250929": ("anthropic/claude-4.5-sonnet", "non-reasoning"),
    "claude-haiku-4-5-20251001": ("anthropic/claude-4.5-haiku", "non-reasoning"),
    # GPT — LMArena "high" 对应 DB "xhigh"
    "gpt-5.5-high": ("openai/gpt-5.5", "xhigh"),
    "gpt-5.4-high": ("openai/gpt-5.4", "xhigh"),
    "gpt-5.5": ("openai/gpt-5.5", ""),
    "gpt-5.5-instant": ("openai/gpt-5.5-instant", ""),
    "gpt-5.4": ("openai/gpt-5.4", "non-reasoning"),
    "gpt-5.4-mini-high": ("openai/gpt-5.4-mini", "xhigh"),
    "gpt-5.3-chat-latest": ("openai/gpt-5.3", ""),  # 需注册
    "gpt-5.2-chat-latest-20260210": ("openai/gpt-5.2", "non-reasoning"),
    "gpt-5.2-high": ("openai/gpt-5.2", "xhigh"),
    "gpt-5.2": ("openai/gpt-5.2", "non-reasoning"),
    "gpt-5.1": ("openai/gpt-5.1", ""),
    "gpt-5-high": ("openai/gpt-5", "high"),
    "o3-2025-04-16": ("openai/o3", ""),  # 需注册
    "o4-mini-2025-04-16": ("openai/o4-mini", ""),  # 需注册
    # Gemini
    "gemini-3.1-pro-preview": ("google/gemini-3.1-pro-preview", ""),
    "gemini-3-pro": ("google/gemini-3-pro", "high"),
    "gemini-3.5-flash": ("google/gemini-3.5-flash", "high"),
    "gemini-3-flash": ("google/gemini-3-flash", "non-reasoning"),
    "gemini-3-flash (thinking-minimal)": ("google/gemini-3-flash", "reasoning"),
    "gemini-3.1-flash-lite-preview": ("google/gemini-3.1-flash-lite-preview", ""),
    "gemini-2.5-pro": ("google/gemini-2.5-pro", ""),
    "gemini-2.5-flash": ("google/gemini-2.5-flash", "non-reasoning"),
    # DeepSeek
    "deepseek-v4-pro-thinking": ("deepseek/deepseek-v4-pro", "reasoning"),
    "deepseek-v4-pro": ("deepseek/deepseek-v4-pro", "non-reasoning"),
    "deepseek-v4-flash-thinking": ("deepseek/deepseek-v4-flash", "reasoning"),
    "deepseek-v4-flash": ("deepseek/deepseek-v4-flash", "non-reasoning"),
    "deepseek-v3.2": ("deepseek/deepseek-v3.2", "non-reasoning"),
    "deepseek-v3.2-exp-thinking": ("deepseek/deepseek-v3.2-exp", "reasoning"),
    "deepseek-v3.2-exp": ("deepseek/deepseek-v3.2-exp", "non-reasoning"),
    "deepseek-v3.2-thinking": ("deepseek/deepseek-v3.2", "reasoning"),
    # GLM
    "glm-5.1": ("zhipu/glm-5.1", "non-reasoning"),
    "glm-5.2 (max)": ("zhipu/glm-5.2", "max"),
    "glm-5": ("zhipu/glm-5", "non-reasoning"),
    "glm-4.7": ("zhipu/glm-4.7", "non-reasoning"),
    "glm-4.6": ("zhipu/glm-4.6", "non-reasoning"),
    # Kimi
    "kimi-k2.6": ("moonshot/kimi-k2.6", ""),
    "kimi-k2.5-thinking": ("moonshot/kimi-k2.5", "reasoning"),
    "kimi-k2.5-instant": ("moonshot/kimi-k2.5-instant", ""),  # 需注册
    "kimi-k2-thinking-turbo": ("moonshot/kimi-k2", "reasoning"),
    "kimi-k2-0905-preview": ("moonshot/kimi-k2-0905", ""),
    "kimi-k2-0711-preview": ("moonshot/kimi-k2", ""),
    # Qwen
    "qwen3.7-max-preview": ("qwen/qwen3.7-max", ""),
    "qwen3.5-max-preview": ("qwen/qwen3.5-max-preview", ""),  # 需注册
    "qwen3.6-max-preview": ("qwen/qwen3.6-max", ""),
    "qwen3.6-plus": ("qwen/qwen3.6-plus", ""),
    "qwen3.5-397b-a17b": ("qwen/qwen3.5-397b-a17b", "non-reasoning"),
    "qwen3-235b-a22b-instruct-2507": ("qwen/qwen3-235b-a22b-instruct", ""),
    "qwen3-235b-a22b": ("qwen/qwen3-235b-a22b-instruct", "non-reasoning"),
    # MiMo
    "mimo-v2.5-pro": ("xiaomi/mimo-v2.5-pro", "adaptive-max"),
    "mimo-v2-pro": ("xiaomi/mimo-v2-pro", ""),
    "mimo-v2.5": ("xiaomi/mimo-v2.5", ""),
    "mimo-v2-omni": ("xiaomi/mimo-v2-omni", ""),
    # MiniMax
    "minimax-m3": ("minimax/minimax-m3", ""),
    "minimax-m2.7": ("minimax/minimax-m2.7", ""),
    # Gemma (Google 开源, 需注册)
    "gemma-4-31b": ("google/gemma-4-31b", ""),  # 需注册
    "gemma-4-26b-a4b": ("google/gemma-4-26b-a4b", ""),  # 需注册
    # GPT-OSS (OpenAI 开源, 需注册)
    "gpt-oss-120b": ("openai/gpt-oss-120b", ""),  # 需注册
    "gpt-oss-20b": ("openai/gpt-oss-20b", ""),  # 需注册
}


def parse_lmarena_file(path: Path) -> List[Dict]:
    """解析 LMArena Elo 文件"""
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) != 4:
                continue
            rank, model_name, elo, votes = parts
            entries.append({
                "rank": int(rank),
                "model_name": model_name.strip(),
                "elo": float(elo),
                "votes": int(votes),
            })
    return entries


def load_db_models(conn: sqlite3.Connection) -> Dict[Tuple[str, str], int]:
    """加载 DB 中所有 (model_id, reasoning_level) → model_pk 映射"""
    cursor = conn.execute(
        "SELECT id, model_id, reasoning_level FROM models"
    )
    result = {}
    for pk, model_id, reasoning_level in cursor:
        key = (model_id, reasoning_level or "")
        result[key] = pk
    return result


def load_aliases(conn: sqlite3.Connection) -> Dict[str, Tuple[str, str]]:
    """加载别名表: alias → (model_id, reasoning_level)"""
    cursor = conn.execute(
        "SELECT alias, canonical_model_id FROM model_alias"
    )
    # 别名只指向 model_id, reasoning_level 默认为空
    return {row[0]: (row[1], "") for row in cursor}


def match_entry(
    entry: Dict,
    db_models: Dict[Tuple[str, str], int],
    aliases: Dict[str, Tuple[str, str]],
) -> Optional[Tuple[int, str]]:
    """匹配单个 LMArena 条目到 DB model_pk

    Returns:
        (model_pk, match_method) 或 None
    """
    name = entry["model_name"]

    # 1. 显式映射
    if name in EXPLICIT_MAP:
        model_id, reasoning_level = EXPLICIT_MAP[name]
        key = (model_id, reasoning_level)
        if key in db_models:
            return db_models[key], "explicit_map"
        # 尝试 reasoning_level 为空
        key_fallback = (model_id, "")
        if key_fallback in db_models:
            return db_models[key_fallback], "explicit_map_fallback"

    # 2. 别名表匹配
    if name in aliases:
        model_id, reasoning_level = aliases[name]
        key = (model_id, reasoning_level)
        if key in db_models:
            return db_models[key], "alias"

    # 3. 模糊匹配: 归一化名称后搜索 model_id
    normalized = name.lower().replace(" ", "-").replace("(", "").replace(")", "")
    for (model_id, rl), pk in db_models.items():
        # model_id 的 slug 部分
        slug = model_id.split("/")[-1].lower()
        if slug == normalized or slug.replace("-", "") == normalized.replace("-", ""):
            return pk, "slug_match"

    return None


def register_missing_models(conn: sqlite3.Connection, entries: List[Dict]) -> int:
    """注册 DB 中不存在的九家厂商模型 (仅 model_id + provider + display_name)

    Returns:
        新注册的模型数量
    """
    db_ids = set()
    cursor = conn.execute("SELECT DISTINCT model_id FROM models")
    for row in cursor:
        db_ids.add(row[0])

    new_models = {}
    for name, (model_id, rl) in EXPLICIT_MAP.items():
        if model_id not in db_ids:
            provider = model_id.split("/")[0]
            display_name = name.replace("-", " ").title()
            new_models[model_id] = {
                "model_id": model_id,
                "provider": provider,
                "display_name": display_name,
                "reasoning_level": rl,
                "status": "active",
                "open_source": "proprietary",
            }

    for model_id in new_models:
        if "gemma" in model_id or "gpt-oss" in model_id:
            new_models[model_id]["open_source"] = "open"

    if not new_models:
        return 0

    print(f"\n需注册 {len(new_models)} 个新模型:")
    for mid, info in sorted(new_models.items()):
        print(f"  {mid} ({info['provider']}, {info['open_source']})")

    count = 0
    for mid, info in new_models.items():
        try:
            conn.execute(
                """INSERT INTO models (model_id, reasoning_level, display_name, provider, status, open_source)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (mid, info["reasoning_level"], info["display_name"],
                 info["provider"], info["status"], info["open_source"]),
            )
            count += 1
        except Exception as e:
            print(f"  跳过 {mid}: {e}")

    conn.commit()
    print(f"✓ 注册 {count} 个新模型")
    return count


def ingest(dry_run: bool = False) -> None:
    """执行入库"""
    entries = parse_lmarena_file(LMARENA_PATH)
    print(f"解析到 {len(entries)} 条 LMArena 记录")

    conn = sqlite3.connect(str(DB_PATH))
    db_models = load_db_models(conn)
    aliases = load_aliases(conn)
    print(f"DB 中有 {len(db_models)} 个模型记录, {len(aliases)} 个别名")

    # 先注册缺失模型
    if not dry_run:
        register_missing_models(conn, entries)
        # 重新加载
        db_models = load_db_models(conn)

    matched = []
    unmatched = []

    for entry in entries:
        result = match_entry(entry, db_models, aliases)
        if result:
            pk, method = result
            matched.append((entry, pk, method))
        else:
            unmatched.append(entry)

    print(f"\n匹配结果: {len(matched)} 成功, {len(unmatched)} 未匹配")

    if unmatched:
        print("\n--- 未匹配条目 ---")
        for e in unmatched:
            print(f"  #{e['rank']} {e['model_name']} (Elo={e['elo']}, votes={e['votes']})")

    # 按匹配方式统计
    method_counts = {}
    for _, _, method in matched:
        method_counts[method] = method_counts.get(method, 0) + 1
    print(f"\n匹配方式统计: {method_counts}")

    # 写入 benchmark_evals
    if not dry_run:
        observed_at = date(2026, 6, 17)
        inserted = 0
        for entry, pk, method in matched:
            # 检查是否已存在
            existing = conn.execute(
                "SELECT id FROM benchmark_evals WHERE model_pk=? AND benchmark=?",
                (pk, "lmarena_text"),
            ).fetchone()
            if existing:
                # 更新
                conn.execute(
                    """UPDATE benchmark_evals
                       SET score_raw=?, score_type=?, source=?, confidence=?,
                           breakdown=?, observed_at=?
                       WHERE model_pk=? AND benchmark=?""",
                    (
                        entry["elo"],
                        "elo",
                        "lmarena",
                        0.95,
                        f'{{"rank": {entry["rank"]}, "votes": {entry["votes"]}, "match_method": "{method}"}}',
                        observed_at,
                        pk,
                        "lmarena_text",
                    ),
                )
            else:
                # 插入
                conn.execute(
                    """INSERT INTO benchmark_evals
                       (model_pk, benchmark, score_raw, score_type, source,
                        confidence, breakdown, observed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        pk,
                        "lmarena_text",
                        entry["elo"],
                        "elo",
                        "lmarena",
                        0.95,
                        f'{{"rank": {entry["rank"]}, "votes": {entry["votes"]}, "match_method": "{method}"}}',
                        observed_at,
                    ),
                )
            inserted += 1

        conn.commit()
        print(f"\n✓ 写入 {inserted} 条 lmarena_text 评测记录到 benchmark_evals")
    else:
        print(f"\n[dry-run] 将写入 {len(matched)} 条记录")

    # 更新 benchmarks.yaml 中 lmarena 的 coverage
    if not dry_run and matched:
        print(f"提示: 记得更新 config/benchmarks.yaml 中 lmarena 的 coverage: {len(matched)}")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LMArena Elo 数据入库")
    parser.add_argument("--dry-run", action="store_true", help="只输出匹配结果，不写入数据库")
    args = parser.parse_args()
    ingest(dry_run=args.dry_run)
