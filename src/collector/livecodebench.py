"""LiveCodeBench collector — 官方 Leaderboard 采集器

数据源: https://livecodebench.github.io/leaderboard.html
  - 网页通过 JS 从 performances_generation.json 加载数据并聚合
  - JSON 文件较大且下载不稳定,当前使用静态快照方式

采集目标:
  - 模型名
  - Pass@1 分数
  - Easy/Medium/Hard 分项分数
  - 排名

TODO: 后续接入 GitHub API 自动获取 LiveCodeBench 仓库的评测结果
"""

from datetime import date
from typing import List

from rich.console import Console

from .base import BaseCollector
from .output import Observation

console = Console()

# 2026-06-15 快照数据 (来源: livecodebench.github.io/leaderboard.html)
# 时间窗口: 8/1/2024 - 5/1/2025, 454 problems
SNAPSHOT_DATA = [
    {"rank": 1, "model": "O4-Mini (High)", "pass_at_1": 80.2, "easy": 99.1, "medium": 89.4, "hard": 63.5},
    {"rank": 2, "model": "O3 (High)", "pass_at_1": 75.8, "easy": 99.1, "medium": 84.4, "hard": 57.1},
    {"rank": 3, "model": "O4-Mini (Medium)", "pass_at_1": 74.2, "easy": 98.2, "medium": 86.5, "hard": 52.7},
    {"rank": 4, "model": "Gemini-2.5-Pro-06-05", "pass_at_1": 73.6, "easy": 99.1, "medium": 87.2, "hard": 50.2},
    {"rank": 5, "model": "DeepSeek-R1-0528", "pass_at_1": 73.1, "easy": 98.7, "medium": 85.2, "hard": 50.7},
    {"rank": 6, "model": "Gemini-2.5-Pro-05-06", "pass_at_1": 71.8, "easy": 98.2, "medium": 82.3, "hard": 50.2},
    {"rank": 7, "model": "EXAONE-4.0-32B", "pass_at_1": 70.0, "easy": 98.4, "medium": 82.3, "hard": 46.2},
    {"rank": 8, "model": "OpenReasoning-Nemotron-32B", "pass_at_1": 69.8, "easy": 98.3, "medium": 81.4, "hard": 46.3},
    {"rank": 9, "model": "O3-Mini-2025-01-31 (High)", "pass_at_1": 67.4, "easy": 99.1, "medium": 84.4, "hard": 38.4},
    {"rank": 10, "model": "OpenCodeReasoning-Nemotron-1.1-32B", "pass_at_1": 66.8, "easy": 97.9, "medium": 79.6, "hard": 41.1},
    {"rank": 11, "model": "Grok-3-Mini (High)", "pass_at_1": 66.7, "easy": 97.3, "medium": 74.5, "hard": 44.8},
    {"rank": 12, "model": "O4-Mini (Low)", "pass_at_1": 65.9, "easy": 98.2, "medium": 80.1, "hard": 38.4},
    {"rank": 13, "model": "Qwen3-235B-A22B", "pass_at_1": 65.9, "easy": 99.1, "medium": 80.1, "hard": 37.9},
    {"rank": 14, "model": "XBai-o4-medium", "pass_at_1": 65.0, "easy": 98.2, "medium": 82.3, "hard": 35.0},
    {"rank": 15, "model": "O3-Mini-2025-01-31 (Med)", "pass_at_1": 63.0, "easy": 99.1, "medium": 80.1, "hard": 31.5},
    {"rank": 16, "model": "Gemini-2.5-Flash-05-20", "pass_at_1": 61.9, "easy": 99.1, "medium": 71.6, "hard": 35.0},
    {"rank": 17, "model": "Gemini-2.5-Flash-04-17", "pass_at_1": 60.6, "easy": 99.1, "medium": 70.2, "hard": 33.0},
    {"rank": 18, "model": "O3-Mini-2025-01-31 (Low)", "pass_at_1": 57.0, "easy": 99.1, "medium": 68.8, "hard": 26.1},
    {"rank": 19, "model": "Claude-Opus-4 (Thinking)", "pass_at_1": 56.6, "easy": 98.2, "medium": 70.9, "hard": 24.1},
    {"rank": 20, "model": "Claude-Sonnet-4 (Thinking)", "pass_at_1": 55.9, "easy": 97.3, "medium": 66.0, "hard": 26.6},
    {"rank": 21, "model": "Claude-Sonnet-4", "pass_at_1": 47.1, "easy": 96.4, "medium": 53.9, "hard": 15.8},
    {"rank": 22, "model": "Claude-Opus-4", "pass_at_1": 46.9, "easy": 94.5, "medium": 52.5, "hard": 17.2},
    {"rank": 23, "model": "Claude-3.5-Sonnet-20241022", "pass_at_1": 36.4, "easy": 91.2, "medium": 34.3, "hard": 8.2},
    {"rank": 24, "model": "GPT-4O-2024-08-06", "pass_at_1": 29.5, "easy": 82.5, "medium": 26.0, "hard": 3.3},
    {"rank": 25, "model": "GPT-4-Turbo-2024-04-09", "pass_at_1": 28.7, "easy": 81.0, "medium": 24.8, "hard": 3.1},
    {"rank": 26, "model": "GPT-4O-mini-2024-07-18", "pass_at_1": 27.5, "easy": 81.9, "medium": 18.9, "hard": 3.9},
    {"rank": 27, "model": "DeepSeek-V3", "pass_at_1": 27.2, "easy": 64.3, "medium": 27.9, "hard": 6.7},
    {"rank": 28, "model": "Claude-3-Haiku", "pass_at_1": 20.2, "easy": 62.3, "medium": 12.6, "hard": 2.8},
]


class LiveCodeBenchCollector(BaseCollector):
    """LiveCodeBench 官方 Leaderboard 采集器"""

    def collect(self) -> List[Observation]:
        obs_date = date(2025, 5, 1)  # 快照时间窗口结束日期
        observations: List[Observation] = []

        for entry in SNAPSHOT_DATA:
            obs = Observation(
                model=entry["model"],
                benchmark="livecodebench/pass_at_1",
                score=entry["pass_at_1"],
                source="livecodebench.github.io",
                confidence=self.default_confidence,
                date=obs_date,
                freshness="snapshot",
                extra={
                    "rank": entry["rank"],
                    "easy": entry["easy"],
                    "medium": entry["medium"],
                    "hard": entry["hard"],
                    "snapshot": True,
                },
            )
            observations.append(obs)

        console.print(
            f"[green]✓ LiveCodeBench: {len(observations)} observations (snapshot)[/green]"
        )
        return observations
