"""LMArena (Chatbot Arena) Elo 排名采集器

数据源: fboulnois/llm-leaderboard-csv (GitHub)
  - 定期从 lmarena.ai 抓取 Arena Elo 排名,发布为 CSV
  - 包含 lmarena_text.csv (文本对话 Elo) / lmarena_vision.csv / lmarena_image.csv
  - Source tier: T3 (第三方转载,但数据来自官方 Arena)

采集目标:
  - 模型列表
  - Elo 分 (arena_score)
  - 排名 (rank)
  - 投票数 (votes)
  - 95% 置信区间 (95_pct_ci)
"""

import csv
import io
import subprocess
from datetime import date, datetime
from typing import List, Optional

import httpx
from rich.console import Console

from .base import BaseCollector
from .output import Observation

console = Console()

# GitHub raw CSV URL
ARENA_TEXT_CSV_URL = (
    "https://raw.githubusercontent.com/fboulnois/"
    "llm-leaderboard-csv/main/csv/lmarena_text.csv"
)
ARENA_VISION_CSV_URL = (
    "https://raw.githubusercontent.com/fboulnois/"
    "llm-leaderboard-csv/main/csv/lmarena_vision.csv"
)

# GitHub API 获取仓库最新 commit 时间
REPO_COMMITS_URL = (
    "https://api.github.com/repos/fboulnois/llm-leaderboard-csv/commits"
    "?path=csv/lmarena_text.csv&per_page=1"
)


def _fetch_url(url: str, timeout: int = 30) -> str:
    """下载 URL 内容,优先 httpx,fallback 到 curl"""
    # 1. 尝试 httpx
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            return r.text
    except (httpx.HTTPError, Exception):
        pass

    # 2. Fallback: curl (本机网络环境可能需要)
    try:
        result = subprocess.run(
            ["curl", "-sL", "--connect-timeout", "15", "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    raise RuntimeError(f"无法下载 {url} (httpx 和 curl 均失败)")


class ArenaCollector(BaseCollector):
    """LMArena Elo 排名采集器"""

    def collect(self) -> List[Observation]:
        """采集 Arena Elo 数据,返回 Observation 列表"""
        # 1. 获取数据更新时间
        obs_date = self._fetch_last_update_date() or date.today()

        # 2. 采集 text leaderboard
        text_observations = self._collect_csv(
            url=ARENA_TEXT_CSV_URL,
            benchmark_prefix="arena/elo",
            obs_date=obs_date,
        )

        # 3. 采集 vision leaderboard
        vision_observations = self._collect_csv(
            url=ARENA_VISION_CSV_URL,
            benchmark_prefix="arena/elo_vision",
            obs_date=obs_date,
        )

        all_obs = text_observations + vision_observations
        console.print(
            f"[green]✓ Arena: {len(text_observations)} text + "
            f"{len(vision_observations)} vision = {len(all_obs)} observations[/green]"
        )
        return all_obs

    def _fetch_last_update_date(self) -> Optional[date]:
        """从 GitHub API 获取 CSV 文件最后更新时间"""
        try:
            text = _fetch_url(REPO_COMMITS_URL, timeout=15)
            import json
            commits = json.loads(text)
            if commits:
                commit_date_str = commits[0]["commit"]["committer"]["date"]
                dt = datetime.fromisoformat(commit_date_str.replace("Z", "+00:00"))
                return dt.date()
        except Exception as e:
            console.print(f"[yellow]⚠ 无法获取 Arena 数据更新时间: {e}[/yellow]")
        return None

    def _collect_csv(
        self,
        url: str,
        benchmark_prefix: str,
        obs_date: date,
    ) -> List[Observation]:
        """下载并解析 CSV,返回 Observation 列表"""
        try:
            csv_text = _fetch_url(url)
        except RuntimeError as e:
            console.print(f"[red]✗ Arena CSV 下载失败: {e}[/red]")
            return []

        observations: List[Observation] = []
        reader = csv.DictReader(io.StringIO(csv_text))

        for row in reader:
            try:
                model_name = row.get("model", "").strip()
                arena_score = float(row.get("arena_score", 0))
                rank = int(row.get("rank", 0))
                votes = int(row.get("votes", 0))
                ci = row.get("95_pct_ci", "").strip()
                organization = row.get("organization", "").strip()

                if not model_name or arena_score <= 0:
                    continue

                obs = Observation(
                    model=model_name,
                    benchmark=benchmark_prefix,
                    score=arena_score,
                    source="lmarena",
                    confidence=self.default_confidence,
                    date=obs_date,
                    freshness="realtime",
                    extra={
                        "rank": rank,
                        "votes": votes,
                        "ci_95": ci,
                        "organization": organization,
                    },
                )
                observations.append(obs)

            except (ValueError, KeyError) as e:
                console.print(f"[yellow]⚠ Arena 行解析跳过: {e}[/yellow]")
                continue

        return observations
