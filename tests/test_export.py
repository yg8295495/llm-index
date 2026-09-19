"""测试导出层与 data.json 契约 (2026-09-20)

分两类:
  1. 纯函数单测 — 导出器的元信息/配置注入逻辑, 不依赖数据库。
  2. 产物契约测试 — 校验 frontend/data.json 的形状与溯源完整性,
     直接防住"前端读不到来源""体积退回 8.6MB"这类回归。
"""

import importlib.util
import json
import math
import re

import pytest

from src.paths import FRONTEND_DATA, ROOT

_spec = importlib.util.spec_from_file_location(
    "export_frontend_data", ROOT / "scripts" / "export_frontend_data.py")
EXP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(EXP)


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------


def test_norm_open_source_buckets():
    assert EXP._norm_open("open") == "Open"
    assert EXP._norm_open("Open weights (permissive license)") == "Open"
    assert EXP._norm_open("Open weights (license required for commercial use)") == "Hybrid"
    assert EXP._norm_open("proprietary") == "Proprietary"
    assert EXP._norm_open(None) == "Proprietary"


def test_bench_meta_covers_every_registered_source(benchmarks_cfg):
    cfg = {"bm": benchmarks_cfg, "st": {}, "vendors": {}}
    meta = EXP.bench_meta(cfg)
    registered = set()
    for dim_key, dim in benchmarks_cfg["dimensions"].items():
        if dim_key == "tags":
            continue
        registered |= set((dim.get("sources") or {}).keys())
    missing = registered - set(meta)
    assert not missing, f"这些已注册数据源没有元信息: {missing}"


def test_bench_meta_emits_both_source_fields():
    """回归: 旧导出器只写 source_url 而前端读 source, 来源标签从未显示过。"""
    cfg = {"bm": EXP.load_config()["bm"], "st": {}, "vendors": {}}
    meta = EXP.bench_meta(cfg)
    for key, m in meta.items():
        assert m.get("source"), f"{key} 缺 source"
        assert m.get("source_url", "").startswith("http"), f"{key} 缺可用 source_url"


def test_frontend_config_injects_weights_and_baseline(settings):
    cfg = EXP.load_config()
    models = {"zhipu/glm-9.9": {"provider": "zhipu", "in_scope": True}}
    fc = EXP.frontend_config(cfg, models)
    assert [d["key"] for d in fc["dimensions"]] == [
        k for k in cfg["bm"]["dimensions"] if k != "tags"]
    assert abs(sum(fc["weights"].values()) - 1.0) < 1e-6
    assert fc["baseline"]["default"] in fc["baseline"]["candidates"]
    assert "zhipu" in fc["providers"], "只暴露数据里真正出现的厂商"
    assert fc["normalization"]["method"] == settings["normalization"]["method"]
    assert set(fc["bench_groups"]["cost"]) == {"cost_per_eval", "pricing"}


def test_blend_assumption_is_documented():
    cfg = EXP.load_config()
    meta = EXP.bench_meta({"bm": cfg["bm"], "st": {}, "vendors": {}})
    assert f"{EXP.BLEND_RATIO_IN}:{EXP.BLEND_RATIO_OUT}" in meta["pricing"]["note"]


def test_cost_metric_is_not_mislabeled_as_per_task():
    """回归: v4 把"跑完整套题的消耗"标成 cost_per_task, 量纲是错的。"""
    cfg = EXP.load_config()
    meta = EXP.bench_meta({"bm": cfg["bm"], "st": {}, "vendors": {}})
    assert "不是「每个任务的成本」" in meta["cost_per_eval"]["note"]


# ---------------------------------------------------------------------------
# 产物契约
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def data():
    if not FRONTEND_DATA.exists():
        pytest.skip("frontend/data.json 尚未生成")
    return json.loads(FRONTEND_DATA.read_text(encoding="utf-8"))


def test_data_json_size_is_small(data):
    size = FRONTEND_DATA.stat().st_size
    assert size < 2_000_000, f"data.json {size/1024/1024:.1f}MB, 访客首屏要整包下载"


def test_top_level_contract(data):
    for key in ("models", "benchmarks", "benchmark_meta", "config", "provenance", "metadata"):
        assert key in data, f"data.json 缺 {key}"


def test_every_benchmark_has_meta(data):
    missing = sorted(set(data["benchmarks"]) - set(data["benchmark_meta"]))
    assert not missing, f"这些 benchmark 没有元信息: {missing}"


def test_every_eval_carries_provenance(data):
    for bench, rows in data["benchmarks"].items():
        for r in rows:
            assert r.get("observed_at"), f"{bench} 有记录缺 observed_at"
            assert (r.get("source_url") or "").startswith("http"), f"{bench} 有记录缺 source_url"
            assert r["score_raw"] is None or (isinstance(r["score_raw"], (int, float))
                                              and math.isfinite(r["score_raw"]))


def test_model_ids_are_clean(data):
    for mid in data["models"]:
        assert "unknown/" not in mid, f"仍有未归属 ID: {mid}"
        assert "unattributed" not in mid, f"仍有未归类 ID: {mid}"
        assert "--" not in mid, f"ID 有重复连字符: {mid}"
        assert re.match(r"^[a-z0-9_]+/[a-z0-9._\-]+$", mid), f"ID 不合规范: {mid}"


def test_scope_flags_present(data):
    core = [m for m in data["models"].values() if m["in_scope"]]
    assert core, "九家范围内一个模型都没有"
    for m in data["models"].values():
        assert m["tier"] in ("core", "reference")
        assert isinstance(m["in_scope"], bool)
        assert m.get("release_date"), f"{m['id']} 缺发布日期"


def test_snapshot_date_and_trail(data):
    md = data["metadata"]
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", md["snapshot_date"])
    assert md["collected_at"], "缺采集时刻"
    assert md["html_sha256"], "缺页面指纹"
    assert len(md["snapshots"]) >= 1
    assert md["core_model_count"] == sum(1 for m in data["models"].values() if m["in_scope"])


def test_provenance_states_the_date_caveat(data):
    p = data["provenance"]
    assert p["leaderboard_url"].startswith("http")
    assert p["dataset_url"], "应给出官方题库链接以便他人复现"
    assert p["paper_url"], "应给出方法学论文链接"
    assert "评测" in p["caveat"], "口径说明必须解释日期含义"
    assert set(p["date_semantics"]) == {"observed_at", "collected_at", "release_date"}


def test_dimension_benches_all_known(data):
    known = set(data["benchmark_meta"])
    for dim, keys in data["config"]["bench_groups"].items():
        for k in keys:
            assert k in known, f"维度 {dim} 引用了未登记的 benchmark {k}"


def test_bench_cn_covers_grouped_benches(data):
    for dim, keys in data["config"]["bench_groups"].items():
        for k in keys:
            assert k in data["config"]["bench_cn"], f"{k} 没有中文名, UI 会显示英文键"


def test_raw_and_derived_eval_counts_add_up(data):
    md = data["metadata"]
    assert md["raw_eval_count"] + md["derived_eval_count"] == md["eval_count"]
    assert md["raw_eval_count"] > 0
    # 快照轨迹里记的是 AA 原始行数, 必须与 raw_eval_count 对得上
    cur = [s for s in md["snapshots"] if s["snapshot_date"] == md["snapshot_date"]]
    assert cur and cur[0]["eval_count"] == md["raw_eval_count"], \
        "采集器回填的快照计数与导出不一致 (changelog #30 的回归锚点)"


def test_scores_are_injected_and_bounded(data):
    assert data["metadata"]["scoring"]["universe_size"] == data["metadata"]["core_model_count"]
    for mid, m in data["models"].items():
        s = m.get("scores")
        assert s, f"{mid} 没有 scores, 榜单视图会空"
        for k in ("capability", "cost", "composite"):
            v = s.get(k)
            assert v is None or 0 <= v <= 100, f"{mid}.{k}={v} 出界"
        if m["in_scope"]:
            assert s["capability"] is not None, f"核心模型 {mid} 缺能力分"


def test_display_name_is_the_base_variant(data):
    """同一模型有 max/high/xhigh 多个档位行时, 模型显示名必须取基座档位,
    否则榜上会出现 'Claude Fable 5.1 (High Effort)' 冒充模型本名。"""
    for mid, m in data["models"].items():
        levels = m["reasoning_levels"]
        if len(levels) < 2:
            continue
        name = m["display_name"]
        if "max" in levels:
            assert "High Effort" not in name and "(high)" not in name, \
                f"{mid} 显示名取到了 high 档位: {name}"


def test_reference_models_are_never_ranked(data):
    for mid, m in data["models"].items():
        if m["in_scope"]:
            continue
        assert m["scores"]["ranked"] is False, f"参照模型 {mid} 不应参与排名"


def test_vendor_official_metrics_never_enter_benchmarks(data):
    """厂商自报数据必须与 AA 同口径数据物理隔离。

    证据: 腾讯官方称 Hy3 在 Terminal-Bench 2.1 得 70.8, AA 实测 64.4。
    若把自报值混进 benchmarks, 归一化就会拿两种口径一起算, 榜面数字即失真。
    """
    official_keys = [k for k in data["benchmarks"] if k.endswith("_official")]
    assert not official_keys, f"自报指标混入了 AA 数据表: {official_keys}"
    with_official = [m for m in data["models"].values() if m.get("official_metrics")]
    for m in with_official:
        for o in m["official_metrics"]:
            assert o["benchmark"].endswith("_official")
            assert (o["source_url"] or "").startswith("http"), "自报数据同样要有来源"
            assert "official" in o["source"]
            assert o["confidence"] <= 0.5, "自报数据置信度必须显式压低"


def test_official_only_model_is_not_scored_as_aa_data(data):
    """只有自报数据、没有 AA 分数的模型: 不得凭空长出能力分。"""
    for mid, m in data["models"].items():
        if m.get("official_metrics") and not m["scores"].get("dims"):
            assert m["scores"].get("capability") is None, f"{mid} 用自报数据算出了榜分"
            assert m["in_scope"] is False, f"{mid} 自报数据模型不应进核心榜"
