#!/usr/bin/env python3
"""导出前端数据 — frontend/data.json (v2, 2026-09-20)

口径:
    - 只导出最新快照 (或 --snapshot-date 指定的一批) 的数值; 历史快照留在库里,
      通过 metadata.snapshots 版本轨迹可查, 不进榜面。
    - 只导出 config/vendors.yaml 中 tier=core / reference 的模型;
      core 参与综合榜, reference 带 in_scope=false 标记供前端灰显。
    - 只导出前端实际会读的字段 + 溯源字段, 不再整表 dump。旧版把
      context_window_fmt / homepage / parameters 等前端从不引用的字段全部导出,
      使 data.json 涨到 8.6MB (见 docs/changelog.md #15)。
    - 维度、权重、归一化、基准模型、benchmark 元信息全部从 config/ 注入,
      前端不再自带一份硬编码副本 (见 docs/changelog.md #7)。
    - benchmark_meta 由 config/benchmarks.yaml 生成。旧版是手写的 15 条字典,
      覆盖不到库里 27 个 benchmark, 且字段名与前端不匹配 (changelog #16)。

用法:
    python3 scripts/export_frontend_data.py
    python3 scripts/export_frontend_data.py --snapshot-date 2026-08-09 --out /tmp/x.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from src.compute.scoring import build_scores                    # noqa: E402
from src.paths import DB_PATH, FRONTEND_DATA, config_path  # noqa: E402

# 混合单价假设: 典型调用输入:输出 = 3:1。显式假设, 前端须标注「估算」。
BLEND_RATIO_IN, BLEND_RATIO_OUT = 3, 1

# 本站自己算出来的指标, 不是 AA 原始数值 —— 计数和溯源都要分开
DERIVED_KEYS = ("cost_per_eval", "pricing")


def _f(v):
    if v is None or isinstance(v, (int, float)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_config() -> dict:
    bm = yaml.safe_load(config_path("benchmarks.yaml").read_text(encoding="utf-8"))
    st = yaml.safe_load(config_path("settings.yaml").read_text(encoding="utf-8"))
    vendors = yaml.safe_load(config_path("vendors.yaml").read_text(encoding="utf-8"))["vendors"]
    return {"bm": bm, "st": st, "vendors": vendors}


def _norm_open(raw) -> str:
    low = (raw or "").lower()
    if "permissive" in low or low in ("open", "open weights"):
        return "Open"
    if "license required" in low or low == "hybrid":
        return "Hybrid"
    if "open" in low:
        return "Open"
    return "Proprietary"


def bench_meta(cfg: dict) -> dict:
    """benchmark_meta: 数据源名称 / 口径 / 可信度 / 来源链接

    修 #16: 旧导出器只写 `source_url`, 而前端读的是 `meta.source`,
    字段名不匹配导致来源标签在页面上从来没出现过。现在两者都给, 语义各自明确。
    """
    out: dict[str, dict] = {}
    page_url = (cfg["bm"].get("provenance") or {}).get("leaderboard_url")
    dims = cfg["bm"].get("dimensions") or {}
    for dim_key, dim in dims.items():
        if dim_key == "tags":
            continue
        for key, src in (dim.get("sources") or {}).items():
            out[key] = {
                "name": src.get("name", key),
                "dimension": dim_key,
                "source": src.get("name", key),
                "source_url": src.get("source_url") or page_url,
                "methodology_url": src.get("methodology_url"),
                "official_url": src.get("official_url"),
                "scale": src.get("scale", "ratio"),
                "direction": src.get("direction", "higher"),
                "tier": src.get("tier", "secondary"),
                "confidence": src.get("confidence"),
                "freshness": src.get("freshness"),
                "status": src.get("status"),
                "note": src.get("note"),
            }
    for key, tag in (dims.get("tags") or {}).items():
        if not isinstance(tag, dict):
            continue
        out[key] = {
            "name": tag.get("name", key), "dimension": None, "source": tag.get("name", key),
            "source_url": tag.get("source_url") or page_url, "scale": "index",
            "direction": "higher", "tier": "tag", "scoring": False, "confidence": None,
            "freshness": "snapshot", "status": "production", "note": tag.get("description"),
        }
    out["cost_per_eval"] = {
        "name": "整轮评测消耗 · 中位", "dimension": "cost", "source": "本站按 AA 数据计算",
        "source_url": page_url, "scale": "usd", "direction": "lower", "tier": "primary",
        "confidence": 0.85, "freshness": "snapshot", "status": "production",
        "note": "跑完该评测整套题一次的美元消耗中位数, 由 AA 公布的逐项 token 用量乘其定价得出。"
                "它不是「每个任务的成本」: 推理型模型 reasoning token 越多这个值越高。"
                "v4 曾把它错标为 cost_per_task, 见 changelog #11。",
    }
    out["pricing"] = {
        "name": "混合单价 · 估算", "dimension": "cost", "source": "AA 公布 API 定价",
        "source_url": page_url, "scale": "usd", "direction": "lower", "tier": "secondary",
        "confidence": 0.9, "freshness": "snapshot", "status": "production",
        "note": f"USD / 1M tokens; 按输入:输出 = {BLEND_RATIO_IN}:{BLEND_RATIO_OUT} 估算的混合单价,"
                " 明细给出原始输入 / 输出 / 缓存价",
    }
    return out


def pick_snapshot(conn, want: str | None) -> sqlite3.Row:
    if want:
        row = conn.execute("SELECT * FROM snapshots WHERE snapshot_date = ?", (want,)).fetchone()
        if not row:
            raise SystemExit(f"快照 {want} 不存在")
        return row
    row = conn.execute("SELECT * FROM snapshots ORDER BY snapshot_date DESC LIMIT 1").fetchone()
    if not row:
        raise SystemExit("库中没有任何快照, 先跑 scripts/collect_aa_v3.py")
    return row


# 同一模型多个推理档位行时, 用哪一行的 display_name 作为模型显示名。
# 优先 AA 的基座 slug (= family), 再按档位常见度排序; 否则会把
# "Claude Fable 5.1 (High Effort)" 这种变体名当成模型本名展示。
LEVEL_PREF = {"max": 0, "": 1, "adaptive-max": 2, "xhigh": 3, "high": 4,
              "medium": 5, "low": 6, "minimal": 7, "reasoning": 8, "non-reasoning": 9}


def collect(conn, snapshot, cfg) -> tuple[dict, dict]:
    """取该快照下的模型行与评测行, 并计算成本维度的两个派生指标"""
    tiers = ("core", "reference")
    grouped: dict[str, list] = {}
    for r in conn.execute(
        """SELECT * FROM models WHERE tier IN (?, ?)
           ORDER BY provider, model_id, reasoning_level""", tiers,
    ).fetchall():
        grouped.setdefault(r["model_id"], []).append(r)

    models: dict[str, dict] = {}
    for mid, rows in grouped.items():
        base = sorted(
            rows,
            key=lambda r: (0 if r["aa_slug"] and r["aa_slug"] == r["family"] else 1,
                           LEVEL_PREF.get(r["reasoning_level"] or "", 99)),
        )[0]
        # 模型级常量属性: 同一 model_id 的多个档位行里可能只有其中一行有值
        # (context_window 就是典型 —— 它只来自详情页补采, 见 changelog #37)。
        # 价格与速度**不做合并**: 它们按档位不同, 混用会给出错误的成本结论。
        def _coalesce(col):
            for r in rows:
                if r[col] is not None:
                    return r[col]
            return None

        models[mid] = {
            "id": mid,
            "provider": base["provider"],
            "display_name": base["display_name"] or mid,
            "tier": base["tier"],
            "in_scope": base["tier"] == "core",
            "release_date": base["release_date"],
            "is_reasoning": None if base["is_reasoning"] is None else bool(base["is_reasoning"]),
            "open_source": _norm_open(base["open_source"]),
            "supports_vision": (bool(base["supports_vision"])
                                if base["supports_vision"] is not None else None),
            "supports_audio": (bool(base["supports_audio"])
                               if base["supports_audio"] is not None else None),
            "pricing_input": _f(base["pricing_input"]),
            "pricing_output": _f(base["pricing_output"]),
            "pricing_cache_input": _f(base["pricing_cache_input"]),
            "answer_speed": _f(base["answer_speed"]),
            "openness_index": _f(base["openness_index"]),
            "context_window": _coalesce("context_window"),
            "parameters_b": _f(_coalesce("parameters")),
            "active_params_b": _f(_coalesce("active_params")),
            "time_per_task_s": _f(_coalesce("time_per_task_s")),
            "size_class": base["size_class"],
            "deprecated": bool(base["deprecated"]),
            "needs_manual_review": bool(base["needs_manual_review"]),
            "official_metrics": [],
            "reasoning_levels": {},
        }
        for r in rows:
            models[mid]["reasoning_levels"][r["reasoning_level"] or ""] = {
                "aa_slug": r["aa_slug"], "pk": r["id"],
                "display_name": r["display_name"],
            }

    benchmarks: dict[str, list] = {}
    per_model_cost: dict[str, list] = {}
    official: dict[str, list] = {}
    evals = conn.execute(
        """SELECT be.*, m.model_id, m.reasoning_level, m.display_name
           FROM benchmark_evals be
           JOIN models m ON be.model_pk = m.id
           WHERE be.snapshot_id = ? AND m.tier IN (?, ?)
           ORDER BY be.benchmark, be.score_raw DESC""", (snapshot["id"], *tiers),
    ).fetchall()
    for r in evals:
        entry = {
            "model_id": r["model_id"],
            "reasoning_level": r["reasoning_level"] or "",
            "display_name": r["display_name"],
            "score_raw": _f(r["score_raw"]),
            "score_type": r["score_type"],
            "input_tokens": r["input_tokens"],
            "output_tokens": r["output_tokens"],
            "reasoning_tokens": r["reasoning_tokens"],
            "cost_usd": _f(r["cost_usd"]),
            "run_cost_usd": _f(r["run_cost_usd"]),
            "breakdown": json.loads(r["breakdown"]) if r["breakdown"] else None,
            "source": r["source"],
            "source_url": r["source_url"],
            "confidence": r["confidence"],
            "observed_at": r["observed_at"],
        }
        if r["benchmark"].endswith("_official"):
            # 厂商自报口径: 单独挂到模型上, 绝不进 benchmarks 表 ——
            # 否则会被 bench_groups 之外的路径误当成 AA 同分数参与归一化。
            bd = entry["breakdown"] or {}
            official.setdefault(r["model_id"], []).append({
                "benchmark": r["benchmark"],
                "name": bd.get("name") or r["benchmark"],
                "value": entry["score_raw"],
                "unit": entry["score_type"],
                "note": bd.get("note"),
                "source": r["source"],
                "source_url": r["source_url"],
                "confidence": r["confidence"],
                "observed_at": r["observed_at"],
            })
            continue
        benchmarks.setdefault(r["benchmark"], []).append(entry)
        if entry["run_cost_usd"]:
            per_model_cost.setdefault(r["model_id"], []).append(
                {"benchmark": r["benchmark"], "cost_usd": entry["run_cost_usd"]}
            )

    page_url = (cfg["bm"].get("provenance") or {}).get("leaderboard_url")
    for mid, items in per_model_cost.items():
        costs = sorted(i["cost_usd"] for i in items)
        median = round(costs[len(costs) // 2], 4)
        m = models.get(mid)
        benchmarks.setdefault("cost_per_eval", []).append({
            "model_id": mid, "reasoning_level": "",
            "display_name": m["display_name"] if m else mid,
            "score_raw": median, "score_type": "usd",
            "input_tokens": None, "output_tokens": None, "reasoning_tokens": None,
            "cost_usd": median, "run_cost_usd": median,
            "breakdown": {"items": items, "n_benchmarks": len(costs)},
            "source": "derived_from_artificial_analysis", "source_url": page_url,
            "confidence": 0.85, "observed_at": snapshot["snapshot_date"],
        })
    for mid, m in models.items():
        pin, pout = m.get("pricing_input"), m.get("pricing_output")
        if pin is None or pout is None:
            continue
        blended = round((BLEND_RATIO_IN * pin + BLEND_RATIO_OUT * pout)
                        / (BLEND_RATIO_IN + BLEND_RATIO_OUT), 4)
        benchmarks.setdefault("pricing", []).append({
            "model_id": mid, "reasoning_level": "", "display_name": m["display_name"],
            "score_raw": blended, "score_type": "usd",
            "input_tokens": None, "output_tokens": None, "reasoning_tokens": None,
            "cost_usd": blended, "run_cost_usd": None,
            "breakdown": {"input_per_1m": pin, "output_per_1m": pout,
                          "cache_input_per_1m": m.get("pricing_cache_input"),
                          "assumption": f"input:output = {BLEND_RATIO_IN}:{BLEND_RATIO_OUT}"},
            "source": "artificial_analysis_pricing", "source_url": page_url,
            "confidence": 0.9, "observed_at": snapshot["snapshot_date"],
        })
    for key in benchmarks:
        benchmarks[key].sort(key=lambda e: -(e["score_raw"] or 0))
    for mid, items in official.items():
        if mid in models:
            models[mid]["official_metrics"] = sorted(
                items, key=lambda x: -(x["value"] if isinstance(x["value"], (int, float)) else 0))
    return models, benchmarks


def frontend_config(cfg: dict, models: dict) -> dict:
    """注入前端: 维度 / 权重 / 归一化 / 基准 / 预设 / 厂商展示元信息全部来自 config/"""
    bm, st = cfg["bm"], cfg["st"]
    dimensions: list[dict] = []
    bench_groups: dict[str, list] = {}
    bench_cn: dict[str, str] = {}
    for key, dim in (bm.get("dimensions") or {}).items():
        if key == "tags":
            continue
        dimensions.append({"key": key, "name": dim.get("name"),
                           "desc": dim.get("description"), "weight": dim.get("weight")})
        keys = ["cost_per_eval", "pricing"] if key == "cost" else list((dim.get("sources") or {}))
        bench_groups[key] = keys
        for k in keys:
            src = (dim.get("sources") or {}).get(k) or {}
            bench_cn[k] = (src.get("name") or k).replace("_", " ")
    providers: dict[str, dict] = {}
    for _slug, v in cfg["vendors"].items():
        providers.setdefault(v["namespace"],
                             {"display": v.get("display", v["namespace"]), "tier": v.get("tier")})
    used = {m["provider"] for m in models.values()}
    providers = {k: v for k, v in sorted(providers.items()) if k in used}
    return {
        "dimensions": dimensions,
        "bench_groups": bench_groups,
        "bench_cn": bench_cn,
        "providers": providers,
        "weights": st.get("weights"),
        "weights_no_preference": st.get("weights_no_preference"),
        "presets": st.get("presets"),
        "normalization": st.get("normalization"),
        "baseline": st.get("baseline_model"),
    }


def snapshot_trail(conn) -> list[dict]:
    return [
        {
            "snapshot_date": r["snapshot_date"], "model_count": r["model_count"],
            "eval_count": r["eval_count"], "collected_at": r["fetched_at"],
            "source_url": r["source_url"], "html_sha256": r["html_sha256"],
            "notes": r["notes"],
        }
        for r in conn.execute("SELECT * FROM snapshots ORDER BY snapshot_date DESC").fetchall()
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="导出 frontend/data.json")
    ap.add_argument("--snapshot-date", default=None, help="指定快照日, 默认取最新")
    ap.add_argument("--out", default=str(FRONTEND_DATA))
    ap.add_argument("--print-summary", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    snapshot = pick_snapshot(conn, args.snapshot_date)
    models, benchmarks = collect(conn, snapshot, cfg)
    meta = bench_meta(cfg)
    trail = snapshot_trail(conn)
    conn.close()

    provenance = cfg["bm"].get("provenance") or {}
    unknown_meta = sorted(set(benchmarks) - set(meta))
    fc = frontend_config(cfg, models)
    # 默认榜单的分数在这里算好写入 data.json: 前端只在用户手调权重时重算,
    # 保证"默认视图看到的数"与"测试校验的数"出自同一份实现 (changelog #27)
    scores, explain = build_scores(
        models, benchmarks, meta, {**cfg["st"], "_bench_groups": fc["bench_groups"]})
    for mid, s in scores.items():
        models[mid]["scores"] = s
    fc["leaderboards"] = cfg["st"].get("leaderboards")
    output = {
        "models": models,
        "benchmarks": benchmarks,
        "benchmark_meta": meta,
        "config": fc,
        "provenance": {
            "leaderboard_url": provenance.get("leaderboard_url"),
            "dataset_url": provenance.get("dataset_url"),
            "paper_url": provenance.get("paper_url"),
            "license": provenance.get("license"),
            "caveat": provenance.get("caveat"),
            "date_semantics": provenance.get("date_semantics"),
        },
        "metadata": {
            "snapshot_date": snapshot["snapshot_date"],
            "collected_at": snapshot["fetched_at"],
            "html_sha256": snapshot["html_sha256"],
            "source_url": snapshot["source_url"],
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model_count": len(models),
            "model_entry_count": sum(len(m["reasoning_levels"]) for m in models.values()),
            "core_model_count": sum(1 for m in models.values() if m["in_scope"]),
            "reference_model_count": sum(1 for m in models.values() if not m["in_scope"]),
            "benchmark_count": len(benchmarks),
            "eval_count": sum(len(v) for v in benchmarks.values()),
            # 原始行 vs 派生行分开计数: 快照轨迹里的 eval_count 只含 AA 原始行,
            # 不分开的话前端无法判断"这批数据到底进没进来" (changelog #30)
            "raw_eval_count": sum(len(v) for k, v in benchmarks.items()
                                  if k not in DERIVED_KEYS),
            "derived_eval_count": sum(len(v) for k, v in benchmarks.items()
                                      if k in DERIVED_KEYS),
            "official_metric_count": sum(len(m.get("official_metrics") or [])
                                         for m in models.values()),
            "schema_version": 2,
            "scoring": explain,
            "snapshots": trail[:12],
            "data_warning": ({"benchmarks_without_meta": unknown_meta} if unknown_meta else None),
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")
    md = output["metadata"]
    print(f"✓ 导出 {out}  ({out.stat().st_size / 1024:.0f} KB, 快照 {md['snapshot_date']})")
    print(f"  模型 {md['model_count']} (核心 {md['core_model_count']} + "
          f"参照 {md['reference_model_count']}) / {md['model_entry_count']} 个档位")
    print(f"  benchmark {md['benchmark_count']} 项 / 评测 {md['eval_count']} 条")
    if unknown_meta:
        print(f"  ⚠️ 无元信息的数据源, 需在 benchmarks.yaml 登记: {unknown_meta}")
    def _top(field: str, n: int = 5) -> None:
        rows = sorted(((m["scores"].get(field), mid, m) for mid, m in models.items()
                       if m["in_scope"] and m["scores"].get(field) is not None), reverse=True)
        print(f"  {field} 前 {n}:")
        for i, (v, mid, m) in enumerate(rows[:n], 1):
            extra = (f"  ${m['scores']['blended_price']}/1M"
                     if m["scores"].get("blended_price") else "")
            print(f"    {i}. {mid:32} {v:6.1f}{extra}")

    _top("capability")
    _top("value")
    if args.print_summary:
        for k, v in sorted(benchmarks.items()):
            print(f"    {k:24} {len(v):3} 条  首位={v[0]['model_id'] if v else '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
