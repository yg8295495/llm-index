"""最小化验证: OpenRouter benchmarks 数据采集

只做 3 件事:
1. 调 OpenRouter API 拿 benchmarks
2. 转成 Observation
3. 入库 + 打印覆盖率

不铺新文件,不改模块。
"""

import sys
import os
from datetime import date

# 让项目 import 可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from rich.console import Console
from rich.table import Table

from src.collector.output import Observation

console = Console()


def main():
    URL = "https://openrouter.ai/api/v1/models"

    # 1. fetch
    console.print(f"[blue]调用 {URL} ...[/blue]")
    resp = httpx.get(URL, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    all_models = payload.get("data", [])
    console.print(f"[green]✓ 收到 {len(all_models)} 个模型[/green]")

    # 2. 解析 benchmarks
    observations = []

    for m in all_models:
        model_id = m.get("id", "")
        if not model_id:
            continue

        bench_data = m.get("benchmarks")
        if not bench_data:
            continue

        # 2a. artificial_analysis → 3 个 benchmark
        aa = bench_data.get("artificial_analysis")
        if isinstance(aa, dict):
            for key, score in aa.items():
                if not isinstance(score, (int, float)):
                    continue
                observations.append(
                    Observation(
                        model=model_id,
                        benchmark=f"artificial_analysis/{key}",
                        score=float(score),
                        source="openrouter/artificial_analysis",
                        confidence=0.8,  # 聚合指数,非原始 benchmark,打 0.8
                        date=date.today(),
                    )
                )

        # 2b. design_arena → per-category benchmark
        da = bench_data.get("design_arena")
        if isinstance(da, list):
            for item in da:
                arena = item.get("arena", "")
                category = item.get("category", "")
                elo = item.get("elo")
                if elo is not None:
                    observations.append(
                        Observation(
                            model=model_id,
                            benchmark=f"design_arena/{arena}/{category}",
                            score=float(elo),
                            source="openrouter/design_arena",
                            confidence=0.8,
                            date=date.today(),
                            extra={
                                "win_rate": item.get("win_rate"),
                                "rank": item.get("rank"),
                            },
                        )
                    )

    # 3. 统计
    console.print("\n[bold]=== 覆盖率报告 ===[/bold]")

    # 按 benchmark 类型统计
    bench_counts = {}
    bench_models = {}
    for obs in observations:
        # 取一级命名空间
        ns = obs.benchmark.split("/")[0]
        bench_counts[ns] = bench_counts.get(ns, 0) + 1
        if ns not in bench_models:
            bench_models[ns] = set()
        bench_models[ns].add(obs.model)

    table = Table(title="Benchmark 覆盖统计")
    table.add_column("数据源", style="cyan")
    table.add_column("Observation 数", style="magenta")
    table.add_column("模型数", style="green")

    for ns in sorted(bench_counts.keys()):
        table.add_row(ns, str(bench_counts[ns]), str(len(bench_models[ns])))
    table.add_row(
        "[bold]合计[/bold]",
        f"[bold]{len(observations)}[/bold]",
        f"[bold]{len(set(o.model for o in observations))}[/bold]",
    )
    console.print(table)

    # 4. 按人工智分类统计细项
    console.print("\n[bold]artificial_analysis 细项覆盖[/bold]")
    keys = ["intelligence_index", "coding_index", "agentic_index"]
    for k in keys:
        cnt = sum(1 for o in observations if o.benchmark == f"artificial_analysis/{k}")
        console.print(f"  {k}: {cnt} 个模型")

    # 5. 样条
    console.print("\n[bold]样本: claude-fable-5[/bold]")
    for o in observations:
        if "claude-fable-5" in o.model:
            console.print(f"  {o.benchmark:45s} score={o.score:>8}  confidence={o.confidence}")

    console.print("\n[bold]样本: gpt-5.2-codex[/bold]")
    for o in observations:
        if "gpt-5.2-codex" in o.model:
            console.print(f"  {o.benchmark:45s} score={o.score:>8}  confidence={o.confidence}")

    # 6. 入库(仅数据,不铺新表)
    console.print("\n[blue]尝试写入 DB ...[/blue]")
    from src.storage.db_manager import DatabaseManager
    from src.storage.models import Base

    db = DatabaseManager()
    Base.metadata.create_all(db.engine)
    console.print("[green]✓ 表已创建[/green]")

    # 只写 50 条做验证
    sample = observations[:50]
    # 预先 upsert model
    model_ids = set(o.model for o in sample)
    for mid in model_ids:
        db.upsert_model({
            "id": mid,
            "provider": "openrouter",
            "status": "active",
        })
    console.print(f"[green]✓ upsert {len(model_ids)} 个 model[/green]")

    # 转 DB 格式
    db_rows = [o.to_db_dict() for o in sample]
    db.save_observations(db_rows)
    console.print(f"[green]✓ 写入 {len(db_rows)} 条 observation[/green]")

    # 回读
    saved = db.get_observations(limit=10)
    console.print(f"[green]✓ 回读 {len(saved)} 条,验证通过[/green]")
    if saved:
        console.print(f"  第 1 条: model={saved[0].model_id} benchmark={saved[0].benchmark} score={saved[0].score}")

    console.print("\n[bold green]✅ 验证通过! OpenRouter benchmarks 数据链路已打通[/bold green]")

    return observations


if __name__ == "__main__":
    main()