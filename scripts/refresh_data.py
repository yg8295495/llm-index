#!/usr/bin/env python3
"""一条命令跑完整条更新流程: 采集 → 入库 → 导出 → 校验

    python3 scripts/refresh_data.py                # 干跑全流程 (不写库、不覆盖 data.json)
    python3 scripts/refresh_data.py --apply        # 实际采集入库并导出
    python3 scripts/refresh_data.py --apply --snapshot-date 2026-10-05

存在的意义: 之前"更新一次数据"要按顺序手敲 3-4 条脚本, 且 README 里写的还是
已被淘汰的 extract→ingest→export 三步 (见 docs/changelog.md #20)。
本脚本把顺序固定下来, 并在导出后自动跑一遍契约测试, 不干净就报错退出。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], label: str) -> int:
    print(f"\n{'=' * 66}\n▶ {label}\n  $ {' '.join(cmd)}\n{'=' * 66}")
    return subprocess.call(cmd, cwd=ROOT)


def main() -> int:
    ap = argparse.ArgumentParser(description="数据刷新编排 (采集→入库→导出→校验)")
    ap.add_argument("--apply", action="store_true", help="实际写库并覆盖 frontend/data.json")
    ap.add_argument("--snapshot-date", default=None, help="指定快照日 YYYY-MM-DD")
    ap.add_argument("--from-file", default=None, help="离线模式: 用本地 HTML 复现解析")
    args = ap.parse_args()

    py = sys.executable
    collect = [py, "scripts/collect_aa_v3.py"]
    if args.apply:
        collect.append("--no-dry-run")
    if args.snapshot_date:
        collect += ["--snapshot-date", args.snapshot_date]
    if args.from_file:
        collect += ["--from-file", args.from_file]

    steps = [("采集并入库 (AA Omniscience)", collect)]
    if args.apply:
        steps.append(("导出 frontend/data.json", [py, "scripts/export_frontend_data.py"]))
    else:
        steps.append(("试导出到 /tmp", [py, "scripts/export_frontend_data.py",
                                       "--out", "/tmp/data_dryrun.json"]))
    steps.append(("契约测试 (data.json 形状 / 溯源完整性)",
                  [py, "-m", "pytest", "-q", "tests/test_export.py", "tests/test_collector_v3.py"]))

    for label, cmd in steps:
        rc = run(cmd, label)
        if rc != 0:
            print(f"\n❌ 步骤失败 (rc={rc}): {label}", file=sys.stderr)
            print("   流程中止, 不要发布。", file=sys.stderr)
            return rc

    print("\n✅ 全流程通过。")
    if args.apply:
        print("   下一步: 人工过目 frontend/data.json 与 reports/collection_*.md,")
        print("   确认后再 commit + push 发布到 GitHub Pages。")
    else:
        print("   这是干跑。确认无误后加 --apply 实际写入。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
