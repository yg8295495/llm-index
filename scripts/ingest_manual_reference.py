#!/usr/bin/env python3
"""把厂商自报评测数据登记入库 (2026-09-20)

用于 AA 尚未收录、但用户需要判断的模型（当前只有混元 Hy4 preview）。

为什么单独一个脚本而不是塞进采集器:
    厂商自报分数与 AA 同口径分数**不能混算**。证据见
    data/raw/manual/hy4_preview_2026-09-20.yaml —— 腾讯官方称 Hy3 在
    Terminal-Bench 2.1 得 70.8，而 AA 实测 Hy3 是 64.42，差 6.4 分，
    说明实现/版本/采样不同。所以这类数据:
      - benchmark key 一律带 _official 后缀，天然不会被 config.bench_groups 捞进归一化;
      - source 标 '<provider>_official'，confidence 压低;
      - 快照行 notes 写明是自报口径。
    前端只在模型详情里单独展示，不进能力榜/性价比榜/综合榜。

用法:
    python3 scripts/ingest_manual_reference.py            # 干跑
    python3 scripts/ingest_manual_reference.py --no-dry-run
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

from src.collector.mapping import load_vendors  # noqa: E402
from src.paths import DB_PATH, SNAPSHOT_DIR, config_path  # noqa: E402
from src.storage import snapshot_store as S  # noqa: E402

OFFICIAL_CONFIDENCE = 0.45   # 厂商自报: 口径不可核验, 置信度显式压低


def _latest_aa_batch(conn) -> str:
    """最新一个含 AA 同口径评测的快照日 (YYYY-MM-DD 字符串); 没有则返回 ''"""
    row = conn.execute(
        """SELECT s.snapshot_date FROM snapshots s
           JOIN benchmark_evals be ON be.snapshot_id = s.id
           WHERE be.benchmark NOT LIKE '%_official' AND be.source LIKE 'artificial%'
           GROUP BY s.id ORDER BY s.snapshot_date DESC LIMIT 1""").fetchone()
    return str(row[0])[:10] if row else ""


def load_entries() -> list[dict]:
    wl = yaml.safe_load(config_path("watchlist.yaml").read_text(encoding="utf-8")) or {}
    out = []
    for item in wl.get("manual") or []:
        f = SNAPSHOT_DIR.parent / "manual" / item["file"]
        if not f.exists():
            print(f"⚠️ 跳过 {item['model_id']}: 找不到 {f}")
            continue
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        data["_watchlist_reason"] = item.get("reason", "")
        data["_file"] = f.name
        out.append(data)
    return out


def ingest(conn, doc, dry_run):
    mid = doc["model_id"]
    provider = doc["provider"]
    vendors = load_vendors()
    tier = next((v.get("tier") for v in vendors.values() if v["namespace"] == provider),
                "unclassified")
    # snapshot_date 三种写法: 'latest' = 跟着最新 AA 批次走(推荐, 日更后不必改 YAML);
    # 显式日期 = 回填某一批历史数据; 缺省 = 退回 collected_at 的日期并告警。
    raw_date = str(doc.get("snapshot_date") or "").strip()
    if raw_date.lower() in ("latest", "auto"):
        date_str = _latest_aa_batch(conn)
        if not date_str:
            raise SystemExit(f"{mid}: snapshot_date: latest, 但库里还没有 AA 批次, "
                             "请先跑 collect_aa_v3.py")
    else:
        date_str = raw_date[:10] or str(doc.get("collected_at", ""))[:10] or datetime.now(
            timezone.utc).date().isoformat()
        if not raw_date:
            print(f"   ⚠️ {mid}: YAML 未写 snapshot_date, 回退到 collected_at 日期 {date_str}")
    rel = (doc.get("sources") or {}).get("official_release") or {}
    snapshot_url = rel.get("url") or (doc.get("sources") or {}).get("model_card", {}).get("url")
    if not snapshot_url:
        raise SystemExit(f"{mid}: 没有任何 source url, 按标准拒绝入库")

    # 护栏: 自报数据必须落在"当前最新 AA 批次"同一天 (changelog #33 / #35 / #39)。
    #   - 日期比最新批次新 → 会凭空造出一个只含混元的更新快照, 而导出器按 snapshot_date
    #     取最新批次, 整个榜单被这一条模型顶掉 (2026-09-20 差点踩中);
    #   - 日期比最新批次旧 → 行是写进去了, 但前端永远读不到, 变成静默死数据;
    #   - 非日期值 (如 '2026-09-20-tencent-official') 按字典序排在真日期之后, 同样中招。
    # 三种都拒绝: 口径区分靠行级 source / confidence, 不靠另开快照日。
    newest = _latest_aa_batch(conn)
    if newest:
        if date_str > newest:
            raise SystemExit(
                f"{mid}: snapshot_date={date_str} 比最新 AA 批次 {newest} 更晚, "
                "会新建一个只含自报数据的批次并顶掉整个榜单。"
                f"请把 YAML 的 snapshot_date 改成 {newest}")
        if date_str < newest:
            raise SystemExit(
                f"{mid}: snapshot_date={date_str} 早于最新 AA 批次 {newest}, "
                "自报数据会落在旧快照里而前端按最新批次取数 = 永远不显示。"
                f"请把 YAML 的 snapshot_date 改成 {newest}")

    row = conn.execute("SELECT id FROM snapshots WHERE snapshot_date = ?", (date_str,)).fetchone()
    if row:
        sid = int(row[0])
        conn.execute(
            """UPDATE snapshots SET notes =
                   COALESCE(substr(notes,1,400),'') || ' | 含厂商自报指标（不参与排名）'
               WHERE id = ?""", (sid,))
    else:
        sid = S.upsert_snapshot(conn, date_str, {
            "source": f"{provider}_official",
            "source_url": snapshot_url,
            "fetched_at": doc.get("collected_at") or datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "notes": "厂商自报评测数据, 非 Artificial Analysis 同口径; 不参与站内归一化排名。"
                     + (doc.get("_watchlist_reason") or "")[:200],
        })

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    existing = conn.execute(
        "SELECT id FROM models WHERE model_id = ? AND reasoning_level = ?", (mid, "")
    ).fetchone()
    params = {
        "model_id": mid, "reasoning_level": "", "aa_slug": doc.get("aa_slug"),
        "aa_base_slug": mid.split("/")[-1], "display_name": doc["display_name"],
        "provider": provider, "family": mid.split("/")[-1],
        "release_date": doc.get("release_date"), "deprecated": 0, "tier": tier,
        "context_window": doc.get("context_window"), "context_window_fmt": None,
        "supports_vision": None, "supports_audio": None, "is_reasoning": None,
        "open_source": doc.get("open_source"), "size_class": None,
        "parameters": doc.get("parameters_b"), "active_params": doc.get("active_params_b"),
        "pricing_input": doc.get("pricing_input"), "pricing_output": doc.get("pricing_output"),
        "pricing_cache_input": None, "openness_index": None, "answer_speed": None,
        "needs_manual_review": 1, "status": "active", "__now": now,
    }
    if existing:
        pk = int(existing[0])
        action = "更新"
        if not dry_run:
            upd = {k: v for k, v in params.items() if k not in ("model_id", "reasoning_level",
                                                                "__now")}
            conn.execute("UPDATE models SET " + ", ".join(f"{k} = :{k}" for k in upd)
                         + ", updated_at = :__now WHERE id = :__pk",
                         {**upd, "__now": now, "__pk": pk})
    else:
        action = "新建"
        pk = None
        if not dry_run:
            cur = conn.execute(
                """INSERT INTO models (model_id, reasoning_level, aa_slug, aa_base_slug,
                    display_name, provider, family, release_date, deprecated, tier,
                    context_window, context_window_fmt, supports_vision, supports_audio,
                    is_reasoning, open_source, size_class, parameters, active_params,
                    pricing_input, pricing_output, pricing_cache_input, openness_index,
                    answer_speed, needs_manual_review, status, created_at, updated_at)
                   VALUES (:model_id, :reasoning_level, :aa_slug, :aa_base_slug,
                    :display_name, :provider, :family, :release_date, :deprecated, :tier,
                    :context_window, :context_window_fmt, :supports_vision,
                    :supports_audio, :is_reasoning, :open_source, :size_class, :parameters,
                    :active_params, :pricing_input, :pricing_output, :pricing_cache_input,
                    :openness_index, :answer_speed, :needs_manual_review, :status,
                    :__now, :__now)""", params)
            pk = int(cur.lastrowid)

    written = 0
    for m in doc.get("metrics") or []:
        if not m.get("benchmark") or m.get("value") is None:
            print(f"   ⚠️ 跳过缺字段指标: {m}")
            continue
        if not m.get("benchmark", "").endswith("_official"):
            raise SystemExit(f"{mid}: 指标 {m['benchmark']} 未标 _official 后缀, "
                             "会被误当成 AA 同口径数据")
        url = (doc.get("sources") or {}).get(m.get("source_key") or "official_release",
                                            {}).get("url") or snapshot_url
        if dry_run:
            written += 1
            continue
        dup = conn.execute(
            "SELECT 1 FROM benchmark_evals WHERE model_pk=? AND benchmark=? AND snapshot_id=?",
            (pk, m["benchmark"], sid)).fetchone()
        if dup:
            continue
        conn.execute(
            """INSERT INTO benchmark_evals
               (model_pk, benchmark, score, score_raw, score_type, input_tokens,
                output_tokens, reasoning_tokens, cost_usd, breakdown, source, confidence,
                observed_at, collected_at, snapshot_id, dimension, direction, source_url,
                run_cost_usd)
               VALUES (:model_pk, :benchmark, NULL, :score_raw, :score_type, NULL, NULL,
                NULL, NULL, :breakdown, :source, :confidence, :observed_at, :collected_at,
                :snapshot_id, :dimension, :direction, :source_url, NULL)""",
            {
                "model_pk": pk, "benchmark": m["benchmark"], "score_raw": float(m["value"]),
                "score_type": m.get("unit", "score"),
                "breakdown": json.dumps({"note": m.get("note"), "name": m.get("name")},
                                        ensure_ascii=False),
                "source": f"{provider}_official", "confidence": OFFICIAL_CONFIDENCE,
                "observed_at": date_str, "collected_at": doc.get("collected_at"),
                "snapshot_id": sid, "dimension": m.get("dimension"),
                "direction": m.get("direction", "higher"), "source_url": url,
            })
        written += 1
    return action, pk, written, tier, sid


def main() -> int:
    ap = argparse.ArgumentParser(description="登记厂商自报评测数据")
    ap.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    ap.set_defaults(dry_run=True)
    args = ap.parse_args()

    docs = load_entries()
    if not docs:
        print("config/watchlist.yaml 里没有 manual 条目")
        return 0
    conn = sqlite3.connect(DB_PATH)
    try:
        S.ensure_schema(conn)
        for doc in docs:
            action, pk, written, tier, sid = ingest(conn, doc, args.dry_run)
            print(f"{'🧪 干跑' if args.dry_run else '✅ 已写入'} {doc['model_id']}: "
                  f"{action} (pk={pk}), tier={tier}, 自报指标 {written} 条, snapshot={sid}")
        if args.dry_run:
            conn.rollback()
            print("\n未写库。加 --no-dry-run 实际登记。")
        else:
            conn.commit()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
