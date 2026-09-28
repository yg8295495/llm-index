"""存储模块 — 快照追加式架构 (v3)

只保留 v3 活管线依赖的两块:
  models         — SQLAlchemy ORM (建表/测试用)
  snapshot_store — 快照追加写入、幂等、reconcile

v2 的 DatabaseManager (session 封装 + save_observations) 已归档到
_archive/v2/src/storage/, 原因见 _archive/v2/README.md。
"""

from .models import (
    Base,
    BenchmarkEval,
    Model,
    ModelAlias,
    ModelIdRename,
    ModelStatusHistory,
    Snapshot,
)

__all__ = [
    "Base",
    "BenchmarkEval",
    "Model",
    "ModelAlias",
    "ModelIdRename",
    "ModelStatusHistory",
    "Snapshot",
]
