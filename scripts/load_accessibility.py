"""加载 accessibility 数据到 DB

从 config/accessibility.yaml 读取,按 provider 字段匹配模型,
生成 Observation 写入数据库。

用法: python3 scripts/load_accessibility.py
"""

import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from rich.console import Console

from src.collector.output import Observation

console = Console()

YAML_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "accessibility.yaml")

# 子指标权重
W_DIRECT = 0.5
W_RISK = 0.3
W_STABILITY = 0.2


def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    # 1. 读取 YAML
    data = load_yaml(YAML_PATH)
    providers = data.get("providers", {})
    console.print(f"[blue]读取 {len(providers)} 个 provider 配置[/blue]")

    # 2. 从 DB 拿所有模型, 按 provider 分组
    from src.storage.db_manager import DatabaseManager

    db = DatabaseManager()
    all_models = db.list_models()
    console.print(f"[blue]DB 中有 {len(all_models)} 个模型[/blue]")

    # 按 provider 分组
    by_provider = {}
    for m in all_models:
        by_provider.setdefault(m.provider, []).append(m.id)

    # 3. 生成 Observations
    today = date.today()
    observations = []

    for provider_key, cfg in providers.items():
        pk = cfg.get("provider_key", "")
        matched_ids = by_provider.get(pk, [])
        if not matched_ids:
            console.print(f"[yellow]⚠ {provider_key} (pk={pk}): 无匹配模型, 跳过[/yellow]")
            continue

        direct = cfg.get("direct_access", -1)
        risk = cfg.get("account_risk", -1)
        stable = cfg.get("stability", -1)

        # 加权总分 (仅当所有子指标都有值)
        if all(v >= 0 for v in [direct, risk, stable]):
            composite = round(direct * W_DIRECT + risk * W_RISK + stable * W_STABILITY, 1)
        else:
            composite = -1

        for mid in matched_ids:
            for sub_key, raw_score in [
                ("direct_access", direct),
                ("account_risk", risk),
                ("stability", stable),
                ("composite", composite),
            ]:
                if raw_score < 0:
                    continue
                observations.append(
                    Observation(
                        model=mid,
                        benchmark=f"accessibility/{sub_key}",
                        score=float(raw_score),
                        source="manual_assessment",
                        confidence=0.7,
                        date=today,
                        extra={"provider": provider_key, "note": cfg.get("note", "")},
                    )
                )

    console.print(f"[green]✓ 生成 {len(observations)} 条 Observation, 覆盖 {len(set(o.model for o in observations))} 个模型[/green]")

    # 4. 写入 DB
    db_rows = [o.to_db_dict() for o in observations]
    db.save_observations(db_rows)
    console.print(f"[green]✓ 写入 {len(db_rows)} 条 observation[/green]")

    # 5. 验证
    saved = db.get_observations(limit=5)
    console.print(f"[green]✓ 回读 {len(saved)} 条 [/green]")

    # 6. 按 provider 统计
    console.print("\n[bold]=== 覆盖统计 ===[/bold]")
    from collections import Counter

    model_count = Counter()
    for obs in observations:
        if obs.benchmark == "accessibility/composite":
            model_count[obs.model] = obs.score

    console.print(f"composite 覆盖: {len(model_count)} 个模型")
    for mid, score in sorted(model_count.items(), key=lambda x: -x[1]):
        console.print(f"  {mid:40s} accessibility={score}")

    console.print("\n[bold green]✅ 完成![/bold green]")


if __name__ == "__main__":
    main()