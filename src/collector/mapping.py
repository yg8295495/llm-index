"""AA 记录 → 本项目 schema 的映射层 (纯函数, 可单测)

单一权威:
    config/vendors.yaml      — creator.slug → 厂商命名空间 + 范围层级
    config/benchmarks.yaml   — AA 字段名 (aa_key) → 规范 benchmark key + 量纲 + 方向
    AA 页面注册表 models[]    — 每个模型的 creator / release(基座) / effort(推理档位)
                                / releaseDate / deprecated, 全部 653 条 100% 覆盖

为什么不再用 slug 正则 (见 docs/changelog.md #4 #10):
    旧 collect_aa_v2.py 用 120 条 `^claude-` 之类的前缀规则猜厂商和档位,
    猜不到就写 provider='unknown', 2026-08-09 那次因此造出 122 个 unknown 模型,
    九家封闭范围随之失效。更危险的是 `^claude-fable-5` 会把新模型
    claude-fable-5-1 解析成 claude-fable-5, 与 6 月老模型撞成同一条记录。
    AA 注册表现在直接给出 creator.slug / release.slug / effort.slug, 无需猜测。

model_id 命名: `{namespace}/{dotted(基座 release.slug)}`, reasoning_level = effort.slug。
对库里已存在但只是写法不同的历史 ID (如 qwen/qwen3-8-max), 产出 rename 建议,
由存储层写入 model_id_renames 审计表并补 model_alias, 不改写任何评测历史。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

import yaml

from src.paths import config_path

# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------


def load_vendors() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(config_path("vendors.yaml").read_text(encoding="utf-8"))
    return data["vendors"]


def load_benchmarks() -> dict[str, Any]:
    return yaml.safe_load(config_path("benchmarks.yaml").read_text(encoding="utf-8"))


def benchmark_index(bm: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """aa_key -> 规范定义。派生型数据源 (无 aa_key) 不在此表, 由导出层计算。"""
    out: dict[str, dict[str, Any]] = {}
    for dim_key, dim in (bm.get("dimensions") or {}).items():
        if dim_key == "tags":
            continue
        for canonical, src in (dim.get("sources") or {}).items():
            aa_key = src.get("aa_key")
            if not aa_key:
                continue
            out[aa_key] = {
                "canonical": canonical,
                "dimension": dim_key,
                "scale": src.get("scale", "ratio"),
                "direction": src.get("direction", "higher"),
                "confidence": src.get("confidence", 0.8),
                "breakdown_key": src.get("breakdown_key"),
                "status": src.get("status", "production"),
            }
    return out


# ---------------------------------------------------------------------------
# 命名规范化
# ---------------------------------------------------------------------------

_VERSION_PAIR = re.compile(r"(\d+)-(\d+)")


def dotted(base_slug: str) -> str:
    """把 AA slug 的版本号还原成项目命名习惯: glm-5-3 -> glm-5.3。

    只处理第一处 `数字-数字`, 因此 qwen3-8-max-0902 -> qwen3.8-max-0902,
    而 k2-horizon-375b-a23b (字母隔断) 与 gpt-oss-120b 保持原样。
    """
    m = _VERSION_PAIR.search(base_slug)
    if not m:
        return base_slug
    return base_slug[: m.start()] + f"{m.group(1)}.{m.group(2)}" + base_slug[m.end() :]


# 仅供离线核对历史 ID 用: AA 偶发把档位写进名字括号里
_EFFORT_IN_NAME = re.compile(r"\((?:[^)]*?)\b(xhigh|high|medium|low|minimal|ultra|max)\s+effort", re.I)


def effort_from_name(name: str) -> str:
    m = _EFFORT_IN_NAME.search(name or "")
    return m.group(1).lower() if m else ""


# ---------------------------------------------------------------------------
# 结果结构
# ---------------------------------------------------------------------------


@dataclass
class ModelRow:
    model_id: str
    reasoning_level: str
    aa_slug: str
    aa_base_slug: str
    display_name: str
    provider: str
    tier: str
    family: str | None = None
    release_date: str | None = None
    deprecated: int = 0
    context_window: int | None = None
    context_window_fmt: str | None = None
    supports_vision: int | None = None
    supports_audio: int | None = None
    is_reasoning: int | None = None
    open_source: str | None = None
    size_class: str | None = None
    parameters: float | None = None
    active_params: float | None = None
    pricing_input: float | None = None
    pricing_output: float | None = None
    pricing_cache_input: float | None = None
    openness_index: float | None = None
    answer_speed: float | None = None
    time_per_task_s: float | None = None
    needs_manual_review: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class EvalRow:
    benchmark: str
    score_raw: float
    score_type: str
    dimension: str
    direction: str
    confidence: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    run_cost_usd: float | None = None
    breakdown: dict[str, Any] | None = None
    source: str = "artificial_analysis"


@dataclass
class MappedModel:
    row: ModelRow
    evals: list[EvalRow]
    existing_pk: int | None = None      # 命中库内既有行: 原地更新, 不新建
    rename_from: str | None = None      # 库内旧 model_id -> 规范 model_id
    provider_fixed_from: str | None = None


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------


def _num(value: Any) -> float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _pick(record: dict[str, Any], *keys: str, nested: tuple[str, str] | None = None) -> Any:
    """按候选键名顺序取第一个非空值。

    为什么需要 (changelog #37): AA 的两个 payload 对同一个属性用了不同键名 ——
    榜单页 (omniscience SSR) 完全没有 contextWindow*, 单模型详情页用
    `contextWindowTokens`; activeParams 在榜单页叫 `activeParams`, 详情页叫
    `inferenceParametersActiveBillions`; ifbench/itbenchSre 也存在大小写分叉
    (`ifbench` vs `itBenchSre` / `itbenchSre`)。旧实现只写死一个键名, 于是
    2026-09-20 批次里**所有带分行的 context_window 都是 NULL** —— 页面明明有值。
    """
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    if nested:
        holder = record.get(nested[0])
        if isinstance(holder, dict):
            value = holder.get(nested[1])
            if value is not None and value != "":
                return value
    return None


def _bool_to_int(raw: Any) -> int | None:
    return None if raw is None else int(bool(raw))


def _openness(raw: Any) -> str | None:
    if raw is True:
        return "open"
    if raw is False:
        return "proprietary"
    return raw if isinstance(raw, str) and raw else None


def model_metadata(record: dict[str, Any]) -> dict[str, Any]:
    """从 AA payload 取"非分数"元数据, 返回 models 表列名 -> 值。

    榜单页与详情页各调一次: 榜单页缺的字段 (contextWindow*) 由详情页补。
    补采脚本 scripts/enrich_metadata.py 与本模块共用这一个入口, 免得两处键名
    各写一半再次跑偏 (changelog #37)。
    """
    return {
        "context_window": _num(_pick(record, "contextWindowTokens", "contextWindow")),
        "context_window_fmt": record.get("contextWindowFormatted"),
        "supports_vision": _bool_to_int(record.get("inputModalityImage")),
        "supports_audio": _bool_to_int(record.get("inputModalitySpeech")),
        "open_source": _openness(record.get("isOpenWeights")),
        "size_class": record.get("sizeClass"),
        "parameters": _num(record.get("parameters")),
        "active_params": _num(_pick(record, "activeParams",
                                    "inferenceParametersActiveBillions")),
        "pricing_input": _num(record.get("price1mInputTokens")),
        "pricing_output": _num(record.get("price1mOutputTokens")),
        "pricing_cache_input": _num(record.get("cacheHitPrice")),
        "openness_index": _num(_pick(record, "opennessIndex",
                                     nested=("openness", "opennessIndex"))),
        "answer_speed": _num(_pick(record, "medianCanonicalAnswerOutputSpeed",
                                   nested=("timescaleData", "medianOutputSpeed"))),
        "time_per_task_s": _num(_pick(record, "intelligenceIndexTimePerTask")),
    }


def build_registry_index(registry: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """aa_slug -> 注册表条目 (含 creator / release / effort)"""
    return {r["slug"]: r for r in registry if isinstance(r, dict) and r.get("slug")}


_LOGO_RE = re.compile(r"/img/logos/(?P<slug>[\w\-]+?)(?:_small)?\.svg$")


def creator_slug(creator: dict[str, Any] | None, by_id: dict[str, str] | None = None) -> str:
    """解析 AA creator 的厂商标识。

    AA 在带分记录里给全 (id/slug/name/color/logo), 在注册表里只给 (id/name/logo),
    所以按三级回退: 自带 slug -> logo 文件名 -> creator.id 反查表。
    例: /img/logos/zai_small.svg -> "zai"; /img/logos/thinking_machines.svg -> "thinking-machines"
    """
    if not isinstance(creator, dict):
        return ""
    if creator.get("slug"):
        return str(creator["slug"])
    m = _LOGO_RE.search(creator.get("logo") or "")
    if m:
        return m.group("slug").replace("_", "-")
    cid = creator.get("id")
    if cid and by_id:
        return by_id.get(cid, "")
    return ""


def build_creator_id_index(*sources: Iterable[dict[str, Any]]) -> dict[str, str]:
    """从所有带 slug 的 creator 对象里汇出 creator.id -> slug 反查表"""
    out: dict[str, str] = {}
    for src in sources:
        for rec in src:
            c = rec.get("creator") if isinstance(rec, dict) else None
            if isinstance(c, dict) and c.get("id") and c.get("slug"):
                out[c["id"]] = c["slug"]
    return out


def _match_vendor(creator: str, name: str, vendors: dict[str, dict[str, Any]]):
    """厂商键匹配: 先原样, 再连字符/去空格变体 (AA 显示名 "Z AI" -> 键 zai)"""
    for cand in (creator, creator.replace("_", "-"), name.lower().replace(" ", "-"),
                 name.lower().replace(" ", "").replace(".", "").replace("-", "")):
        if cand and cand in vendors:
            return vendors[cand], cand
    return None, ""


def resolve_identity(
    record: dict[str, Any],
    reg_index: dict[str, dict[str, Any]],
    vendors: dict[str, dict[str, Any]],
    db_by_slug: dict[str, tuple[int, str, str, str]],
    db_by_base: dict[str, tuple[int, str, str, str]],
    creator_ids: dict[str, str] | None = None,
) -> tuple[ModelRow, int | None, str | None, str | None]:
    """返回 (ModelRow, existing_pk, rename_from, provider_fixed_from)

    existing_pk 非空表示命中库内既有模型行: 存储层应 UPDATE 该行而不是新建,
    这样 model_pk 不变, 挂在它上面的历史评测记录不会被打断。
    """
    slug = record.get("slug") or ""
    name = record.get("name") or ""
    reg = reg_index.get(slug) or {}
    notes: list[str] = []

    c_raw = reg.get("creator") or record.get("creator") or {}
    c_slug = creator_slug(c_raw, creator_ids)
    c_name = c_raw.get("name") or ""
    vendor_cfg, _matched_key = _match_vendor(c_slug, c_name, vendors)
    if vendor_cfg is None:
        namespace = c_slug.replace("_", "-") or "unattributed"
        tier = "unclassified"
        notes.append(f"AA creator {c_slug or c_name or '?'} 不在 config/vendors.yaml, 需人工归类")
    else:
        namespace = vendor_cfg["namespace"]
        tier = vendor_cfg.get("tier", "excluded")

    base = (reg.get("release") or {}).get("slug") or slug
    effort = (reg.get("effort") or {}).get("slug") or effort_from_name(name) or ""
    model_id = f"{namespace}/{dotted(base)}"

    rename_from: str | None = None
    provider_fixed_from: str | None = None
    existing = db_by_slug.get(slug) or db_by_base.get(base)
    existing_pk: int | None = None
    if existing:
        existing_pk, old_id, _old_level, old_provider = existing
        if old_id != model_id:
            rename_from = old_id
            notes.append(f"库内旧 ID {old_id} 规范为 {model_id}")
        if (old_provider or "") != namespace:
            provider_fixed_from = old_provider or None
            notes.append(f"provider 由 {old_provider or 'NULL'} 依 AA creator 更正为 {namespace}")
    row = ModelRow(
        model_id=model_id,
        reasoning_level=effort,
        aa_slug=slug,
        aa_base_slug=base,
        display_name=name or ((reg.get("release") or {}).get("name")) or slug,
        provider=namespace,
        tier=tier,
        family=(reg.get("release") or {}).get("slug"),
        release_date=reg.get("releaseDate") or record.get("releaseDate"),
        deprecated=int(bool(reg.get("deprecated"))),
        is_reasoning=_bool_to_int(reg.get("isReasoning", record.get("isReasoning"))),
        **model_metadata(record),
        needs_manual_review=int(tier != "core"),
        notes=notes,
    )
    return row, existing_pk, rename_from, provider_fixed_from


def build_evals(
    record: dict[str, Any],
    row: ModelRow,
    bidx: dict[str, dict[str, Any]],
) -> tuple[list[EvalRow], int]:
    """逐字段取分。返回 (评测行, 因非数值被跳过的字段数)。

    run_cost_usd = 跑完该评测整套题一次的美元消耗
                   = (输入 token × 输入单价 + (作答+推理 token) × 输出单价) / 1e6
    这是 AA payload 的 canonicalEvalTokenCounts 与其定价的乘积, 不是估算的
    "每个任务成本" —— v4 曾把它标成 cost_per_task, 见 docs/changelog.md #11。
    """
    token_costs = record.get("canonicalEvalTokenCounts") or {}
    evals: list[EvalRow] = []
    skipped = 0
    # AA 在两个 payload 里对同一指标用过不同大小写 (榜单页 itbenchSre /
    # 详情页 itBenchSre), 精确匹配会静默丢字段 —— 见 changelog #37
    lowered = {k.lower(): k for k in record}
    for aa_key, spec in bidx.items():
        raw = record.get(aa_key)
        if raw is None:
            alt = lowered.get(aa_key.lower())
            if alt and alt != aa_key:
                raw = record.get(alt)
        if raw is None:
            continue
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            skipped += 1
            continue
        tokens = token_costs.get(aa_key) or {}
        tin = _num(tokens.get("input"))
        tans = _num(tokens.get("answer"))
        trea = _num(tokens.get("reasoning"))
        out_tokens = int((tans or 0) + (trea or 0)) if (tans is not None or trea is not None) else None
        cost = None
        if (
            tin is not None
            and out_tokens
            and row.pricing_input is not None
            and row.pricing_output is not None
        ):
            cost = round((tin * row.pricing_input + out_tokens * row.pricing_output) / 1e6, 6)
        breakdown = record.get(spec["breakdown_key"]) if spec.get("breakdown_key") else None
        evals.append(
            EvalRow(
                benchmark=spec["canonical"],
                score_raw=float(raw),
                score_type=spec["scale"],
                dimension=spec["dimension"],
                direction=spec["direction"],
                confidence=float(spec["confidence"]),
                input_tokens=int(tin) if tin is not None else None,
                output_tokens=out_tokens,
                reasoning_tokens=int(trea) if trea is not None else None,
                run_cost_usd=cost,
                breakdown=breakdown if isinstance(breakdown, dict) else None,
            )
        )
    return evals, skipped


def map_records(
    records: Iterable[dict[str, Any]],
    registry: Iterable[dict[str, Any]],
    bm: dict[str, Any],
    vendors: dict[str, dict[str, Any]],
    db_by_slug: dict[str, tuple[int, str, str, str]],
    db_by_base: dict[str, tuple[int, str, str, str]],
) -> tuple[list[MappedModel], dict[str, Any]]:
    bidx = benchmark_index(bm)
    reg_index = build_registry_index(registry)
    creator_ids = build_creator_id_index(records, registry)
    rec_list = list(records)
    mapped: list[MappedModel] = []
    stats: dict[str, Any] = {"excluded": 0, "collisions": [], "by_tier": {}, "no_scores": 0,
                             "renames": [], "provider_fixes": []}

    for rec in rec_list:
        row, existing_pk, rename_from, provider_fixed = resolve_identity(
            rec, reg_index, vendors, db_by_slug, db_by_base, creator_ids
        )
        if row.tier == "excluded":
            stats["excluded"] += 1
            continue
        evals, skipped = build_evals(rec, row, bidx)
        if skipped:
            stats["non_numeric_skipped"] = stats.get("non_numeric_skipped", 0) + skipped
        if not evals:
            stats["no_scores"] += 1
        stats["by_tier"][row.tier] = stats["by_tier"].get(row.tier, 0) + 1
        if rename_from:
            stats["renames"].append({"from": rename_from, "to": row.model_id,
                                     "aa_slug": row.aa_slug,
                                     "needs_review": bool(row.tier != "core")})
        if provider_fixed:
            stats["provider_fixes"].append({"model_id": row.model_id,
                                            "from": provider_fixed, "to": row.provider})
        mapped.append(
            MappedModel(
                row=row,
                evals=evals,
                existing_pk=existing_pk,
                rename_from=rename_from,
                provider_fixed_from=provider_fixed,
            )
        )

    seen: dict[tuple[str, str], str] = {}
    for m in mapped:
        key = (m.row.model_id, m.row.reasoning_level)
        if key in seen:
            stats["collisions"].append({"key": list(key), "aa_slugs": [seen[key], m.row.aa_slug]})
        else:
            seen[key] = m.row.aa_slug
    stats["benchmark_fields"] = len(bidx)
    stats["total"] = len(mapped)
    return mapped, stats
