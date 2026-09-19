"""测试配置 (v5, 2026-09-20)

原则: 期望值一律从 config/ 读, 不在测试里重述维度名和权重。
旧测试写死 "4 维 / developer 预设" 这类字面量, 配置升到 v5 五维后
测试整片变红却没有暴露真实故障, 只是测试自己过期了 —— 见 docs/changelog.md #18。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load(name: str) -> dict:
    return yaml.safe_load((ROOT / "config" / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def settings() -> dict:
    return _load("settings.yaml")


@pytest.fixture(scope="session")
def benchmarks_cfg() -> dict:
    return _load("benchmarks.yaml")


@pytest.fixture(scope="session")
def vendors() -> dict:
    return _load("vendors.yaml")["vendors"]


@pytest.fixture(scope="session")
def scoring_dims(benchmarks_cfg) -> list[str]:
    return [k for k in benchmarks_cfg["dimensions"] if k != "tags"]


@pytest.fixture(scope="session")
def aa_benchmark_fields(benchmarks_cfg) -> set[str]:
    """benchmarks.yaml 里声明了 aa_key 的数据源 = 采集器应当认识的字段全集"""
    out = set()
    for dim in benchmarks_cfg["dimensions"].values():
        for src in (dim.get("sources") or {}).values():
            if isinstance(src, dict) and src.get("aa_key"):
                out.add(src["aa_key"])
    return out


# ---------------------------------------------------------------------------
# 合成 AA 数据: 不依赖真实快照文件, 保证测试可在任何机器上跑
# ---------------------------------------------------------------------------

FAKE_BASE = "2026-09-20"

FAKE_SCORED = [
    {
        "id": "aaaaaaaa-0000-0000-0000-000000000001",
        "slug": "glm-9-9",
        "name": "GLM-9.9 (max)",
        "creator": {"id": "c1", "slug": "zai", "name": "Z AI",
                    "logo": "/img/logos/zai_small.svg"},
        "releaseDate": "2026-09-01",
        "isOpenWeights": False,
        "isReasoning": True,
        "sizeClass": "large",
        "inputModalityImage": True,
        "inputModalitySpeech": False,
        "price1mInputTokens": 1.0,
        "price1mOutputTokens": 4.0,
        "cacheHitPrice": 0.2,
        "intelligenceIndex": 50.0,
        "omniscience": 40.0,
        "gpqa": 0.90,
        "hle": 0.50,
        "gdpval": 1700.0,
        "tauBanking": 0.40,
        "terminalBench21": 0.80,
        "terminalBench40": 0.50,
        "scicode": 0.60,
        "lcr": 0.70,
        "critpt": 0.30,
        "briefcaseElo": 1600.0,
        "gdpPdfAllPass": 0.30,
        "automationBenchPartialScore": 0.60,
        "omniscienceBreakdown": {"accuracy": 0.7, "hallucinationRate": 0.2,
                                 "attemptRate": 0.9},
        "canonicalEvalTokenCounts": {
            "gpqa": {"input": 100000, "answer": 200000, "reasoning": 700000},
            "hle": {"input": 50000, "answer": 100000, "reasoning": 0},
        },
    },
    {
        # 同一基座的另一个推理档位: 必须落到同一 model_id, 不同 reasoning_level
        "id": "aaaaaaaa-0000-0000-0000-000000000002",
        "slug": "glm-9-9-high",
        "name": "GLM-9.9 (high)",
        "creator": {"id": "c1", "slug": "zai", "name": "Z AI",
                    "logo": "/img/logos/zai_small.svg"},
        "releaseDate": "2026-09-01",
        "isOpenWeights": False,
        "intelligenceIndex": 45.0,
        "omniscience": -12.5,     # 负值: 归一化必须不出界
        "gpqa": 0.80,
        "canonicalEvalTokenCounts": {},
    },
    {
        # 范围外厂商: 不进综合榜
        "id": "aaaaaaaa-0000-0000-0000-000000000003",
        "slug": "other-9",
        "name": "Other 9 (max)",
        "creator": {"id": "c2", "slug": "groklab", "name": "GrokLab",
                    "logo": "/img/logos/unknown_vendor.svg"},
        "releaseDate": "2026-09-05",
        "intelligenceIndex": 60.0,
        "omniscience": 10.0,
        "canonicalEvalTokenCounts": {},
    },
]

FAKE_REGISTRY = [
    {"slug": "glm-9-9", "name": "GLM-9.9 (max)", "deprecated": False, "isReasoning": True,
     "effort": {"slug": "max", "label": "max", "level": 60},
     "release": {"slug": "glm-9-9", "name": "GLM-9.9"},
     "releaseDate": "2026-09-01",
     "creator": {"id": "c1", "name": "Z AI", "logo": "/img/logos/zai_small.svg"}},
    {"slug": "glm-9-9-high", "name": "GLM-9.9 (high)", "deprecated": False, "isReasoning": True,
     "effort": {"slug": "high", "label": "high", "level": 40},
     "release": {"slug": "glm-9-9", "name": "GLM-9.9"},
     "releaseDate": "2026-09-01",
     "creator": {"id": "c1", "name": "Z AI", "logo": "/img/logos/zai_small.svg"}},
    {"slug": "other-9", "name": "Other 9 (max)", "deprecated": False, "isReasoning": True,
     "effort": {"slug": "max", "label": "max", "level": 60},
     "release": {"slug": "other-9", "name": "Other 9"},
     "releaseDate": "2026-09-05",
     "creator": {"id": "c2", "name": "GrokLab", "logo": "/img/logos/unknown_vendor.svg"}},
]


@pytest.fixture
def fake_scored() -> list[dict]:
    return [dict(r) for r in FAKE_SCORED]


@pytest.fixture
def fake_registry() -> list[dict]:
    return [dict(r) for r in FAKE_REGISTRY]
