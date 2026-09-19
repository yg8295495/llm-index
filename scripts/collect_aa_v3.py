#!/usr/bin/env python3
"""AA Omniscience 采集器 v3 — 快照式、可反复跑、不覆盖历史

用法:
    python3 scripts/collect_aa_v3.py                 # 干跑, 只看将要写什么
    python3 scripts/collect_aa_v3.py --no-dry-run    # 实际写入 SQLite
    python3 scripts/collect_aa_v3.py --from-file /tmp/aa.html   # 离线复现

为什么有 v3 (详见 docs/changelog.md #1 #2 #3 #4 #12):
    v2 依赖的 `defaultData` chunk 已被 AA 移除, 采集于 2026-08 后彻底失效;
    它的 --force-refresh 会 DELETE 掉该模型全部历史评测; 它把跑批日期写进
    observed_at 冒充观测日期; 它靠 slug 前缀猜厂商, 猜不到就写 unknown。
    v3 改为: AA 注册表权威归属 + 快照追加 + 行级 source_url + 页面指纹留档。

范围: 只采 config/vendors.yaml 中 tier in (core, reference) 的厂商,
      core 进综合榜, reference 存档并标 needs_manual_review。
"""

from __future__ import annotations

import argparse
import gzip
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.collector import aa_omniscience as AA          # noqa: E402
from src.collector import mapping as M                  # noqa: E402
from src.paths import (                                 # noqa: E402
    DB_PATH, REPORTS_DIR, SNAPSHOT_DIR, config_path,
)
from src.storage import snapshot_store as S            # noqa: E402

TOOL = "collect_aa_v3"

# 快照日取受众所在时区而不是 UTC: 2026-09-20 这次抓取发生在 UTC 19:55,
# 若直接用 UTC 日期, 本站会把"9 月 20 日截止"的数据标成 09-19 (见 changelog #14)。
AUDIENCE_TZ = "Asia/Shanghai"


def _as_of_date(fetched_at: str) -> str:
    try:
        from zoneinfo import ZoneInfo

        dt = datetime.fromisoformat(fetched_at).astimezone(ZoneInfo(AUDIENCE_TZ))
        return dt.date().isoformat()
    except Exception:
        return fetched_at[:10]


def source_url_map(bm: dict) -> tuple[dict[str, str], list[str]]:
    """canonical benchmark key -> 来源 URL。

    数据源若自带 source_url 用它自己; 否则回退到 provenance.leaderboard_url
    (这批数值确实就是从那一页读来的, 回退成立), 并把回退名单报出来供人工核对,
    不做静默兜底。落实"无 source_url 不存储"。
    """
    prov = bm.get("provenance") or {}
    page_url = prov.get("leaderboard_url")
    out: dict[str, str] = {}
    fallback: list[str] = []
    for dim in (bm.get("dimensions") or {}).values():
        for key, src in (dim.get("sources") or {}).items():
            url = src.get("source_url")
            if url:
                out[key] = url
            elif page_url:
                out[key] = page_url
                fallback.append(key)
    return out, fallback


def write_snapshot_files(date_str: str, page: AA.RawPage, parsed: dict, bm: dict) -> Path:
    d = SNAPSHOT_DIR / date_str
    d.mkdir(parents=True, exist_ok=True)
    (d / "omniscience.html.gz").write_bytes(
        gzip.compress(page.html.encode("utf-8", "replace"), compresslevel=6)
    )
    (d / "scored_models.json").write_text(
        json.dumps(parsed["scored_models"], ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (d / "registry.json").write_text(
        json.dumps(parsed["registry"], ensure_ascii=False), encoding="utf-8"
    )
    manifest = {
        "snapshot_date": date_str,
        "tool": TOOL,
        "source": parsed["source"],
        "counts": parsed["counts"],
        "config": {
            "vendors": config_path("vendors.yaml").name,
            "benchmarks": config_path("benchmarks.yaml").name,
            "benchmarks_version": (bm.get("meta") or {}).get("version"),
        },
    }
    (d / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return d


def render_report(date_str: str, page, parsed, mapped, stats, report: S.WriteReport,
                  schema_changes, legacy, url_fallback, dry: bool) -> str:
    lines = [
        f"# Collection Report — AA Omniscience {date_str}",
        "",
        f"- 工具: `{TOOL}`  模式: {'DRY RUN (未写库)' if dry else '已写入'}",
        f"- 来源: {page.url}",
        f"- 抓取时刻: {page.fetched_at}  HTTP {page.http_status}  {page.bytes:,} B",
        f"- 页面指纹 sha256: `{page.sha256}`",
        f"- RSC 分片数: {parsed['source']['rsc_chunks']}",
        f"- 解析: 带分模型 {parsed['counts']['scored']} / 注册表 {parsed['counts']['registry']}",
        "",
        "## 范围与归属",
        f"- 入库模型: core {stats['by_tier'].get('core', 0)}"
        f" + reference {stats['by_tier'].get('reference', 0)}"
        f" + unclassified {stats['by_tier'].get('unclassified', 0)}"
        f"; 范围外排除 {stats['excluded']}",
        f"- 评测行: 写 {report.evals_written}, 已存在跳过 {report.evals_skipped_existing},"
        f" 因缺 source_url 拒绝 {len(report.rejected)}",
        f"- 新建模型行 {report.models_new} / 更新既有行 {report.models_updated}",
        "",
        "## 需要人工确认 (needs_manual_review)",
    ]
    for r in report.renames:
        lines.append(f"- ID 规范化: `{r['from']}` → `{r['to']}` (aa_slug={r['aa_slug']})")
    for r in report.provider_fixes:
        lines.append(f"- provider 更正: `{r['model_id']}` {r['from']} → {r['to']}")
    for c in stats["collisions"]:
        lines.append(f"- ⚠️ 身份冲突: {c['key']} 由 {c['aa_slugs']} 同时解析, 已中止")
    for m in mapped:
        if m.row.tier == "unclassified":
            lines.append(f"- ⚠️ 未归类厂商: `{m.row.aa_slug}` → {m.row.notes}")
    if not (report.renames or report.provider_fixes or stats["collisions"]):
        lines.append("- 无")
    lines += ["", "## Schema", ]
    for ch in schema_changes:
        lines.append(f"- 新增列 {ch}")
    for lg in legacy:
        lines.append(f"- 回填历史快照 {lg['date']}: {lg['models']} 模型 / {lg['evals']} 评测行")
    if not schema_changes and not legacy:
        lines.append("- 无变更")
    lines += ["", "## 来源 URL 口径"]
    if url_fallback:
        lines.append(
            f"- 以下 {len(url_fallback)} 个数据源在 config/benchmarks.yaml 未写独立 source_url, "
            "统一回退为 AA omniscience 页面 URL (本批次数值的确切出处):\n  "
            + ", ".join(f"`{k}`" for k in sorted(url_fallback))
        )
    else:
        lines.append("- 全部数据源均有独立 source_url")
    lines += ["", "## 模型明细", "", "| tier | model_id | 档位 | 发布 | 评测数 |", "|---|---|---|---|---|"]
    for m in sorted(mapped, key=lambda x: (x.row.tier, x.row.model_id, x.row.reasoning_level)):
        lines.append(
            f"| {m.row.tier} | `{m.row.model_id}` | {m.row.reasoning_level or '—'} "
            f"| {m.row.release_date or '—'} | {len(m.evals)} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="AA Omniscience 采集器 v3 (快照追加)")
    ap.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                    help="实际写入数据库 (默认干跑)")
    ap.add_argument("--snapshot-date", default=None,
                    help="快照日 YYYY-MM-DD, 默认取抓取当天 UTC")
    ap.add_argument("--from-file", default=None, help="离线模式: 读本地 HTML, 不发网络请求")
    ap.add_argument("--allow-collisions", action="store_true",
                    help="即使 model_id 身份冲突也继续 (默认中止)")
    ap.set_defaults(dry_run=True)
    args = ap.parse_args()

    print("🌐 抓取 AA omniscience 页面 ...")
    try:
        if args.from_file:
            html = Path(args.from_file).read_text(encoding="utf-8", errors="replace")
            page = AA.RawPage(
                url=f"file://{args.from_file}", http_status=0, html=html,
                fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            print(f"   离线模式: {page.bytes:,} B sha256={page.sha256[:12]}…")
        else:
            page = AA.fetch_page()
            print(f"   HTTP {page.http_status} · {page.bytes:,} B · sha256={page.sha256[:12]}…")
        parsed = AA.parse_page(page)
    except AA.PayloadError as exc:
        print(f"❌ 采集失败: {exc}", file=sys.stderr)
        return 2
    print(f"   带分模型 {parsed['counts']['scored']} · 注册表 {parsed['counts']['registry']}")

    date_str = args.snapshot_date or _as_of_date(page.fetched_at)
    bm = M.load_benchmarks()
    vendors = M.load_vendors()
    urls, url_fallback = source_url_map(bm)

    conn = sqlite3.connect(DB_PATH)
    try:
        changes = S.ensure_schema(conn)
        legacy = S.backfill_legacy_snapshots(conn)
        by_slug, by_base = S.load_identity_index(conn)
        mapped, stats = M.map_records(
            parsed["scored_models"], parsed["registry"], bm, vendors, by_slug, by_base
        )
        print(f"   范围: core {stats['by_tier'].get('core', 0)} · "
              f"reference {stats['by_tier'].get('reference', 0)} · "
              f"unclassified {stats['by_tier'].get('unclassified', 0)} · 排除 {stats['excluded']}")
        if stats["collisions"] and not args.allow_collisions:
            print("❌ 检测到 model_id 身份冲突, 已中止 (未写库):", file=sys.stderr)
            for c in stats["collisions"]:
                print(f"   {c}", file=sys.stderr)
            conn.rollback()
            return 3

        snap_dir = write_snapshot_files(date_str, page, parsed, bm)
        print(f"   快照落盘: {snap_dir}")
        sid = S.upsert_snapshot(conn, date_str, {
            "source": "artificial_analysis",
            "source_url": page.url,
            "fetched_at": page.fetched_at,
            "html_sha256": page.sha256,
            "html_bytes": page.bytes,
            "parsed_path": str(snap_dir.relative_to(snap_dir.parents[2])),
            "notes": f"{TOOL}; RSC chunks={parsed['source']['rsc_chunks']}",
        })
        report = S.write(conn, mapped, sid, date_str, urls, dry_run=args.dry_run)
        print(f"\n{'🧪 DRY RUN — 未写库' if args.dry_run else '✅ 已写入'}")
        print(f"   模型行: 新建 {report.models_new} / 更新 {report.models_updated}")
        print(f"   评测行: {report.evals_written} (跳过已存在 {report.evals_skipped_existing},"
              f" 拒绝 {len(report.rejected)})")
        print(f"   ID 规范化 {len(report.renames)} · provider 更正 {len(report.provider_fixes)}")
        if args.dry_run:
            conn.rollback()
        else:
            # 回填快照计数: 版本轨迹要能自查"这一批进了多少东西"。
            # 必须按库内该快照的实际行数统计 —— 用"本次新写入数"会在幂等重跑时
            # 把已经正确的数覆盖成 0 (2026-09-20 首次踩到, 见 changelog #30)。
            conn.execute(
                """UPDATE snapshots SET
                       model_count = (SELECT COUNT(DISTINCT model_pk) FROM benchmark_evals
                                      WHERE snapshot_id = ?),
                       eval_count  = (SELECT COUNT(*) FROM benchmark_evals
                                      WHERE snapshot_id = ?)
                   WHERE id = ?""",
                (sid, sid, sid),
            )
            conn.commit()
    finally:
        conn.close()

    REPORTS_DIR.mkdir(exist_ok=True)
    txt = render_report(date_str, page, parsed, mapped, stats, report, changes, legacy,
                        url_fallback, args.dry_run)
    out = REPORTS_DIR / f"collection_{date_str}.md"
    out.write_text(txt, encoding="utf-8")
    print(f"   报告: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
