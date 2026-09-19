"""Collector 统一输出模型

对应用户指定的 JSON schema:
{
  "model": "gpt-5.3",
  "benchmark": "swe",
  "score": 78.2,
  "source": "official",
  "confidence": 1.0,
  "date": "2026-06-14"
}

DB 写入时通过 to_db_dict() 转换为 db_manager 期望的格式。
"""

from datetime import date as _date
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class Observation(BaseModel):
    """Collector 统一输出(对应用户指定的 schema)

    字段说明:
    - model:       canonical model_id(必须存在于 models 表或 alias 可解析)
    - benchmark:   benchmark 键(swe / livecodebench / arena_elo 等)
    - score:       主分数(数值)
    - source:      数据来源标识(official / community / openrouter / lmarena ...)
    - confidence:  数据可信度 0-1,缺省 1.0
    - date:        观测发生时间(评测日期 / 榜单日)
    """

    model: str = Field(..., min_length=1)
    benchmark: str = Field(..., min_length=1)
    score: float
    source: str = Field(..., min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    date: _date

    # 扩展字段(可选)
    score_raw: Optional[float] = None
    normalized_score: Optional[float] = None
    percentile: Optional[float] = None
    freshness: str = Field(default="realtime")  # realtime / cached / snapshot / manual
    is_fallback: bool = Field(default=False)
    extra: Optional[Dict[str, Any]] = None

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        # 二次兜底(Pydantic ge/le 已校验)
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v

    def to_db_dict(self) -> Dict[str, Any]:
        """转换为 db_manager.save_observations 接受的格式"""
        return {
            "model_id": self.model,
            "observation_type": "benchmark",  # 默认类型
            "benchmark": self.benchmark,
            "score": self.score,
            "score_raw": self.score_raw if self.score_raw is not None else self.score,
            "normalized_score": self.normalized_score,
            "percentile": self.percentile,
            "source": self.source,
            "confidence": self.confidence,
            "freshness": self.freshness,
            "is_fallback": self.is_fallback,
            "extra": self.extra,
            "observed_at": self.date,
        }


class CollectionResult(BaseModel):
    """单个 collector 的采集结果(便于批量处理和报告)"""

    collector_key: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    success: bool = False
    error: Optional[str] = None
    observations: list[Observation] = Field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.observations)
