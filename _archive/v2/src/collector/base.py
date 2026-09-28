"""Collector 抽象基类

所有 benchmark collector 都继承 BaseCollector,实现 collect() 方法。
Collector 不直接知道 DB(可选注入),只负责产出 Observation 列表。
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from .output import Observation


class BaseCollector(ABC):
    """Collector 抽象基类

    使用流程:
        cfg = BenchmarkRegistry.get("swe")
        cls = BenchmarkRegistry.get_collector_class("swe")
        collector = cls(cfg)  # config 注入
        observations = collector.collect()
    """

    def __init__(
        self,
        config: dict,
        benchmark_key: Optional[str] = None,
        db: Optional[object] = None,
    ):
        self.config = config
        self.benchmark_key = benchmark_key or config.get("name", "unknown")
        self.category = config.get("category", "")
        self.default_confidence = config.get("default_confidence", 1.0)
        self.source_url = config.get("source_url", "")
        self.db = db  # DatabaseManager,可选

    @abstractmethod
    def collect(self) -> List[Observation]:
        """执行采集,返回 Observation 列表

        子类应:
        1. 调用 strategy.fetch() 拿原始数据
        2. parse 成 Observation
        3. 异常时单独 try-catch,不让单条错误搞挂整批
        """
        raise NotImplementedError

    def name(self) -> str:
        return self.config.get("name", self.benchmark_key)
