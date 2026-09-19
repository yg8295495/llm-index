"""Pydantic 模型定义

维度体系 (v4, 2026-06-19):
  5 个评分维度: factual / workflow / engineering / cost / preference
  preference 无数据时权重自动重新分配
  accessibility 为标签,不参与评分
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ModelResponse(BaseModel):
    """模型基本信息响应"""
    model_id: str = Field(..., description="模型 ID (OpenRouter canonical: provider/model-slug)")
    model_name: str = Field(..., description="模型显示名称")
    provider: Optional[str] = Field(None, description="厂商")
    reasoning_level: Optional[str] = Field(None, description="推理级别: xhigh/high/medium/low/non-reasoning/adaptive-max/reasoning 等")
    display_name: Optional[str] = Field(None, description="AA 原始显示名 (含推理级别标注)")
    family: Optional[str] = Field(None, description="模型家族 (gpt-5/claude/gemini/...)")
    release_date: Optional[str] = Field(None, description="发布日期")
    context_window: Optional[int] = Field(None, description="上下文窗口大小")
    context_window_fmt: Optional[str] = Field(None, description="上下文窗口格式化 (1M/200K)")
    max_output_tokens: Optional[int] = Field(None, description="最大输出 token 数")
    supports_tools: bool = Field(False, description="是否支持工具调用")
    supports_vision: bool = Field(False, description="是否支持视觉输入")
    pricing_input: Optional[float] = Field(None, description="输入价格 (USD/1M tokens)")
    pricing_output: Optional[float] = Field(None, description="输出价格 (USD/1M tokens)")
    pricing_cache_input: Optional[float] = Field(None, description="缓存输入价格 (USD/1M tokens)")
    pricing_batch: Optional[float] = Field(None, description="批处理价格 (USD/1M tokens)")
    size_class: Optional[str] = Field(None, description="模型大小分类 (Tiny/Small/Medium/Large)")
    parameters: Optional[float] = Field(None, description="参数量 (B)")
    is_reasoning: Optional[bool] = Field(None, description="是否推理模型")
    open_source: Optional[str] = Field(None, description="开源状态 (open/proprietary/hybrid)")
    homepage: Optional[str] = Field(None, description="模型主页 URL")
    status: str = Field("active", description="状态: active/deprecated/preview")
    tags: Dict[str, Any] = Field(default_factory=dict, description="标签 (如 accessibility)")


class BenchmarkScoreResponse(BaseModel):
    """基准测试得分响应 (来自 benchmark_evals 表)"""
    model_id: str
    model_name: Optional[str] = None
    reasoning_level: Optional[str] = None
    benchmark: str = Field(..., description="benchmark key (如 aa_omniscience/gpqa/hle)")
    score_raw: Optional[float] = Field(None, description="原始分数 (Elo/百分比/指数)")
    score_type: Optional[str] = Field(None, description="分数类型 (index/normalized/elo)")
    input_tokens: Optional[int] = Field(None, description="输入 token 用量")
    output_tokens: Optional[int] = Field(None, description="输出 token 用量")
    reasoning_tokens: Optional[int] = Field(None, description="推理 token 用量")
    cost_usd: Optional[float] = Field(None, description="推算成本 (USD)")
    breakdown: Optional[Dict[str, Any]] = Field(None, description="子维度拆分")
    source: Optional[str] = Field(None, description="数据来源")
    confidence: Optional[float] = Field(None, description="置信度")
    observed_at: Optional[str] = Field(None, description="观测日期")


class PricingResponse(BaseModel):
    """价格数据响应"""
    model_id: str
    model_name: Optional[str] = None
    provider: Optional[str] = None
    pricing_input: Optional[float] = Field(None, description="输入价格 (USD/1M tokens)")
    pricing_output: Optional[float] = Field(None, description="输出价格 (USD/1M tokens)")
    currency: str = "USD"
    source: str = "openrouter"


class DimensionScore(BaseModel):
    """维度得分"""
    dimension: str
    raw_score: float
    normalized_score: float
    weight: float
    contribution: float


class CompositeIndexResponse(BaseModel):
    """综合指数响应"""
    model_id: str
    model_name: Optional[str] = None
    composite_index: float
    dimension_scores: Dict[str, float]
    dimension_contributions: Dict[str, float]
    weights_used: Dict[str, float]
    preset_name: Optional[str] = None
    calculated_at: datetime


class RadarAxis(BaseModel):
    """雷达图轴数据"""
    dimension: str
    dimension_label: str
    score: float
    max_score: float = 100.0


class RadarSeries(BaseModel):
    """雷达图系列数据"""
    model_id: str
    model_name: str
    values: List[float]
    area: Optional[Dict[str, Any]] = None
    line: Optional[Dict[str, Any]] = None


class RadarDataResponse(BaseModel):
    """雷达图数据响应"""
    indicator: List[Dict[str, Any]]  # [{"name": "真实工作流", "max": 100}, ...]
    series: List[RadarSeries]
    metadata: Optional[Dict[str, Any]] = None


class ComparisonResponse(BaseModel):
    """模型比较响应"""
    models: Dict[str, Dict[str, Any]]
    rankings: List[Dict[str, Any]]
    dimension_leaders: Dict[str, Dict[str, Any]]


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    version: str
    timestamp: datetime


class IngestRequest(BaseModel):
    """数据采集请求"""
    source_type: str = Field(..., description="数据源类型: benchmark, pricing, model_discovery")
    source_name: Optional[str] = Field(None, description="特定数据源名称 (如 arena, swebench)")


class IngestResponse(BaseModel):
    """数据采集响应"""
    source_type: str
    records_count: int
    status: str
    message: str
    timestamp: datetime


class DimensionInfo(BaseModel):
    """维度信息"""
    key: str
    name: str
    description: str
    weight: float
    sources: List[str] = Field(default_factory=list, description="数据源 key 列表")


class SourceInfo(BaseModel):
    """数据源信息"""
    key: str
    name: str
    dimension: str
    tier: str = Field(..., description="primary/secondary")
    coverage: Optional[int] = None
    freshness: Optional[str] = None
    confidence: Optional[float] = None
    status: Optional[str] = None
    source_url: Optional[str] = None
