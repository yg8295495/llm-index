"""LMArena Elo 入库 — Step 2

从 data/raw/lmarena_text_elo_2026-06-17.txt 读取 Text Overall Elo 分数,
匹配数据库里的 34 个模型, 入库为 observation (benchmark=arena_elo, source=lmarena)。

匹配策略 (按优先级):
  1. 精确匹配 slug == lmarena name
  2. 基础版本优先 (不带 high/thinking 后缀)
  3. 日期后缀匹配 (claude-opus-4-5-20251101 == claude-opus-4.5)
  4. -preview 后缀匹配 (gemini-3.1-pro == gemini-3.1-pro-preview)
  5. token 排序匹配 (claude-4.5-haiku == claude-haiku-4-5)

用法:
  python3 scripts/load_lmarena_elo.py --dry-run    # 只看匹配
  python3 scripts/load_lmarena_elo.py              # 入库
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table

from src.storage.db_manager import DatabaseManager
from src.storage.models import Model

console = Console()

DATA_FILE = PROJECT_ROOT / "data/raw/lmarena_text_elo_2026-06-17.txt"


def load_lmarena_data() -> List[dict]:
    """读取 LMArena 原始数据"""
    models = []
    with open(DATA_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) < 3:
                continue
            models.append({
                "rank": int(parts[0]),
                "name": parts[1].strip(),
                "elo": int(parts[2]),
                "votes": int(parts[3].replace(",", "")) if len(parts) > 3 and parts[3].strip() else 0,
            })
    return models


def normalize_name(name: str) -> str:
    """归一化模型名: 小写, 去分隔符, 去日期, token 排序"""
    s = name.lower()
    s = re.sub(r"\(.*?\)", "", s)  # 去括号内容 (max) (thinking) 等
    s = re.sub(r"\d{8}", "", s)  # 去日期 20251001
    s = re.sub(r"\d{6}", "", s)  # 去日期 250929
    s = s.strip()
    tokens = [t for t in re.split(r"[\-_.\s]", s) if t]
    return "|".join(sorted(tokens))


# 已知的推理深度/测试配置后缀 (匹配时可作为变体忽略)
REASONING_SUFFIXES = ["-high", "-thinking", "-instant", "-turbo", "-chat-latest",
                      "-thinking-32k", "-thinking-16k", "-thinking-minimal"]
# 已知的版本后缀 (匹配时可作为变体忽略)
VERSION_SUFFIXES = ["-preview", "-preview-2507", "-instruct-2507", "-instruct"]


def is_base_version(name: str) -> bool:
    """判断是否基础版本 (不带 high/thinking/max 等推理深度后缀)"""
    lower = name.lower()
    for kw in REASONING_SUFFIXES:
        if kw in lower:
            return False
    if "(max)" in lower or "(high)" in lower or "(thinking)" in lower:
        return False
    return True


# 手动映射 (DB slug → LMArena name)
# 用于命名差异较大、无法自动匹配但明确对应的模型
MANUAL_MAP = {
    "k2-think-v2": "kimi-k2-thinking-turbo",  # think v2 → thinking turbo
    "kimi-k2-instruct": "kimi-k2-0711-preview",  # instruct → 基础版 0711
}


def match_model(db_model: Model, lmarena_models: List[dict]) -> Tuple[Optional[dict], str]:
    """匹配单个 DB 模型到 LMArena 模型"""
    cid = db_model.id
    slug = cid.split("/", 1)[-1] if "/" in cid else cid
    slug_lower = slug.lower()

    # 0. 手动映射
    if slug_lower in MANUAL_MAP:
        target = MANUAL_MAP[slug_lower]
        for m in lmarena_models:
            if m["name"].lower() == target:
                return m, "manual_map"

    # 1. 精确匹配 (基础版本优先)
    exact_matches = [m for m in lmarena_models if m["name"].lower() == slug_lower]
    if exact_matches:
        base = [m for m in exact_matches if is_base_version(m["name"])]
        chosen = base[0] if base else exact_matches[0]
        return chosen, "exact"

    # 2. 推理深度后缀匹配 (gpt-5.4-mini == gpt-5.4-mini-high)
    #    DB slug + 推理深度后缀 == LMArena name
    for suffix in REASONING_SUFFIXES:
        candidate = f"{slug_lower}{suffix}"
        matches = [m for m in lmarena_models if m["name"].lower() == candidate]
        if matches:
            return matches[0], "reasoning_suffix"

    # 3. 日期后缀匹配 (claude-opus-4.5 == claude-opus-4-5-20251101, o3 == o3-2025-04-16)
    slug_normalized = slug_lower.replace(".", "-")
    for m in lmarena_models:
        name = m["name"].lower()
        # 去掉各种日期格式: 20251101 / 250929 / 2025-04-16 / 05-06
        name_clean = re.sub(r"-\d{8}$", "", name)
        name_clean = re.sub(r"-\d{6}$", "", name_clean)
        name_clean = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", name_clean)
        name_clean = re.sub(r"-\d{2}-\d{2}$", "", name_clean)
        if name_clean == slug_normalized:
            return m, "date_suffix"

    # 4. -preview 后缀匹配 (gemini-3.1-pro == gemini-3.1-pro-preview)
    for m in lmarena_models:
        name = m["name"].lower()
        if name == f"{slug_lower}-preview":
            return m, "preview_suffix"
        if slug_lower.endswith("-preview") and name == slug_lower.replace("-preview", ""):
            return m, "preview_strip"

    # 5. token 排序匹配 (claude-4.5-haiku == claude-haiku-4-5)
    slug_norm = normalize_name(slug)
    for m in lmarena_models:
        name_norm = normalize_name(m["name"])
        if name_norm == slug_norm:
            return m, "token_sorted"

    # 6. 严格前缀匹配 (只允许 instruct/日期等已知后缀)
    for m in lmarena_models:
        name = m["name"].lower()
        if name.startswith(slug_lower + "-"):
            remainder = name[len(slug_lower):]
            if remainder in VERSION_SUFFIXES or remainder in ["-instruct-2507", "-2507"]:
                return m, "version_prefix"

    return None, "no_match"


def main():
    parser = argparse.ArgumentParser(description="LMArena Elo 入库")
    parser.add_argument("--dry-run", action="store_true", help="只看匹配,不入库")
    args = parser.parse_args()

    console.print("[blue]===== Step 2: LMArena Elo 入库 =====[/blue]")

    # 1. 读取 LMArena 数据
    lmarena_models = load_lmarena_data()
    console.print(f"[blue]LMArena 模型数: {len(lmarena_models)}[/blue]")

    # 2. 读 DB 模型
    db = DatabaseManager()
    with db.get_session() as session:
        db_models = session.query(Model).all()
    console.print(f"[blue]DB 模型数: {len(db_models)}[/blue]")

    # 3. 匹配
    console.print("\n[blue]匹配 DB 模型 → LMArena...[/blue]")
    matched: List[Tuple[Model, dict, str]] = []
    unmatched: List[Model] = []

    for m in db_models:
        result, method = match_model(m, lmarena_models)
        if result:
            matched.append((m, result, method))
        else:
            unmatched.append(m)

    # 4. 输出匹配结果
    table = Table(title="LMArena Elo 匹配结果", show_lines=False, expand=True, width=180)
    table.add_column("DB Model ID", style="cyan", no_wrap=True, overflow="fold")
    table.add_column("LMArena Name", style="green", no_wrap=True, overflow="fold")
    table.add_column("方式", style="yellow")
    table.add_column("Rank", style="blue")
    table.add_column("Elo", style="magenta")
    table.add_column("Votes", style="white")

    for m, lm, method in matched:
        table.add_row(m.id, lm["name"], method, str(lm["rank"]), str(lm["elo"]), str(lm["votes"]))

    console.print(table)

    if unmatched:
        console.print(f"\n[red]⚠ 未匹配 ({len(unmatched)}):[/red]")
        for m in unmatched:
            console.print(f"  [red]- {m.id}[/red]")

    console.print(f"\n[bold]匹配: {len(matched)}/{len(db_models)}[/bold]")

    if args.dry_run:
        console.print("\n[yellow]--dry-run 模式, 不入库[/yellow]")
        return

    # 5. 入库
    console.print(f"\n[blue]入库 {len(matched)} 个 Elo observation...[/blue]")
    observations = []
    for m, lm, method in matched:
        observations.append({
            "model_id": m.id,
            "observation_type": "benchmark",
            "benchmark": "arena_elo",
            "score": float(lm["elo"]),
            "score_raw": float(lm["elo"]),
            "source": "lmarena",
            "confidence": 0.95,
            "freshness": "realtime",
            "observed_at": date(2026, 6, 17),
            "extra": {
                "rank": lm["rank"],
                "votes": lm["votes"],
                "category": "text_overall",
                "match_method": method,
                "source_url": "https://lmarena.ai/leaderboard",
            },
        })
    try:
        count = db.save_observations(observations)
        console.print(f"[green]✓ 入库完成: {count}[/green]")
    except Exception as e:
        console.print(f"[red]✗ 入库失败: {e}[/red]")


if __name__ == "__main__":
    main()
