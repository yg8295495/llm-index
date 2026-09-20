"""测试榜单计分 (2026-09-20)

双榜口径: 能力榜不计成本, 性价比榜 = 能力分 ÷ 混合单价, 综合榜随权重变。
这些测试锁住"分数不会出界、参照模型不占榜内标尺、preference 空时自动重归一"。
"""


from src.compute.scoring import (
    best_per_model, blended_price, build_scores, normalize_dim,
)

GROUPS = {
    "factual": ["aa_omniscience", "gpqa"],
    "workflow": ["gdpval_aa"],
    "engineering": ["scicode"],
    "cost": ["cost_per_eval", "pricing"],
    "preference": ["lmarena_text"],
}
META = {
    "aa_omniscience": {"direction": "higher"}, "gpqa": {"direction": "higher"},
    "gdpval_aa": {"direction": "higher"}, "scicode": {"direction": "higher"},
    "cost_per_eval": {"direction": "lower"}, "pricing": {"direction": "lower"},
    "lmarena_text": {"direction": "higher"},
}


def _models():
    return {
        "openai/a": {"in_scope": True, "pricing_input": 2.0, "pricing_output": 10.0},
        "openai/b": {"in_scope": True, "pricing_input": 0.5, "pricing_output": 2.0},
        "zhipu/c": {"in_scope": True, "pricing_input": 0.2, "pricing_output": 0.8},
        "xai/ref": {"in_scope": False, "pricing_input": 1.0, "pricing_output": 5.0},
    }


def _benchmarks(with_pref=False):
    b = {
        # a 最强但最贵; c 最弱但最便宜; b 居中
        # omniscience 含负值, 检验 min-max 不出界
        "aa_omniscience": [
            {"model_id": "openai/a", "score_raw": 43.7},
            {"model_id": "openai/b", "score_raw": 0.0},
            {"model_id": "zhipu/c", "score_raw": -49.2},
            {"model_id": "xai/ref", "score_raw": 99.0},
        ],
        "gpqa": [
            {"model_id": "openai/a", "score_raw": 0.96},
            {"model_id": "openai/b", "score_raw": 0.90},
            {"model_id": "zhipu/c", "score_raw": 0.75},
        ],
        "gdpval_aa": [
            {"model_id": "openai/a", "score_raw": 1700.0},
            {"model_id": "openai/b", "score_raw": 1500.0},
            {"model_id": "zhipu/c", "score_raw": 1400.0},
        ],
        "scicode": [
            {"model_id": "openai/a", "score_raw": 0.60},
            {"model_id": "openai/b", "score_raw": 0.40},
            # c 在工程能力上最强: 否则 min-max 下它每个维度都是 0,
            # 能力分归零会让"性价比"退化成 0 而测不出价格的作用
            {"model_id": "zhipu/c", "score_raw": 0.70},
        ],
    }
    if with_pref:
        b["lmarena_text"] = [
            {"model_id": "openai/a", "score_raw": 1450.0},
            {"model_id": "openai/b", "score_raw": 1400.0},
            {"model_id": "zhipu/c", "score_raw": 1300.0},
        ]
    return b


def _settings():
    return {
        "weights": {"factual": 0.25, "workflow": 0.25, "engineering": 0.20,
                    "cost": 0.15, "preference": 0.15},
        "weights_no_preference": {"factual": 0.29, "workflow": 0.29, "engineering": 0.24,
                                  "cost": 0.18, "preference": 0.0},
        "normalization": {"method": "min-max", "min_score": 0, "max_score": 100},
        "leaderboards": {
            "capability": {"name": "能力榜", "dimensions": {"factual": 0.25, "workflow": 0.25,
                                                            "engineering": 0.20, "preference": 0.15}},
            "value": {"name": "性价比榜", "formula": "capability_score / blended_price_per_1m",
                      "floor_price": 0.01},
            "composite": {"name": "综合榜"},
        },
        "_bench_groups": GROUPS,
    }


def test_scores_are_within_bounds(settings):
    scores, _ = build_scores(_models(), _benchmarks(), META, _settings())
    for mid, s in scores.items():
        for k in ("capability", "cost", "composite", "value"):
            v = s.get(k)
            assert v is None or 0 <= v <= 100, f"{mid}.{k}={v} 出界"


def test_capability_ranking_ignores_price():
    scores, _ = build_scores(_models(), _benchmarks(), META, _settings())
    assert scores["openai/a"]["capability"] > scores["openai/b"]["capability"]
    assert scores["openai/b"]["capability"] > scores["zhipu/c"]["capability"]


def test_value_ranking_inverts_capability_ranking():
    """最便宜的弱模型应在性价比榜赢过最贵的强模型 —— 这正是拆双榜的理由"""
    scores, _ = build_scores(_models(), _benchmarks(), META, _settings())
    assert scores["zhipu/c"]["value"] > scores["openai/a"]["value"]
    assert scores["openai/a"]["capability"] > scores["zhipu/c"]["capability"]


def test_reference_model_does_not_set_the_scale():
    """xai/ref 的 omniscience=99 高于所有核心模型, 但榜内相对分必须以核心模型为标尺:
    核心最强者 openai/a 拿 100。"""
    scores, _ = build_scores(_models(), _benchmarks(), META, _settings())
    assert scores["openai/a"]["dims"]["factual"] > 60
    assert scores["xai/ref"]["ranked"] is False


def test_cost_only_model_gets_no_composite():
    """只有成本维的模型不得产出"综合指数"。

    混元 Hy4 preview 没有任何 AA 同口径评测 (changelog #39), 若 cost-only 也能求加权
    平均, 它会拿到 94.84 的综合分排到 GPT-5.6 Sol (76.3) 之前 —— 一个纯成本数字
    被当成了能力结论。
    """
    models = _models()
    models["tencent/hy4-preview"] = {"in_scope": False, "pricing_input": 0.834,
                                     "pricing_output": 2.501}
    scores, _ = build_scores(models, _benchmarks(), META, _settings())
    r = scores["tencent/hy4-preview"]
    assert r["cost"] is not None, "成本维本身仍应可算, 它只是不构成综合分"
    assert r["composite"] is None
    assert r["capability"] is None
    assert r["value_raw"] is None, "没有能力分就不能编出性价比"


def test_reference_model_is_still_scored_on_the_core_scale():
    """参照模型不是空壳: 它要在核心模型定的同一把尺子上拿到可比的分,
    只是不占名次。否则前端「含参照模型」开关打开后全是破折号, 用户无法判断。"""
    scores, _ = build_scores(_models(), _benchmarks(), META, _settings())
    ref = scores["xai/ref"]
    assert ref["ranked"] is False
    assert ref["dims"]["factual"] == 100.0, "ref 的 omniscience=99 超过核心最大值, 应钳到 100"
    assert ref["capability"] is not None, "参照模型应拿到能力分"
    assert ref["blended_price"] is not None
    assert ref["value"] is not None


def test_negative_index_is_normalized_without_negative_output():
    scores, _ = build_scores(_models(), _benchmarks(), META, _settings())
    assert scores["zhipu/c"]["dims"]["factual"] >= 0
    assert scores["openai/a"]["dims"]["factual"] > scores["zhipu/c"]["dims"]["factual"]


def test_preference_empty_reweights():
    scores, explain = build_scores(_models(), _benchmarks(False), META, _settings())
    assert explain["preference_status"] == "empty_reweighted"
    assert "preference" not in explain["weights_in_effect"]
    assert abs(sum(explain["weights_in_effect"].values()) - 1.0) < 1e-6


def test_preference_present_changes_status():
    scores, explain = build_scores(_models(), _benchmarks(True), META, _settings())
    assert explain["preference_status"] == "present"


def test_capability_weights_renormalized_over_available_dims():
    _scores, explain = build_scores(_models(), _benchmarks(), META, _settings())
    cw = explain["capability_weights"]
    assert set(cw) == {"factual", "workflow", "engineering"}
    # explain 里的权重保留 4 位小数, 求和只能按展示精度断言
    assert abs(sum(cw.values()) - 1.0) < 1e-3


def test_universe_reported():
    _s, explain = build_scores(_models(), _benchmarks(), META, _settings())
    assert explain["universe"] == "core_only"
    assert explain["universe_size"] == 3


def test_blended_price_uses_documented_ratio():
    assert blended_price({"pricing_input": 2.0, "pricing_output": 10.0}) == 4.0
    assert blended_price({"pricing_input": None, "pricing_output": 1.0}) is None


def test_best_variant_is_taken_per_model():
    rows = [{"model_id": "m", "score_raw": 10.0}, {"model_id": "m", "score_raw": 42.0},
            {"model_id": "n", "score_raw": 30.0}]
    assert best_per_model(rows, {"m", "n"}, reverse=False) == {"m": 42.0, "n": 30.0}
    assert best_per_model(rows, {"m", "n"}, reverse=True) == {"m": 10.0, "n": 30.0}


def test_normalize_dim_counts_coverage():
    scores, covered = normalize_dim("factual", GROUPS, _benchmarks(), META, {"openai/a", "openai/b"})
    assert covered["openai/a"] == 2
    assert all(0 <= v <= 100 for v in scores.values())
