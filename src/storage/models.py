"""SQLAlchemy ORM 模型 — AA 数据驱动架构 (v3, 2026-09-20)

数据层：
- Model              模型主表（含推理深度变体，每条 AA 记录一行）
- BenchmarkEval      评测结果表（一个模型 × 一个 benchmark × 一个快照 = 一行）
- Snapshot           采集快照表（版本轨迹: 抓取时刻 + 页面 sha256）
- ModelIdRename      model_id 规范化审计表
- ModelAlias         模型别名映射
- ModelStatusHistory 模型状态变更审计
- Observation        非 benchmark 观测（pricing/subscription/community 等）

schema 以本文件为唯一声明处; src/storage/snapshot_store.ensure_schema() 只负责
把缺失的列 ALTER 到已存在的旧库上, 不另起一套定义。
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Model(Base):
    """模型主表 — 每条 AA 记录一行（含推理深度变体）"""

    __tablename__ = "models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(String(100), nullable=False, index=True)  # OpenRouter ID: "openai/gpt-5.5"
    reasoning_level = Column(String(30), nullable=True)  # xhigh/high/medium/low/non-reasoning/adaptive-max/null
    aa_slug = Column(String(100), nullable=True, index=True)  # AA slug: "gpt-5-5"
    display_name = Column(String(200), nullable=True)  # "GPT-5.5 (xhigh)"

    provider = Column(String(50), nullable=False, index=True)  # openai/anthropic/google/...
    family = Column(String(50), nullable=True, index=True)  # gpt-5/claude/gemini/...
    version = Column(String(50), nullable=True)
    release_date = Column(Date, nullable=True)

    # 上下文 & 输出
    context_window = Column(Integer, nullable=True)
    context_window_fmt = Column(String(20), nullable=True)  # "1M"/"200K"
    max_output_tokens = Column(Integer, nullable=True)

    # 能力
    supports_tools = Column(Boolean, default=False)
    supports_vision = Column(Boolean, default=False)
    supports_audio = Column(Boolean, default=False)

    # 价格（USD per 1M tokens）
    pricing_input = Column(Float, nullable=True)
    pricing_output = Column(Float, nullable=True)
    pricing_cache_input = Column(Float, nullable=True)
    pricing_batch = Column(Float, nullable=True)

    # 模型属性
    size_class = Column(String(20), nullable=True)  # Tiny/Small/Medium/Large
    parameters = Column(Float, nullable=True)  # 参数量(B)
    is_reasoning = Column(Boolean, nullable=True)
    open_source = Column(String(30), nullable=True)  # open/proprietary/hybrid

    # 生命周期
    status = Column(String(20), default="active", index=True)
    homepage = Column(String(500), nullable=True)

    # 范围与溯源 (v3, 2026-09-20)
    tier = Column(String(20), nullable=True, index=True)  # core/reference/unclassified/excluded
    aa_base_slug = Column(String(100), nullable=True, index=True)  # AA release.slug (基座)
    deprecated = Column(Integer, default=0)  # AA 自带 deprecated 标记
    active_params = Column(Float, nullable=True)  # 激活参数量(B), MoE 模型用
    openness_index = Column(Float, nullable=True)  # AA Openness Index (标签, 不参与评分)
    answer_speed = Column(Float, nullable=True)  # 标准评测下输出速度 tokens/s
    needs_manual_review = Column(Integer, default=0)  # 自动化产出的待人工确认项

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("model_id", "reasoning_level", name="uq_model_reasoning"),
    )

    def __repr__(self) -> str:
        return f"<Model(id={self.id}, model_id={self.model_id}, reasoning={self.reasoning_level})>"


class BenchmarkEval(Base):
    """评测结果表 — 一个模型 × 一个 benchmark × 一个快照 = 一行

    同一模型被再次采集时追加新行而不是覆盖, 分数因此有版本轨迹可回溯。

    包含分数 + token 用量 + 成本 + 子维度拆分
    """

    __tablename__ = "benchmark_evals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_pk = Column(Integer, ForeignKey("models.id"), nullable=False, index=True)
    benchmark = Column(String(50), nullable=False, index=True)  # aa_omniscience/gpqa/hle/...

    # 分数
    score = Column(Float, nullable=True)  # 归一化分数 (0-100), 由计算层填充
    score_raw = Column(Float, nullable=True)  # 原始分数 (Elo/百分比/指数, 可为负)
    score_type = Column(String(20), nullable=True)  # index/normalized/elo/ratio/usd

    # Token 用量
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    reasoning_tokens = Column(Integer, nullable=True)

    # 成本
    cost_usd = Column(Float, nullable=True)  # 旧列: v2 的 per-task 口径, v3 起不再写入
    run_cost_usd = Column(Float, nullable=True)  # v3: 跑完该评测整套题一次的美元消耗

    # 子维度拆分
    breakdown = Column(JSON, nullable=True)  # omniscience_breakdown 等

    # 元数据
    source = Column(String(50), nullable=True)  # artificial_analysis/openrouter/...
    confidence = Column(Float, default=1.0)
    observed_at = Column(Date, nullable=True)  # AA 快照日
    collected_at = Column(DateTime, default=_utcnow)  # 真实抓取时刻

    # 溯源与版本 (v3, 2026-09-20)
    snapshot_id = Column(Integer, ForeignKey("snapshots.id"), nullable=True, index=True)
    dimension = Column(String(20), nullable=True)  # 所属评分维度
    direction = Column(String(10), nullable=True)  # higher | lower
    source_url = Column(Text, nullable=True)  # 无 source_url 不入库, 见 snapshot_store.write

    __table_args__ = (
        Index("idx_benchmark_evals_lookup", "model_pk", "benchmark"),
        Index("idx_eval_benchmark_snapshot", "benchmark", "snapshot_id"),
        UniqueConstraint("model_pk", "benchmark", "snapshot_id", name="uq_eval_snapshot"),
    )

    def __repr__(self) -> str:
        return (
            f"<BenchmarkEval(model_pk={self.model_pk}, "
            f"benchmark={self.benchmark}, score_raw={self.score_raw})>"
        )


class ModelAlias(Base):
    """模型别名映射表"""

    __tablename__ = "model_alias"

    alias = Column(String(200), primary_key=True)
    canonical_model_id = Column(
        String(100), nullable=False, index=True
    )
    source = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    def __repr__(self) -> str:
        return f"<ModelAlias({self.alias} -> {self.canonical_model_id})>"


class ModelStatusHistory(Base):
    """模型状态变更审计表"""

    __tablename__ = "model_status_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_pk = Column(Integer, ForeignKey("models.id"), nullable=False, index=True)
    old_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=False)
    changed_at = Column(DateTime, default=_utcnow, index=True)
    note = Column(String(500), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ModelStatusHistory(model_pk={self.model_pk}, "
            f"{self.old_status} -> {self.new_status})>"
        )


class Observation(Base):
    """非 benchmark 观测表 — pricing/subscription/community 等"""

    __tablename__ = "observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_pk = Column(Integer, ForeignKey("models.id"), nullable=False, index=True)
    observation_type = Column(String(30), nullable=False, index=True)  # pricing/subscription/community
    category = Column(String(50), nullable=True)
    value = Column(Float, nullable=True)
    value_str = Column(String(500), nullable=True)
    extra = Column(JSON, nullable=True)
    source = Column(String(50), nullable=True)
    confidence = Column(Float, default=1.0)
    observed_at = Column(Date, nullable=True)
    collected_at = Column(DateTime, default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"<Observation(model_pk={self.model_pk}, "
            f"type={self.observation_type}, category={self.category})>"
        )


class Snapshot(Base):
    """采集快照表 — 一站一版, 支撑"数据可核验 + 版本轨迹"

    旧架构没有这张表, 所以无法回答"这个 62.5 分是哪一天从页面上取到的",
    也无法在不覆盖历史的前提下追加新一批数据 (changelog #3)。
    """

    __tablename__ = "snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_date = Column(Date, nullable=False, unique=True)  # AA 快照日 (受众时区)
    source = Column(String(50), nullable=False)
    source_url = Column(Text, nullable=False)
    fetched_at = Column(String(40), nullable=False)  # 真实抓取 UTC 时刻 (ISO8601)
    html_sha256 = Column(String(64), nullable=True)  # 页面指纹, 供他人复验
    html_bytes = Column(Integer, nullable=True)
    parsed_path = Column(String(300), nullable=True)  # 解析产物落盘位置
    model_count = Column(Integer, nullable=True)
    eval_count = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    def __repr__(self) -> str:
        return f"<Snapshot({self.snapshot_date}, {self.source}, evals={self.eval_count})>"


class ModelIdRename(Base):
    """model_id 规范化审计表

    采集器按 AA creator/release 纠正历史 ID 时, 旧 ID 不删, 在这里留一条记录,
    并写入 model_alias 使旧链接仍可解析。
    """

    __tablename__ = "model_id_renames"

    id = Column(Integer, primary_key=True, autoincrement=True)
    old_model_id = Column(String(100), nullable=False, index=True)
    new_model_id = Column(String(100), nullable=False, index=True)
    aa_slug = Column(String(100), nullable=True)
    reason = Column(Text, nullable=True)
    snapshot_id = Column(Integer, ForeignKey("snapshots.id"), nullable=True)
    changed_at = Column(DateTime, default=_utcnow)
