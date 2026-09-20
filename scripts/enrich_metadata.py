#!/usr/bin/env python3
"""元数据补采 — 从 AA 单模型详情页回填"分数之外"的选型属性

用法:
    python3 scripts/enrich_metadata.py                    # 干跑, 打印将回填什么
    python3 scripts/enrich_metadata.py --apply            # 写入最新快照的带分行
    python3 scripts/enrich_metadata.py --apply --slugs kimi-k3,qwen3-8-flash-next

为什么单独一个脚本 (changelog #37):
    AA 的**榜单页 payload 里根本没有 contextWindow\\*** —— 上下文窗口只出现在
    单模型详情页 (`contextWindowTokens`), 而 v3 主采集只解析榜单页, 于是
    2026-09-20 批次 30 个带分模型的 context_window 全是 NULL。同理
    `intelligenceIndexTimePerTask` (单任务耗时) 也只有详情页有, 而这个数对
    "夜里 7 小时能跑多少个因子实验" 是一等输入。
    详情页一页 3.9MB, 31 个模型全拉约 120MB, 因此默认只处理最新快照里带分的模型,
    并且可以 --slugs 缩小范围。

口径: 元数据只 UPDATE models 表已有行, 不新建评测、不动 snapshot_id;
      每个模型的来源 URL + 页面指纹写进 data/reports/enrich_metadata_*.json。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.collector import aa_omniscience as AA          # noqa: E402
from src.collector import mapping as M                  # noqa: E402
from src.paths import DB_PATH, REPORTS_DIR              # noqa: E402
from src.storage import snapshot_store as S             # noqa: E402

TOOL = "enrich_metadata"
META_COLUMNS = (
    "context_window", "parameters", "active_params", "pricing_input", "pricing_output",
    "pricing_cache_input", "answer_speed", "time_per_task_s", "openness_index",
    "size_class", "open_source", "supports_vision", "supports_audio",
)


def targets(conn: sqlite3.Connection, slugs: list[str] | None, only_missing: bool = True
            ) -> list[tuple[int, str, str]]:
    """最新快照里带独立评测的行: (models.id, aa_slug, model_id)

    默认只取"还缺上下文窗口或单任务耗时"的行 —— 一页详情页 3.9MB, 全量重拉一遍
    要 130MB, 而这些列都是模型级常量, 补过就不必再补。--all 才强制重拉。
    """
    sid = conn.execute("SELECT MAX(id) FROM snapshots").fetchone()[0]
    if sid is None:
        raise SystemExit("数据库里没有快照, 先跑 collect_aa_v3.py")
    having = ""
    if only_missing:
        # 按 model_id 判断"这个模型已经补过了" —— 同一模型的多个档位行里,
        # 只要有一行同时有上下文窗口和单任务耗时, 就不必再拉 3.9MB 的详情页。
        having = """AND NOT EXISTS (
                       SELECT 1 FROM models s
                       WHERE s.model_id = m.model_id
                         AND s.context_window IS NOT NULL
                         AND s.time_per_task_s IS NOT NULL)"""
    rows = conn.execute(
        f"""SELECT DISTINCT m.id, m.aa_slug, m.model_id
            FROM benchmark_evals be JOIN models m ON be.model_pk = m.id
            WHERE be.snapshot_id = ? AND m.aa_slug IS NOT NULL AND m.aa_slug != ''
              AND be.benchmark NOT LIKE '%_official' AND be.source LIKE 'artificial%'
              {having}
            ORDER BY m.model_id""",
        (sid,),
    ).fetchall()
    out = [(int(r[0]), r[1], r[2]) for r in rows]
    if slugs:
        wanted = set(slugs)
        out = [t for t in out if t[1] in wanted]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="AA 详情页元数据补采")
    ap.add_argument("--apply", action="store_true", help="实际写入 (默认干跑)")
    ap.add_argument("--slugs", default=None, help="逗号分隔的 aa_slug 白名单, 默认全部带分模型")
    ap.add_argument("--all", dest="only_missing", action="store_false",
                    help="强制重拉所有带分模型的详情页 (默认只拉还缺元数据的)")
    ap.add_argument("--sleep", type=float, default=1.0, help="相邻请求间隔秒数")
    ap.add_argument("--db", default=None, help="覆盖数据库路径 (测试用)")
    args = ap.parse_args()

    db_path = args.db or DB_PATH
    conn = sqlite3.connect(db_path)
    S.ensure_schema(conn)
    slugs = [s.strip() for s in args.slugs.split(",")] if args.slugs else None
    rows = targets(conn, slugs, only_missing=args.only_missing)
    print(f"目标 {len(rows)} 个带分模型 (快照 {conn.execute('SELECT MAX(id) FROM snapshots').fetchone()[0]})")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report, changed_rows, failures = [], 0, []
    for pk, slug, model_id in rows:
        try:
            page = AA.fetch_model_page(slug)
            rec = AA.find_scored_record(page, slug)
        except Exception as exc:                      # 网络/结构变化都要显式记下来
            failures.append({"aa_slug": slug, "error": f"{type(exc).__name__}: {exc}"})
            print(f"   ✗ {slug}: {type(exc).__name__} {exc}")
            continue
        meta = M.model_metadata(rec)
        before = conn.execute(
            f"SELECT {', '.join(META_COLUMNS)} FROM models WHERE id = ?", (pk,)
        ).fetchone()
        updates = {
            col: meta[col] for col in META_COLUMNS
            if meta[col] is not None and (before is None or before[META_COLUMNS.index(col)] is None)
        }
        report.append({
            "models_id": pk, "model_id": model_id, "aa_slug": slug,
            "source_url": page.url, "html_sha256": page.sha256, "bytes": page.bytes,
            "fetched_at": now, "would_set": updates,
            "already_had": {c: b for c, b in zip(META_COLUMNS, before or ()) if b is not None},
        })
        if updates:
            changed_rows += 1
            print(f"   ✓ {slug:<24} 回填 {', '.join(f'{k}={v}' for k, v in updates.items())}"
                  if args.apply else
                  f"   · {slug:<24} 待回填 {', '.join(f'{k}={v}' for k, v in updates.items())}")
        else:
            print(f"   – {slug:<24} 无缺失字段" if before else f"   · {slug:<24} 详情页也无这些字段")
        if args.apply and updates:
            assignments = ", ".join(f"{k} = :{k}" for k in updates)
            conn.execute(
                f"UPDATE models SET {assignments}, updated_at = :__now WHERE id = :__pk",
                {**updates, "__now": now, "__pk": pk},
            )
        time.sleep(args.sleep)

    if args.apply:
        conn.commit()
    # 报告按**批次日**命名并合并历史: 同一天多次重跑 (失败重试) 不该互相覆盖,
    # 也不该每次都产生一个新文件把仓库刷脏。
    batch = conn.execute("SELECT snapshot_date FROM snapshots WHERE id = (SELECT MAX(id) FROM snapshots)").fetchone()[0]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"enrich_metadata_{str(batch)[:10]}.json"
    prior: dict = {}
    if out.exists():
        try:
            prior = json.loads(out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prior = {}
    merged = {r["aa_slug"]: r for r in (prior.get("models") or [])}
    merged.update({r["aa_slug"]: r for r in report})
    runs = (prior.get("runs") or []) + [{
        "generated_at": now, "dry_run": not args.apply,
        "targets": len(rows), "rows_changed": changed_rows,
        "failures": [f["aa_slug"] for f in failures]}]
    out.write_text(json.dumps(
        {"tool": TOOL, "batch_snapshot_date": str(batch)[:10],
         "generated_at": now, "dry_run": not args.apply,
         "targets": len(rows), "rows_changed": changed_rows,
         "failures": failures, "runs": runs[-12:],
         "models": [merged[k] for k in sorted(merged)]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    conn.close()
    print(f"{'已写入' if args.apply else '干跑, 未写入'}: {changed_rows}/{len(rows)} 行需要回填, "
          f"{len(failures)} 个模型页抓取失败")
    print(f"报告: {out}")
    if failures:
        print("   ⚠️ 失败清单: " + ", ".join(f["aa_slug"] for f in failures))
        print("   多为 curl rc=35 (TLS 握手抖动), 重跑本脚本即可 —— 它只补 NULL, 不会覆盖已有值")
    # 部分失败不该让整条日更中断 (缺的只是上下文窗口这类元数据, 榜面数值不受影响);
    # 但只要"有目标且全部抓取失败"说明 AA 或网络整体不可用, 必须让 refresh_data.py 停下来。
    # 注意 0 改动 + 0 失败 = 早就补过了, 这是正常收敛状态, 不是错误。
    return 1 if rows and len(failures) == len(rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
