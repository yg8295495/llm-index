"""Model Discoverer — 模型发现层

与 collector 平行:
- Collector: 采集某个 benchmark 的得分
- Discoverer: 发现/更新 model 主表里的模型(发现新模型、价格、能力)

Phase 1 实现:
- BaseDiscoverer 抽象
- OpenRouterDiscoverer(用 OpenRouter 公开 /api/v1/models 端点)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

import httpx
from rich.console import Console

console = Console()


@dataclass
class DiscoveredModel:
    """Discoverer 输出的标准化模型数据

    ID 规范 (2026-06-17): canonical_id 使用 OpenRouter 完整 ID (provider/model-slug)
    与 aliases.yaml / factual_scores.yaml / swe_claims.yaml 一致
    """

    canonical_id: str  # OpenRouter 完整 ID (provider/model-slug), 主表 id
    provider: str
    raw_id: str  # 原始 OpenRouter id (含 ~ 路由符号,作为 alias)
    release_date: Optional[date]
    context_window: Optional[int]
    max_output_tokens: Optional[int]
    supports_tools: bool
    supports_vision: bool
    supports_audio: bool
    pricing_input: Optional[float]  # USD per 1M tokens
    pricing_output: Optional[float]
    homepage: str
    source: str = "openrouter"


class BaseDiscoverer(ABC):
    """Discoverer 抽象基类"""

    def __init__(self, source: str):
        self.source = source

    @abstractmethod
    def discover(self) -> List[DiscoveredModel]:
        """执行发现,返回 DiscoveredModel 列表"""
        raise NotImplementedError


class OpenRouterDiscoverer(BaseDiscoverer):
    """OpenRouter 模型发现器

    - 调 https://openrouter.ai/api/v1/models(无需 key,有 key 限速更高)
    - 解析每个模型的 metadata,标准化为 DiscoveredModel
    - canonical_id = OpenRouter 完整 ID (provider/model-slug)
    - raw_id 保留原始 ID (含 ~ 路由符号) 作为 alias
    """

    DEFAULT_URL = "https://openrouter.ai/api/v1/models"

    def __init__(self, api_key: Optional[str] = None, url: str = DEFAULT_URL, timeout: int = 30):
        super().__init__(source="openrouter")
        self.api_key = api_key
        self.url = url
        self.timeout = timeout

    def discover(self) -> List[DiscoveredModel]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        console.print(f"[blue]调用 {self.url} ...[/blue]")
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(self.url, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
        raw_models = payload.get("data", [])
        console.print(f"[green]✓ 收到 {len(raw_models)} 个模型[/green]")

        results: List[DiscoveredModel] = []
        for m in raw_models:
            try:
                results.append(self._parse(m))
            except Exception as e:
                console.print(f"[yellow]⚠ 跳过 {m.get('id', '?')}: {e}[/yellow]")
        return results

    @staticmethod
    def _parse(m: dict) -> DiscoveredModel:
        raw_id = m.get("id", "")
        if not raw_id:
            raise ValueError("missing id")

        # 拆 provider
        # ~anthropic/claude-fable-latest -> provider=anthropic, canonical_id=anthropic/claude-fable-latest
        # openai/gpt-5.3 -> provider=openai, canonical_id=openai/gpt-5.3
        # openrouter/fusion -> provider=openrouter, canonical_id=openrouter/fusion
        cleaned = raw_id.lstrip("~")
        if "/" in cleaned:
            provider, _ = cleaned.split("/", 1)
        else:
            provider = "unknown"

        # canonical_id: OpenRouter 完整 ID (provider/model-slug)
        # 与 aliases.yaml / factual_scores.yaml / swe_claims.yaml 一致
        canonical_id = cleaned

        # release_date
        release_date = None
        if m.get("created"):
            try:
                release_date = datetime.fromtimestamp(int(m["created"])).date()
            except (ValueError, TypeError, OSError):
                release_date = None

        # 能力
        context_window = m.get("context_length") or None
        top = m.get("top_provider") or {}
        max_output = top.get("max_completion_tokens") or None

        arch = m.get("architecture") or {}
        input_modalities = arch.get("input_modalities") or []
        supports_vision = "image" in input_modalities
        supports_audio = "audio" in input_modalities

        sp = m.get("supported_parameters") or []
        supports_tools = "tools" in sp

        # pricing: USD per token -> USD per 1M tokens
        pricing = m.get("pricing") or {}
        pricing_input = OpenRouterDiscoverer._price_to_per_million(pricing.get("prompt"))
        pricing_output = OpenRouterDiscoverer._price_to_per_million(pricing.get("completion"))

        homepage = f"https://openrouter.ai/models/{raw_id}"

        return DiscoveredModel(
            canonical_id=canonical_id,
            provider=provider,
            raw_id=raw_id,
            release_date=release_date,
            context_window=int(context_window) if context_window else None,
            max_output_tokens=int(max_output) if max_output else None,
            supports_tools=supports_tools,
            supports_vision=supports_vision,
            supports_audio=supports_audio,
            pricing_input=pricing_input,
            pricing_output=pricing_output,
            homepage=homepage,
            source="openrouter",
        )

    @staticmethod
    def _price_to_per_million(p) -> Optional[float]:
        """OpenRouter 计价单位: USD per token. 转为 USD per 1M tokens"""
        if p is None or p == "":
            return None
        try:
            return float(p) * 1_000_000
        except (ValueError, TypeError):
            return None


def persist_discoveries(db, discoveries: List[DiscoveredModel]) -> tuple[int, int]:
    """把 DiscoveredModel 写入数据库

    - 每个 model upsert 到 models 表
    - raw_id (含 ~ 路由符号) 作为 alias 写入 model_alias(source="openrouter")
    - 返回 (model 数, alias 数)
    """
    n_models = 0
    n_aliases = 0
    for d in discoveries:
        db.upsert_model({
            "id": d.canonical_id,
            "provider": d.provider,
            "release_date": d.release_date,
            "context_window": d.context_window,
            "max_output_tokens": d.max_output_tokens,
            "supports_tools": d.supports_tools,
            "supports_vision": d.supports_vision,
            "supports_audio": d.supports_audio,
            "pricing_input": d.pricing_input,
            "pricing_output": d.pricing_output,
            "homepage": d.homepage,
            "status": "active",
        })
        n_models += 1
        # raw_id 含 ~ 路由符号时作为 alias 保留
        if d.raw_id != d.canonical_id:
            db.add_alias(d.raw_id, d.canonical_id, source="openrouter")
            n_aliases += 1
    console.print(f"[green]✓ 持久化 {n_models} 个 model + {n_aliases} 个 alias[/green]")
    return n_models, n_aliases
