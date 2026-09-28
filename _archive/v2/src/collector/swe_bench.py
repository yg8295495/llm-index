"""SWE-Bench collector — 官方 Leaderboard 采集器

数据源: https://www.swebench.com/index.html
  - 一个页面包含 6 个 leaderboard (Verified / Multilingual / Lite / Multimodal / Test / bash-only)
  - 数据嵌入在 <script id="leaderboard-data"> 里 (JSON)
  - 采集方式: httpx/curl 下载 HTML → 正则提取 JSON → 解析
  - Fallback: 本地 fixture (测试/离线友好)

采集目标:
  - 模型名
  - resolved 百分比 (score)
  - 评测日期
  - agent 版本
"""

import json
import re
from datetime import date as _date
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from .base import BaseCollector
from .output import Observation

console = Console()

# 各 leaderboard 在 DB 里的 benchmark key
LEADERBOARD_BENCHMARK_KEY = {
    "verified": "swebench/verified",
    "multilingual": "swebench/multilingual",
    "lite": "swebench/lite",
    "multimodal": "swebench/multimodal",
    "test": "swebench/test",
    "bash-only": "swebench/bash_only",
}

# 只采集 Verified 和 Lite (最常用,数据最全)
ACTIVE_BOARDS = {"verified", "lite"}


class SWEBenchCollector(BaseCollector):
    """SWE-Bench 官方 Leaderboard 采集器"""

    SOURCE_URL = "https://www.swebench.com/index.html"
    FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"

    def collect(self) -> List[Observation]:
        data, is_fallback = self._load_data()
        if not data:
            console.print("[red]✗ SWE-Bench: 无数据[/red]")
            return []

        freshness = "cached" if is_fallback else "realtime"
        observations: List[Observation] = []
        for leaderboard in data:
            lb_name = (leaderboard.get("name") or "").lower()
            benchmark_key = LEADERBOARD_BENCHMARK_KEY.get(lb_name)
            if not benchmark_key:
                continue
            if lb_name not in ACTIVE_BOARDS:
                continue

            results = leaderboard.get("results") or []
            for result in results:
                obs = self._parse_result(benchmark_key, lb_name, result, freshness, is_fallback)
                if obs:
                    observations.append(obs)

        console.print(
            f"[green]✓ SWE-Bench: {len(observations)} observations "
            f"(boards: {ACTIVE_BOARDS}, freshness: {freshness})[/green]"
        )
        return observations

    def _load_data(self) -> tuple:
        """加载数据: 优先实时抓取, fallback 到本地 fixture

        Returns: (data_list, is_fallback)
        """
        # 1. 尝试实时抓取 (httpx → curl)
        data = self._fetch_live()
        if data:
            return data, False

        # 2. Fallback: 本地 fixture
        fixture = self._find_latest_fixture()
        if fixture and fixture.exists():
            console.print(f"[yellow]⚠ SWE-Bench: 实时抓取失败,使用 fixture: {fixture.name}[/yellow]")
            with open(fixture, encoding="utf-8") as f:
                payload = json.load(f)
            return payload.get("data"), True

        return None, False

    def _fetch_live(self) -> Optional[list]:
        """从 swebench.com 实时抓取 HTML,提取嵌入的 JSON"""
        from .arena import _fetch_url

        try:
            html = _fetch_url(self.SOURCE_URL, timeout=30)
        except RuntimeError:
            return None

        # 提取 <script id="leaderboard-data">...</script> 中的 JSON
        match = re.search(
            r'<script[^>]*id=["\']leaderboard-data["\'][^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not match:
            console.print("[yellow]⚠ SWE-Bench: HTML 中未找到 leaderboard-data[/yellow]")
            return None

        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError as e:
            console.print(f"[red]✗ SWE-Bench: JSON 解析失败: {e}[/red]")
            return None

    def _find_latest_fixture(self) -> Optional[Path]:
        """找最新的 swebench_official_index_*.json"""
        if not self.FIXTURE_DIR.exists():
            return None
        candidates = sorted(self.FIXTURE_DIR.glob("swebench_official_index_*.json"))
        return candidates[-1] if candidates else None

    def _parse_result(
        self, benchmark_key: str, leaderboard_name: str, result: dict,
        freshness: str, is_fallback: bool,
    ) -> Optional[Observation]:
        """单条 result -> Observation"""
        score = result.get("resolved")
        if score is None or not isinstance(score, (int, float)):
            return None

        date_str = result.get("date")
        if not date_str:
            return None
        try:
            obs_date = (
                _date.fromisoformat(str(date_str))
                if isinstance(date_str, str)
                else date_str
            )
        except (ValueError, TypeError):
            return None

        model_id = self._extract_model_id(result.get("name", ""))
        if not model_id:
            return None

        extra = {
            "raw_name": result.get("name"),
            "leaderboard": leaderboard_name,
            "instance_cost": result.get("instance_cost"),
            "instance_calls": result.get("instance_calls"),
            "total_cost": result.get("cost"),
            "agent_version": result.get("mini-swe-agent_version"),
            "os_model": result.get("os_model"),
            "tags": result.get("tags"),
        }

        return Observation(
            model=model_id,
            benchmark=benchmark_key,
            score=float(score),
            source="swebench.com",
            confidence=self.default_confidence,
            date=obs_date,
            score_raw=float(score),
            freshness=freshness,
            is_fallback=is_fallback,
            extra=extra,
        )

    @staticmethod
    def _extract_model_id(name: str) -> str:
        """从 result.name 解析基础模型名作为 canonical_id

        模式示例:
        - "live-SWE-agent + Claude 4.5 Opus medium (20251101)" -> "claude-4-5-opus"
        - "Claude 4.5 Opus (high reasoning)" -> "claude-4-5-opus"
        - "GPT-5-2 Codex" -> "gpt-5-2-codex"
        - "Gemini 3 Flash (high reasoning)" -> "gemini-3-flash"

        Phase 1: 启发式拆分 + slug 化
        Phase 2: 接入 OpenRouter alias 表做精确 join
        """
        if not name:
            return ""
        # 1. 拆 "+" 取后半 (典型 "Agent + Model" 格式)
        if "+" in name:
            name = name.split("+", 1)[1].strip()
        # 2. 去括号内容 (reasoning / 日期 / 版本)
        name = re.sub(r"\([^)]*\)", "", name)
        name = name.strip()
        if not name:
            return ""
        # 3. 转 slug: 小写、空格/点→横线、合并连续横线、去首尾横线
        slug = name.lower()
        slug = re.sub(r"[\s\.]+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        slug = slug.strip("-")
        return slug
