"""OpenRouter 元数据采集 — Step 1

从 OpenRouter /api/v1/models 补全数据库里 34 个模型的元数据:
  - pricing_input / pricing_output (USD per 1M tokens)
  - context_window / max_output_tokens
  - supports_tools / supports_vision / supports_audio
  - homepage / release_date

匹配策略 (按优先级):
  1. 精确匹配: DB canonical_id == OpenRouter id
  2. Alias 匹配: DB 里的显示名别名 == OpenRouter name
  3. 模糊匹配: provider + 去版本后缀的 slug
  4. 前缀匹配: OpenRouter id 以 DB id 为前缀 (处理 :beta/:free 等后缀)

用法:
  python3 scripts/fetch_openrouter_meta.py --dry-run    # 只看匹配,不入库
  python3 scripts/fetch_openrouter_meta.py              # 入库
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table

from src.collector.discoverer import DiscoveredModel, OpenRouterDiscoverer
from src.storage.db_manager import DatabaseManager
from src.storage.models import Model, ModelAlias

console = Console()

# DB provider key → OpenRouter provider key 映射
# 项目宪法规定 GLM 用 zhipu, Kimi 用 moonshot, 但 OpenRouter 用 z-ai / moonshotai
PROVIDER_ALIAS_MAP = {
    "zhipu": "z-ai",
    "moonshot": "moonshotai",
}
# 反向映射 (OpenRouter -> DB)
PROVIDER_ALIAS_MAP_REV = {v: k for k, v in PROVIDER_ALIAS_MAP.items()}

# 特殊手动映射 (DB id → OpenRouter id)
# 用于命名差异较大、无法自动匹配但明确对应的模型
MANUAL_MAP = {
    "moonshot/k2-think-v2": "moonshotai/kimi-k2-thinking",  # think v2 → thinking
    "moonshot/kimi-k2-instruct": "moonshotai/kimi-k2",  # instruct → 基础版 (0711)
}


def normalize_slug(slug: str) -> str:
    """归一化 slug 用于模糊匹配: token 排序后拼接

    保留版本号,只去分隔符,token 排序处理命名顺序差异
    例:
      claude-4.5-haiku -> "4.5|claude|haiku"
      claude-haiku-4.5 -> "4.5|claude|haiku"  (同模型不同命名)
      claude-3-haiku   -> "3|claude|haiku"    (不同版本,不匹配)
    """
    import re
    s = slug.lower()
    # 去掉 :free :beta 等路由后缀
    s = s.split(":")[0]
    # 按分隔符切分
    tokens = [t for t in re.split(r"[\-_.]", s) if t]
    # 排序后用 | 拼接
    return "|".join(sorted(tokens))


def build_or_index(discoveries: List[DiscoveredModel]) -> Tuple[Dict[str, DiscoveredModel], Dict[str, DiscoveredModel], Dict[str, DiscoveredModel]]:
    """建立 OpenRouter 模型的三种索引

    返回: (精确 id 索引, 模糊 slug 索引, provider+slug 索引)
    非 :free 版本优先于 :free 版本(同 slug 时)
    """
    exact: Dict[str, DiscoveredModel] = {}
    fuzzy: Dict[str, DiscoveredModel] = {}
    by_provider_slug: Dict[str, DiscoveredModel] = {}

    def prefer_non_free(existing: DiscoveredModel, new: DiscoveredModel) -> DiscoveredModel:
        """非 free 优先"""
        if ":free" in existing.raw_id and ":free" not in new.raw_id:
            return new
        return existing

    for d in discoveries:
        # 精确 id
        if d.canonical_id in exact:
            exact[d.canonical_id] = prefer_non_free(exact[d.canonical_id], d)
        else:
            exact[d.canonical_id] = d
        if d.raw_id != d.canonical_id and d.raw_id not in exact:
            exact[d.raw_id] = d

        # 模糊 slug (非 free 优先)
        slug = d.canonical_id.split("/", 1)[-1] if "/" in d.canonical_id else d.canonical_id
        norm = normalize_slug(slug)
        if norm:
            if norm in fuzzy:
                fuzzy[norm] = prefer_non_free(fuzzy[norm], d)
            else:
                fuzzy[norm] = d
            key = f"{d.provider}/{norm}"
            if key in by_provider_slug:
                by_provider_slug[key] = prefer_non_free(by_provider_slug[key], d)
            else:
                by_provider_slug[key] = d

    return exact, fuzzy, by_provider_slug


def match_model(
    db_model: Model,
    aliases: List[str],
    exact: Dict[str, DiscoveredModel],
    fuzzy: Dict[str, DiscoveredModel],
    by_provider_slug: Dict[str, DiscoveredModel],
) -> Tuple[Optional[DiscoveredModel], str]:
    """匹配单个 DB 模型,返回 (匹配结果, 匹配方式)

    匹配策略 (按优先级):
      1. 精确匹配 canonical_id
      2. Provider 映射后精确匹配 (zhipu->z-ai, moonshot->moonshotai)
      3. Provider 映射 + 模糊 slug
      4. 前缀/后缀匹配 (处理 :beta/:free/-it 等)
    """
    cid = db_model.id

    # 0. 手动映射 (特殊命名差异)
    if cid in MANUAL_MAP:
        target = MANUAL_MAP[cid]
        if target in exact:
            return exact[target], "manual_map"

    # 1. 精确匹配 canonical_id
    if cid in exact:
        return exact[cid], "exact"

    # 2. Provider 映射后精确匹配
    if "/" in cid:
        provider, slug = cid.split("/", 1)
        or_provider = PROVIDER_ALIAS_MAP.get(provider, provider)
        mapped_id = f"{or_provider}/{slug}"
        if mapped_id in exact:
            return exact[mapped_id], "provider_mapped"

        # 2.1 反向后缀匹配: DB id + "-preview" (gemini-3.1-pro -> gemini-3.1-pro-preview)
        for suffix in ("-preview", "-preview-05-06"):
            candidate = f"{mapped_id}{suffix}"
            if candidate in exact:
                return exact[candidate], "reverse_suffix"

        # 3. Provider 映射 + 后缀变体 (gemma-4-31b -> gemma-4-31b-it), 非 free 优先
        candidates = []
        for or_id, d in exact.items():
            or_clean = or_id.lstrip("~")
            if or_clean.startswith(mapped_id):
                suffix = or_clean[len(mapped_id):]
                if suffix in ("-it", ":free", "-it:free", "-instruct", "-it:free"):
                    candidates.append((d, suffix))
        if candidates:
            # 非 free 优先
            non_free = [c for c in candidates if ":free" not in c[0].raw_id]
            chosen = non_free[0] if non_free else candidates[0]
            return chosen[0], "suffix_variant"

        # 4. Provider 映射 + 模糊 slug
        norm = normalize_slug(slug)
        if norm:
            key = f"{or_provider}/{norm}"
            if key in by_provider_slug:
                return by_provider_slug[key], "fuzzy_provider_mapped"

    # 5. 原始模糊匹配 (无 provider 映射)
    if "/" in cid:
        provider, slug = cid.split("/", 1)
        norm = normalize_slug(slug)
        if norm:
            key = f"{provider}/{norm}"
            if key in by_provider_slug:
                return by_provider_slug[key], "fuzzy_provider_slug"

    return None, "no_match"


def fetch_db_models(db: DatabaseManager) -> List[Tuple[Model, List[str]]]:
    """读取数据库所有模型 + 每个模型的别名列表"""
    models_with_aliases: List[Tuple[Model, List[str]]] = []
    with db.get_session() as session:
        models = session.query(Model).all()
        for m in models:
            alias_rows = session.query(ModelAlias).filter(
                ModelAlias.canonical_model_id == m.id
            ).all()
            aliases = [a.alias for a in alias_rows]
            models_with_aliases.append((m, aliases))
    return models_with_aliases


def update_model_meta(db: DatabaseManager, model_id: str, d: DiscoveredModel) -> None:
    """用 OpenRouter 数据更新 DB 模型元数据 (不覆盖已有非空值? 这里直接覆盖,因为 OpenRouter 是权威源)"""
    db.upsert_model({
        "id": model_id,
        "context_window": d.context_window,
        "max_output_tokens": d.max_output_tokens,
        "supports_tools": d.supports_tools,
        "supports_vision": d.supports_vision,
        "supports_audio": d.supports_audio,
        "pricing_input": d.pricing_input,
        "pricing_output": d.pricing_output,
        "homepage": d.homepage,
        "release_date": d.release_date,
        "status": "active",
    })


def main():
    parser = argparse.ArgumentParser(description="OpenRouter 元数据采集")
    parser.add_argument("--dry-run", action="store_true", help="只看匹配,不入库")
    parser.add_argument("--api-key", default=None, help="OpenRouter API key (可选,提高限速)")
    args = parser.parse_args()

    console.print("[blue]===== Step 1: OpenRouter 元数据采集 =====[/blue]")

    # 1. 调 OpenRouter API
    console.print("\n[blue]1. 调用 OpenRouter API...[/blue]")
    discoverer = OpenRouterDiscoverer(api_key=args.api_key)
    try:
        discoveries = discoverer.discover()
    except Exception as e:
        console.print(f"[red]✗ API 调用失败: {e}[/red]")
        sys.exit(1)

    # 2. 建立索引
    exact, fuzzy, by_provider_slug = build_or_index(discoveries)
    console.print(f"[green]✓ 索引建立: 精确 {len(exact)} / 模糊 {len(fuzzy)}[/green]")

    # 3. 读 DB 模型
    db = DatabaseManager()
    db_models = fetch_db_models(db)
    console.print(f"[blue]DB 模型数: {len(db_models)}[/blue]")

    # 4. 匹配
    console.print("\n[blue]2. 匹配 DB 模型 → OpenRouter...[/blue]")
    matched: List[Tuple[Model, DiscoveredModel, str]] = []
    unmatched: List[Model] = []

    for m, aliases in db_models:
        d, method = match_model(m, aliases, exact, fuzzy, by_provider_slug)
        if d:
            matched.append((m, d, method))
        else:
            unmatched.append(m)

    # 5. 输出匹配结果表
    table = Table(title="匹配结果", show_lines=False, expand=True, width=200)
    table.add_column("DB Model ID", style="cyan", no_wrap=True, overflow="fold")
    table.add_column("OpenRouter ID", style="green", no_wrap=True, overflow="fold")
    table.add_column("方式", style="yellow")
    table.add_column("价格(in/out)", style="magenta")
    table.add_column("上下文", style="blue")

    for m, d, method in matched:
        price = f"{d.pricing_input}/{d.pricing_output}" if d.pricing_input else "-"
        ctx = str(d.context_window) if d.context_window else "-"
        table.add_row(m.id, d.canonical_id, method, price, ctx)

    console.print(table)

    if unmatched:
        console.print(f"\n[red]⚠ 未匹配 ({len(unmatched)}):[/red]")
        for m in unmatched:
            console.print(f"  [red]- {m.id}[/red]")

    # 6. 统计
    console.print(f"\n[bold]匹配: {len(matched)}/{len(db_models)}[/bold]")

    # 7. 入库 (非 dry-run)
    if args.dry_run:
        console.print("\n[yellow]--dry-run 模式, 不入库[/yellow]")
        return

    if not matched:
        console.print("[red]无匹配, 跳过入库[/red]")
        return

    console.print(f"\n[blue]3. 更新 {len(matched)} 个模型的元数据...[/blue]")
    updated = 0
    for m, d, method in matched:
        try:
            update_model_meta(db, m.id, d)
            updated += 1
        except Exception as e:
            console.print(f"[red]✗ 更新 {m.id} 失败: {e}[/red]")

    console.print(f"[green]✓ 更新完成: {updated}/{len(matched)}[/green]")

    # 8. 未匹配的写入待审核标记
    if unmatched:
        console.print(f"\n[yellow]未匹配 {len(unmatched)} 个, 建议:[/yellow]")
        console.print("[yellow]  1. 检查 OpenRouter 是否有对应模型 (可能模型名差异较大)[/yellow]")
        console.print("[yellow]  2. 部分国内厂商模型可能未上架 OpenRouter[/yellow]")
        console.print("[yellow]  3. 需要从厂商官网补全元数据[/yellow]")


if __name__ == "__main__":
    main()
