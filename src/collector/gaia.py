"""GAIA collector (Phase 1 stub)

P2 阶段实现。
"""

from typing import List

from .base import BaseCollector
from .output import Observation


class GAIACollector(BaseCollector):
    """GAIA 数据采集器"""

    def collect(self) -> List[Observation]:
        raise NotImplementedError(
            "GAIACollector.collect() 在 P2 阶段实现"
        )
