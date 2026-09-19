"""Collector module — 数据采集框架

Phase 1 进度：
- registry:   BenchmarkRegistry(配置驱动)
- base:       BaseCollector 抽象基类
- output:     Observation 统一输出模型
- strategies: 4 级采集策略(API / JSON / Static / Playwright)
- 5 个具体 collector(全部 stub,P1/P2 填充)
"""

from .base import BaseCollector
from .discoverer import (
    BaseDiscoverer,
    DiscoveredModel,
    OpenRouterDiscoverer,
    persist_discoveries,
)
from .output import CollectionResult, Observation
from .registry import BenchmarkRegistry

__all__ = [
    "BaseCollector",
    "BaseDiscoverer",
    "DiscoveredModel",
    "OpenRouterDiscoverer",
    "persist_discoveries",
    "Observation",
    "CollectionResult",
    "BenchmarkRegistry",
]
