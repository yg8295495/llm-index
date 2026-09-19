"""数据库管理器 — AA 数据驱动架构 (v2)

职责：
- 创建/删除表
- 通用 session 上下文
- Model / BenchmarkEval / Alias / StatusHistory / Observation 的 CRUD
"""

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from rich.console import Console
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, BenchmarkEval, Model, ModelAlias, ModelStatusHistory, Observation

console = Console()


class DatabaseManager:
    """数据库管理器"""

    def __init__(self, database_url: str = "sqlite:///data/llm_index.db"):
        self.database_url = database_url
        connect_args: Dict[str, Any] = {}
        if database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self.engine = create_engine(database_url, echo=False, connect_args=connect_args)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    # ===== 表管理 =====

    def create_tables(self) -> None:
        console.print("[blue]正在创建数据库表...[/blue]")
        Base.metadata.create_all(self.engine)
        console.print("[green]✓ 数据库表创建完成[/green]")

    def drop_tables(self) -> None:
        console.print("[yellow]正在删除数据库表...[/yellow]")
        Base.metadata.drop_all(self.engine)
        console.print("[red]✗ 数据库表已删除[/red]")

    # ===== Session 上下文 =====

    @contextmanager
    def get_session(self) -> Session:
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            console.print(f"[red]数据库操作失败: {e}[/red]")
            raise
        finally:
            session.close()

    # ===== Model 操作 =====

    def get_model_by_pk(self, pk: int) -> Optional[Model]:
        """通过自增主键获取模型"""
        with self.get_session() as session:
            return session.get(Model, pk)

    def get_model_by_id(self, model_id: str, reasoning_level: str = "") -> Optional[Model]:
        """通过 model_id + reasoning_level 获取模型"""
        with self.get_session() as session:
            return (
                session.query(Model)
                .filter(Model.model_id == model_id, Model.reasoning_level == reasoning_level)
                .first()
            )

    def get_model_by_alias(self, alias: str) -> Optional[Model]:
        """通过别名查找模型"""
        with self.get_session() as session:
            a = session.get(ModelAlias, alias)
            if a:
                # 别名指向 canonical_model_id，返回该模型的默认版本 (reasoning_level='')
                return (
                    session.query(Model)
                    .filter(Model.model_id == a.canonical_model_id)
                    .first()
                )
            return None

    def list_models(
        self,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        family: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Model]:
        """列出模型，支持按 provider/status/family 筛选"""
        with self.get_session() as session:
            q = session.query(Model)
            if provider:
                q = q.filter(Model.provider == provider)
            if status:
                q = q.filter(Model.status == status)
            if family:
                q = q.filter(Model.family == family)
            return q.order_by(Model.provider, Model.model_id, Model.reasoning_level).limit(limit).all()

    def list_model_variants(self, model_id: str) -> List[Model]:
        """获取同一 model_id 的所有推理级别变体"""
        with self.get_session() as session:
            return (
                session.query(Model)
                .filter(Model.model_id == model_id)
                .order_by(Model.reasoning_level)
                .all()
            )

    # ===== BenchmarkEval 操作 =====

    def get_benchmark_evals(
        self,
        model_pk: Optional[int] = None,
        benchmark: Optional[str] = None,
        limit: int = 1000,
    ) -> List[BenchmarkEval]:
        """获取评测记录"""
        with self.get_session() as session:
            q = session.query(BenchmarkEval)
            if model_pk is not None:
                q = q.filter(BenchmarkEval.model_pk == model_pk)
            if benchmark:
                q = q.filter(BenchmarkEval.benchmark == benchmark)
            return q.limit(limit).all()

    def get_model_benchmark_evals(self, model_pk: int) -> List[BenchmarkEval]:
        """获取某个模型的所有评测记录"""
        with self.get_session() as session:
            return (
                session.query(BenchmarkEval)
                .filter(BenchmarkEval.model_pk == model_pk)
                .all()
            )

    def get_benchmark_eval(self, model_pk: int, benchmark: str) -> Optional[BenchmarkEval]:
        """获取某个模型某个 benchmark 的评测记录"""
        with self.get_session() as session:
            return (
                session.query(BenchmarkEval)
                .filter(BenchmarkEval.model_pk == model_pk, BenchmarkEval.benchmark == benchmark)
                .first()
            )

    def list_benchmarks(self) -> List[str]:
        """列出所有已入库的 benchmark 类型"""
        with self.get_session() as session:
            rows = session.query(BenchmarkEval.benchmark).distinct().all()
            return [r[0] for r in rows]

    # ===== Alias 操作 =====

    def add_alias(
        self, alias: str, canonical_model_id: str, source: Optional[str] = None
    ) -> ModelAlias:
        """添加或更新别名映射"""
        with self.get_session() as session:
            existing = session.get(ModelAlias, alias)
            if existing:
                existing.canonical_model_id = canonical_model_id
                if source:
                    existing.source = source
                session.flush()
                return existing
            a = ModelAlias(alias=alias, canonical_model_id=canonical_model_id, source=source)
            session.add(a)
            session.flush()
            console.print(f"[green]✓ alias: {alias} -> {canonical_model_id}[/green]")
            return a

    # ===== Status History 操作 =====

    def record_status_change(
        self,
        model_pk: int,
        old_status: Optional[str],
        new_status: str,
        note: Optional[str] = None,
    ) -> ModelStatusHistory:
        with self.get_session() as session:
            h = ModelStatusHistory(
                model_pk=model_pk,
                old_status=old_status,
                new_status=new_status,
                note=note,
            )
            session.add(h)
            session.flush()
            return h

    # ===== Observation 操作 =====

    def save_observations(self, observations: List[Dict[str, Any]]) -> int:
        """批量保存观测记录(append-only)"""
        with self.get_session() as session:
            count = 0
            for obs_data in observations:
                if "model_pk" not in obs_data:
                    raise ValueError("observation 必须包含 'model_pk' 字段")
                obs = Observation(
                    model_pk=obs_data["model_pk"],
                    observation_type=obs_data.get("observation_type", "pricing"),
                    category=obs_data.get("category"),
                    value=obs_data.get("value"),
                    value_str=obs_data.get("value_str"),
                    extra=obs_data.get("extra"),
                    source=obs_data.get("source"),
                    confidence=obs_data.get("confidence", 1.0),
                    observed_at=obs_data.get("observed_at"),
                )
                session.add(obs)
                count += 1
            console.print(f"[green]✓ 保存 {count} 条 observation 记录[/green]")
            return count

    def get_observations(
        self,
        model_pk: Optional[int] = None,
        observation_type: Optional[str] = None,
        category: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Observation]:
        with self.get_session() as session:
            q = session.query(Observation)
            if model_pk is not None:
                q = q.filter(Observation.model_pk == model_pk)
            if observation_type:
                q = q.filter(Observation.observation_type == observation_type)
            if category:
                q = q.filter(Observation.category == category)
            if since:
                q = q.filter(Observation.collected_at >= since)
            return q.order_by(desc(Observation.collected_at)).limit(limit).all()
