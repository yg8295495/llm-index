"""API 路由定义 — AA 数据驱动架构 (v2)

数据来源:
  - 模型/评测数据: SQLite (via DatabaseManager)
  - 维度/数据源配置: config/benchmarks.yaml (via BenchmarkRegistry)
  - 权重/预设配置: config/settings.yaml (via WeightManager)
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from rich.console import Console

from src.collector.registry import BenchmarkRegistry
from src.compute.weight_manager import WeightManager
from src.storage.db_manager import DatabaseManager
from .schemas import (
    ModelResponse,
    BenchmarkScoreResponse,
    PricingResponse,
    CompositeIndexResponse,
    RadarDataResponse,
    ComparisonResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    DimensionInfo,
    SourceInfo,
)

console = Console()
router = APIRouter()

# 全局单例 (首次访问时初始化)
_weight_manager: Optional[WeightManager] = None
_db_manager: Optional[DatabaseManager] = None


def _get_weight_manager() -> WeightManager:
    global _weight_manager
    if _weight_manager is None:
        _weight_manager = WeightManager()
    return _weight_manager


def _get_db() -> DatabaseManager:
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


# =========================================================================
# System
# =========================================================================

@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """健康检查"""
    return HealthResponse(
        status="ok",
        version="0.3.0",
        timestamp=datetime.utcnow()
    )


# =========================================================================
# Configuration (维度/数据源/预设)
# =========================================================================

@router.get("/dimensions", response_model=List[DimensionInfo], tags=["Configuration"])
async def list_dimensions():
    """获取评测维度列表 (5 个评分维度)"""
    result = []
    for dim_key in BenchmarkRegistry.list_dimensions():
        dim = BenchmarkRegistry.get_dimension(dim_key)
        sources = BenchmarkRegistry.list_sources_by_dimension(dim_key)
        result.append(DimensionInfo(
            key=dim_key,
            name=dim.get("name", dim_key),
            description=dim.get("description", ""),
            weight=dim.get("weight", 0.0),
            sources=sources,
        ))
    return result


@router.get("/sources", response_model=List[SourceInfo], tags=["Configuration"])
async def list_sources(
    dimension: Optional[str] = Query(None, description="按维度筛选"),
    tier: Optional[str] = Query(None, description="按 tier 筛选 (primary/secondary)")
):
    """获取数据源列表"""
    if dimension:
        source_keys = BenchmarkRegistry.list_sources_by_dimension(dimension)
    else:
        source_keys = BenchmarkRegistry.list_sources()

    result = []
    for key in source_keys:
        cfg = BenchmarkRegistry.get_source(key)
        if tier and cfg.get("tier") != tier:
            continue
        result.append(SourceInfo(
            key=key,
            name=cfg.get("name", key),
            dimension=cfg.get("_dimension", ""),
            tier=cfg.get("tier", ""),
            coverage=cfg.get("coverage"),
            freshness=cfg.get("freshness"),
            confidence=cfg.get("confidence"),
            status=cfg.get("status"),
            source_url=cfg.get("source_url"),
        ))
    return result


@router.get("/presets", tags=["Configuration"])
async def list_presets():
    """获取可用的权重预设列表"""
    wm = _get_weight_manager()
    presets = wm.list_presets()
    result = {}
    for name, desc in presets.items():
        info = wm.get_preset_info(name)
        result[name] = {
            "name": info.get("name", name) if info else name,
            "description": desc,
            "weights": wm.get_weights(name),
        }
    return result


@router.get("/weights", tags=["Configuration"])
async def get_weights(
    preset_name: Optional[str] = Query(None, description="预设名称")
):
    """获取权重配置 (默认或指定预设)"""
    wm = _get_weight_manager()
    weights = wm.get_weights(preset_name)
    return {
        "weights": weights,
        "preset_name": preset_name,
        "sum": sum(weights.values()),
        "valid": wm.validate_weights(weights),
    }


# =========================================================================
# Models
# =========================================================================

@router.get("/models", response_model=List[ModelResponse], tags=["Models"])
async def list_models(
    provider: Optional[str] = Query(None, description="按厂商筛选"),
    family: Optional[str] = Query(None, description="按家族筛选"),
    active_only: bool = Query(True, description="仅返回活跃模型")
):
    """获取模型列表 (从数据库读取)"""
    db = _get_db()
    status = "active" if active_only else None
    models = db.list_models(provider=provider, status=status, family=family)
    return [
        ModelResponse(
            model_id=m.model_id,
            model_name=m.display_name or m.model_id,
            provider=m.provider,
            reasoning_level=m.reasoning_level or None,
            display_name=m.display_name,
            family=m.family,
            release_date=m.release_date.isoformat() if m.release_date else None,
            context_window=m.context_window,
            context_window_fmt=m.context_window_fmt,
            max_output_tokens=m.max_output_tokens,
            supports_tools=m.supports_tools or False,
            supports_vision=m.supports_vision or False,
            pricing_input=m.pricing_input,
            pricing_output=m.pricing_output,
            pricing_cache_input=m.pricing_cache_input,
            pricing_batch=m.pricing_batch,
            size_class=m.size_class,
            parameters=m.parameters,
            is_reasoning=m.is_reasoning,
            open_source=m.open_source,
            homepage=m.homepage,
            status=m.status,
        )
        for m in models
    ]


@router.get(
    "/models/{model_id:path}/benchmarks",
    response_model=List[BenchmarkScoreResponse],
    tags=["Models"]
)
async def get_model_benchmarks(
    model_id: str,
    benchmark: Optional[str] = Query(None, description="按 benchmark 筛选"),
    reasoning_level: Optional[str] = Query(None, description="按推理级别筛选"),
):
    """获取模型的评测数据 (从 benchmark_evals 表读取)"""
    db = _get_db()
    # 找到匹配的模型行
    models = db.list_model_variants(model_id)
    if not models:
        raise HTTPException(status_code=404, detail=f"模型 {model_id} 不存在")

    # 按 reasoning_level 筛选
    if reasoning_level:
        models = [m for m in models if m.reasoning_level == reasoning_level]

    result = []
    for m in models:
        evals = db.get_model_benchmark_evals(m.id)
        for ev in evals:
            if benchmark and ev.benchmark != benchmark:
                continue
            result.append(BenchmarkScoreResponse(
                model_id=m.model_id,
                model_name=m.display_name or m.model_id,
                reasoning_level=m.reasoning_level or None,
                benchmark=ev.benchmark,
                score_raw=ev.score_raw,
                score_type=ev.score_type,
                input_tokens=ev.input_tokens,
                output_tokens=ev.output_tokens,
                reasoning_tokens=ev.reasoning_tokens,
                cost_usd=ev.cost_usd,
                breakdown=ev.breakdown,
                source=ev.source,
                confidence=ev.confidence,
                observed_at=ev.observed_at.isoformat() if ev.observed_at else None,
            ))

    return result


@router.get(
    "/models/{model_id:path}/pricing",
    response_model=List[PricingResponse],
    tags=["Models"]
)
async def get_model_pricing(model_id: str):
    """获取模型的价格数据"""
    db = _get_db()
    models = db.list_model_variants(model_id)
    if not models:
        raise HTTPException(status_code=404, detail=f"模型 {model_id} 不存在")

    return [
        PricingResponse(
            model_id=m.model_id,
            model_name=m.display_name or m.model_id,
            provider=m.provider,
            pricing_input=m.pricing_input,
            pricing_output=m.pricing_output,
        )
        for m in models
    ]


# =========================================================================
# Benchmarks (全局)
# =========================================================================

@router.get("/benchmarks", tags=["Benchmarks"])
async def list_benchmarks():
    """列出所有已入库的 benchmark 类型"""
    db = _get_db()
    benchmarks = db.list_benchmarks()
    return {"benchmarks": benchmarks, "count": len(benchmarks)}


# =========================================================================
# Composite Index & Rankings (TODO: 对接计算层后实现)
# =========================================================================

@router.get(
    "/models/{model_id:path}/composite-index",
    response_model=CompositeIndexResponse,
    tags=["Composite Index"]
)
async def get_composite_index(
    model_id: str,
    preset_name: Optional[str] = Query(None, description="预设名称")
):
    """获取模型的综合指数

    TODO: 对接 IndexCalculator 后实现
    """
    raise HTTPException(
        status_code=501,
        detail="综合指数计算待实现 (需先入库数据)"
    )


@router.get("/rankings", tags=["Rankings"])
async def get_rankings(
    preset_name: Optional[str] = Query(None, description="预设名称"),
    top_n: int = Query(10, ge=1, le=100, description="返回前 N 名")
):
    """获取模型排名

    TODO: 对接 IndexCalculator 后实现
    """
    return []


# =========================================================================
# Visualization (雷达图)
# =========================================================================

@router.get("/radar", response_model=RadarDataResponse, tags=["Visualization"])
async def get_radar_data(
    model_ids: str = Query(..., description="模型 ID 列表，逗号分隔"),
    preset_name: Optional[str] = Query(None, description="预设名称")
):
    """获取雷达图数据

    TODO: 对接数据库和计算层后实现真实数据
    当前返回维度指示器 (空 series)
    """
    from src.dashboard.radar_data_builder import RadarDataBuilder

    model_id_list = [m.strip() for m in model_ids.split(",")]
    builder = RadarDataBuilder()

    # 构建维度指示器 (4 个评分维度)
    dimensions = BenchmarkRegistry.list_dimensions()
    indicator = builder.build_indicator(dimensions)

    return RadarDataResponse(
        indicator=indicator,
        series=[],
        metadata={
            "model_ids": model_id_list,
            "preset_name": preset_name,
            "dimensions": dimensions,
            "note": "数据待入库,当前仅返回维度结构"
        }
    )


@router.post("/compare", response_model=ComparisonResponse, tags=["Comparison"])
async def compare_models(
    model_ids: List[str],
    preset_name: Optional[str] = Query(None, description="预设名称")
):
    """比较多个模型

    TODO: 对接计算层后实现
    """
    raise HTTPException(
        status_code=501,
        detail="模型比较待实现 (需先入库数据)"
    )


# =========================================================================
# Data Ingestion (TODO: 对接 collector 后实现)
# =========================================================================

@router.post("/ingest", response_model=IngestResponse, tags=["Data Ingestion"])
async def trigger_ingest(request: IngestRequest):
    """触发数据采集

    TODO: 对接 collector 架构后实现
    """
    return IngestResponse(
        source_type=request.source_type,
        records_count=0,
        status="pending",
        message="数据采集触发逻辑待实现 (需对接 collector 架构)",
        timestamp=datetime.utcnow()
    )
