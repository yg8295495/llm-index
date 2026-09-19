"""榜单计分 — 单一实现，导出器与 API 共用

为什么放这里 (docs/changelog.md #7 #27):
    归一化与加权以前在 Python 和前端 JS 各写了一份且不同步，线上生效的是 JS 那份，
    src/compute/ 沦为死代码。现在默认榜单的分数由这里算好写进 data.json，
    用户手调权重时才由前端重算 —— 同一套公式，只有一个权威来源。

口径:
    - 归一化用 min-max 并钳在 [0,100]。AA-Omniscience 等指数可为负，
      比值法 (best/max*100) 会算出负分，故不使用 (#5 #6)。
    - 计分基准集 = 九家范围内的模型 (tier=core)。参照模型在同一标尺上取分但不参与
      排名，避免范围外模型扭曲榜内相对位置。
    - 同一模型的多个推理档位取该档位中的最好成绩 (用户关心"这个模型最强能到多少")。
"""

from __future__ import annotations


from src.collector.mapping import dotted  # noqa: F401  (re-export 便于排查)

SCORE_CLAMP = (0.0, 100.0)


def _clamp(v: float) -> float:
    lo, hi = SCORE_CLAMP
    return max(lo, min(hi, v))


def _bench_bounds(rows: list[float]) -> tuple[float, float]:
    return (min(rows), max(rows)) if rows else (0.0, 0.0)


def best_per_model(bench_rows: list[dict], universe: set[str],
                   reverse: bool) -> dict[str, float]:
    """一个 benchmark 下, 取每个模型所有推理档位里最好的一条原始分"""
    best: dict[str, float] = {}
    for r in bench_rows:
        mid = r.get("model_id")
        v = r.get("score_raw")
        if mid not in universe or v is None:
            continue
        if mid not in best or (v > best[mid] if not reverse else v < best[mid]):
            best[mid] = v
    return best


def normalize_dim(dim: str, bench_groups: dict[str, list[str]], benchmarks: dict,
                  meta: dict, universe: set[str]) -> tuple[dict[str, float], dict[str, int]]:
    """返回 ({model_id: 维度分}, {model_id: 有数据的 benchmark 数})"""
    keys = [b for b in bench_groups.get(dim, []) if b in benchmarks]
    per_model: dict[str, list[float]] = {}
    covered: dict[str, int] = {}
    for b in keys:
        m = meta.get(b) or {}
        reverse = m.get("direction") == "lower"
        raw = best_per_model(benchmarks[b], universe, reverse)
        if not raw:
            continue
        lo, hi = _bench_bounds(list(raw.values()))
        for mid, v in raw.items():
            n = 50.0 if hi == lo else (v - lo) / (hi - lo) * 100.0
            per_model.setdefault(mid, []).append(100.0 - n if reverse else n)
            covered[mid] = covered.get(mid, 0) + 1
    scores = {mid: _clamp(sum(vs) / len(vs)) for mid, vs in per_model.items()}
    return scores, covered


def active_weights(settings: dict, dim_scores: dict[str, dict], prefer_no_pref: bool
                   ) -> dict[str, float]:
    """按实际有数据的维度取权重并重新归一化。

    preference 本批无数据 -> 用 weights_no_preference; 若连这组也没有, 就把
    weights 里有数据的维度按比例归一。
    """
    base = dict(settings.get("weights") or {})
    if prefer_no_pref and settings.get("weights_no_preference"):
        base = dict(settings["weights_no_preference"])
    used = {d: w for d, w in base.items() if w and dim_scores.get(d)}
    total = sum(used.values())
    if not total:
        return {}
    return {d: w / total for d, w in used.items()}


def blended_price(m: dict, ratio_in: int = 3, ratio_out: int = 1) -> float | None:
    pin, pout = m.get("pricing_input"), m.get("pricing_output")
    if pin is None or pout is None:
        return None
    return round((ratio_in * pin + ratio_out * pout) / (ratio_in + ratio_out), 4)


def build_scores(models: dict, benchmarks: dict, meta: dict, settings: dict
                 ) -> tuple[dict, dict]:
    """返回 ({model_id: scores}, scoring_说明)

    scores = {dims, coverage, capability, cost, value, composite, blended_price}
    """
    core_ids = {mid for mid, m in models.items() if m.get("in_scope")}
    universe = core_ids or set(models)
    groups = (settings.get("_bench_groups") or {})
    lb = settings.get("leaderboards") or {}
    cap_dims_cfg = (lb.get("capability") or {}).get("dimensions") or {}

    dims = {"factual": {}, "workflow": {}, "engineering": {}, "cost": {}, "preference": {}}
    coverage: dict[str, dict[str, int]] = {}
    dim_bench_count: dict[str, int] = {}
    for dim in list(dims):
        if dim == "cost":
            continue
        sc, cov = normalize_dim(dim, groups, benchmarks, meta, universe)
        dims[dim] = sc
        coverage[dim] = cov
        dim_bench_count[dim] = len([b for b in groups.get(dim, []) if b in benchmarks])

    # 成本维: 直接用混合单价 (稳定, 不受"某套题多大"影响), 反向 min-max
    prices = {mid: blended_price(models[mid]) for mid in universe}
    prices = {k: v for k, v in prices.items() if v is not None}
    if prices:
        lo, hi = _bench_bounds(list(prices.values()))
        for mid, p in prices.items():
            dims["cost"][mid] = _clamp(50.0 if hi == lo else (hi - p) / (hi - lo) * 100.0)

    pref_empty = not dims["preference"]
    weights = active_weights(settings, dims, prefer_no_pref=pref_empty)
    cap_weights = {d: w for d, w in cap_dims_cfg.items() if dims.get(d)}
    cap_total = sum(cap_weights.values())
    cap_weights = {d: w / cap_total for d, w in cap_weights.items()} if cap_total else {}

    out: dict[str, dict] = {}
    floor = (lb.get("value") or {}).get("floor_price", 0.01)
    for mid, m in models.items():
        dim_scores = {d: round(dims[d][mid], 2) for d in dims if mid in dims[d]}
        cov = {d: {"n": coverage[d].get(mid, 0), "of": dim_bench_count.get(d, 0)}
               for d in coverage if d in dim_scores}
        capability = None
        if cap_weights and dim_scores:
            vals = {d: dim_scores[d] for d in cap_weights if d in dim_scores}
            wsum = sum(cap_weights[d] for d in vals)
            if wsum:
                capability = round(sum(vals[d] * cap_weights[d] for d in vals) / wsum, 2)
        composite = None
        if weights and dim_scores:
            vals = {d: dim_scores[d] for d in weights if d in dim_scores}
            wsum = sum(weights[d] for d in vals)
            if wsum:
                composite = round(sum(vals[d] * weights[d] for d in vals) / wsum, 2)
        price = prices.get(mid)
        value_raw = round(capability / max(price, floor), 4) if (capability and price) else None
        out[mid] = {
            "dims": dim_scores,
            "coverage": cov,
            "capability": capability,
            "cost": round(dim_scores["cost"], 2) if "cost" in dim_scores else None,
            "composite": composite,
            "blended_price": price,
            "value_raw": value_raw,
            "ranked": bool(m.get("in_scope")),
        }

    # 性价比指数: 把 value_raw 压到 [0,100] 便于与其他榜同屏比较
    raws = {mid: s["value_raw"] for mid, s in out.items() if s["value_raw"]}
    if raws:
        lo, hi = _bench_bounds(list(raws.values()))
        for mid, r in raws.items():
            out[mid]["value"] = round(_clamp(50.0 if hi == lo
                                             else (r - lo) / (hi - lo) * 100.0), 2)
    for s in out.values():
        s.setdefault("value", None)

    explain = {
        "universe": "core_only",
        "universe_size": len(universe),
        "normalization": settings.get("normalization") or {},
        "weights_in_effect": {k: round(v, 4) for k, v in weights.items()},
        "capability_weights": {k: round(v, 4) for k, v in cap_weights.items()},
        "preference_status": "empty_reweighted" if pref_empty else "present",
        "value_formula": (lb.get("value") or {}).get("formula"),
        "variant_rule": "best_per_model",
    }
    return out, explain
