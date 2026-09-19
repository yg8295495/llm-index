"""项目路径锚点

所有读 config/ 与 data/ 的代码都必须经由这里, 不要用相对路径。
原因见 docs/changelog.md #9: WeightManager 原先写死 `open("config/settings.yaml")`,
换个工作目录跑就报 FileNotFoundError, 而同一个配置又被脚本用绝对路径读第二遍。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "llm_index.db"
SNAPSHOT_DIR = DATA_DIR / "raw" / "snapshots"
FRONTEND_DATA = ROOT / "frontend" / "data.json"
REPORTS_DIR = ROOT / "reports"
DOCS_DIR = ROOT / "docs"


def config_path(name: str) -> Path:
    return CONFIG_DIR / name
