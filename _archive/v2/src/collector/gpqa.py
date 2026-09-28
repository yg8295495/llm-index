"""GPQA collector — Dataset 类采集器

数据源: https://github.com/idavidrein/gpqa
  - GPQA 没有"集中维护的多模型成绩表"
  - baseline_results/ 仅有 GPT-4/LLaMA 等早期模型
  - 最新模型分数来自各团队自测自报 (模型发布报告)
  - 当前使用静态快照方式

采集目标:
  - 模型名
  - Diamond / Main / Extended 子集分数
  - 评测方法 (zero-shot / few-shot / CoT)

TODO: 后续可从 Artificial Analysis 或 Open LLM Leaderboard 获取聚合数据
"""

from datetime import date
from typing import List

from rich.console import Console

from .base import BaseCollector
from .output import Observation

console = Console()

# 2026-06 快照数据
# 来源: 各模型官方发布报告 + Artificial Analysis 聚合
# GPQA Diamond 是最常用的子集 (198 题)
SNAPSHOT_DATA = [
    # Top-tier models
    {"model": "o3", "diamond": 79.7, "method": "CoT"},
    {"model": "o4-mini", "diamond": 77.2, "method": "CoT"},
    {"model": "gemini-2.5-pro", "diamond": 78.9, "method": "CoT"},
    {"model": "claude-opus-4", "diamond": 74.2, "method": "CoT"},
    {"model": "deepseek-r1", "diamond": 71.5, "method": "CoT"},
    {"model": "gpt-4o", "diamond": 53.6, "method": "zero-shot"},
    {"model": "claude-sonnet-4", "diamond": 67.1, "method": "CoT"},
    {"model": "gemini-2.5-flash", "diamond": 65.1, "method": "CoT"},
    {"model": "qwen3-235b-a22b", "diamond": 62.6, "method": "CoT"},
    {"model": "grok-3", "diamond": 67.4, "method": "CoT"},
    {"model": "llama-4-maverick", "diamond": 52.3, "method": "few-shot"},
    # Earlier models
    {"model": "gpt-4-turbo", "diamond": 46.5, "method": "few-shot"},
    {"model": "claude-3.5-sonnet", "diamond": 59.4, "method": "CoT"},
    {"model": "gemini-1.5-pro", "diamond": 51.1, "method": "few-shot"},
    {"model": "llama-3.1-405b", "diamond": 50.7, "method": "few-shot"},
    {"model": "deepseek-v3", "diamond": 59.1, "method": "CoT"},
    {"model": "mistral-large", "diamond": 44.8, "method": "few-shot"},
]


class GPQACollector(BaseCollector):
    """GPQA Dataset 采集器"""

    def collect(self) -> List[Observation]:
        obs_date = date(2025, 6, 1)  # 快照日期
        observations: List[Observation] = []

        for entry in SNAPSHOT_DATA:
            obs = Observation(
                model=entry["model"],
                benchmark="gpqa/diamond",
                score=entry["diamond"],
                source="gpqa_official_reports",
                confidence=self.default_confidence,
                date=obs_date,
                freshness="manual",
                extra={
                    "method": entry["method"],
                    "snapshot": True,
                },
            )
            observations.append(obs)

        console.print(
            f"[green]✓ GPQA: {len(observations)} observations (snapshot)[/green]"
        )
        return observations
