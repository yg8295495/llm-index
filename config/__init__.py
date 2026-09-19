"""配置模块"""

from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 配置文件目录
CONFIG_DIR = PROJECT_ROOT / "config"

# 数据目录
DATA_DIR = PROJECT_ROOT / "data"
RAW_BENCH_DIR = DATA_DIR / "raw_bench"
RAW_PRICING_DIR = DATA_DIR / "raw_pricing"
RAW_AGENT_DIR = DATA_DIR / "raw_agent"

# 报告目录
REPORTS_DIR = PROJECT_ROOT / "reports"

# 确保目录存在
for dir_path in [DATA_DIR, RAW_BENCH_DIR, RAW_PRICING_DIR, RAW_AGENT_DIR, REPORTS_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)
