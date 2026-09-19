"""测试计算层 (v5, 2026-09-20)

期望值来自 config/, 不再在测试里重述维度名与权重。
"""

import pytest

from src.compute import IndexCalculator, Normalizer, WeightManager


class TestNormalizer:
    def test_minmax_endpoints(self):
        n = Normalizer()
        out = n.normalize_minmax([0, 50, 100])
        assert out == [0, 50, 100]

    def test_minmax_reverse_for_cost(self):
        n = Normalizer()
        out = n.normalize_minmax([0, 50, 100], reverse=True)
        assert out[0] == 100 and out[-1] == 0

    def test_minmax_is_bounded_with_negative_input(self):
        """回归测试: AA-Omniscience 指数可为负 (本批次 -49.25 ~ 43.73)。

        前端旧实现用 best/max*100 的比值法, 在负值上会算出负得分甚至把名次算反。
        Python 侧必须始终是 min-max 且落在 [0, 100]。
        """
        n = Normalizer()
        vals = [-49.25, -12.5, 0.8, 43.73]
        out = n.normalize_minmax(vals)
        assert all(0 <= v <= 100 for v in out)
        assert out == sorted(out)
        assert out[0] == 0 and out[-1] == 100

    def test_all_equal_gives_midpoint(self):
        n = Normalizer()
        assert n.normalize_minmax([7, 7, 7]) == [50, 50, 50]

    def test_empty_input(self):
        n = Normalizer()
        assert n.normalize_minmax([]) == []
        assert n.normalize_zscore([]) == []

    def test_dimension_drives_reversal(self, scoring_dims):
        n = Normalizer()
        scores = {"a": 1.0, "b": 2.0}
        assert n.normalize_scores(scores, "cost") == {"a": 100.0, "b": 0.0}
        assert n.normalize_scores(scores, "factual") == {"a": 0.0, "b": 100.0}

    def test_respects_config_bounds(self, settings):
        cfg = settings["normalization"]
        n = Normalizer(cfg)
        out = n.normalize_minmax([10, 20])
        assert set(out) == {cfg["min_score"], cfg["max_score"]}


class TestWeightManager:
    def test_default_weights_match_config_dimensions(self, scoring_dims):
        wm = WeightManager()
        weights = wm.get_weights()
        assert set(weights.keys()) == set(scoring_dims)
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_weights_no_preference_renormalized(self, scoring_dims):
        wm = WeightManager()
        w = wm.get_weights_no_preference()
        assert set(w.keys()) == set(scoring_dims)
        assert w.get("preference") == 0.0
        assert abs(sum(w.values()) - 1.0) < 0.01

    def test_validate_weights(self, scoring_dims):
        wm = WeightManager()
        good = {d: 1 / len(scoring_dims) for d in scoring_dims}
        good[list(scoring_dims)[0]] += 1 - sum(good.values())
        assert wm.validate_weights(good) is True
        assert wm.validate_weights({d: 0.1 for d in scoring_dims}) is False
        assert wm.validate_weights({}) is False

    def test_presets_exist_and_are_valid(self, settings, scoring_dims):
        presets = settings["presets"]
        assert len(presets) >= 5, "前端「我的方案」依赖预设"
        for name, p in presets.items():
            assert "weights" in p, f"预设 {name} 缺 weights"
            assert set(p["weights"].keys()) == set(scoring_dims), f"预设 {name} 维度不齐"
            assert abs(sum(p["weights"].values()) - 1.0) < 1e-6, f"预设 {name} 权重和不为 1"
            assert "description" in p, f"预设 {name} 缺描述"

    def test_get_weights_by_preset(self, settings, scoring_dims):
        wm = WeightManager()
        first = next(iter(settings["presets"]))
        assert set(wm.get_weights(first).keys()) == set(scoring_dims)

    def test_unknown_preset_falls_back_to_default(self):
        wm = WeightManager()
        assert wm.get_weights("不存在的预设") == wm.get_weights()

    def test_config_loads_regardless_of_cwd(self, tmp_path, monkeypatch):
        """回归测试: WeightManager 原来用 CWD 相对路径读配置, 换目录就跑不通。"""
        monkeypatch.chdir(tmp_path)
        wm = WeightManager()
        assert wm.weights, "在别的工作目录下也应能读到 config/settings.yaml"


class TestIndexCalculator:
    def test_composite_index_weighted_sum(self, scoring_dims):
        calc = IndexCalculator()
        scores = {d: {"m1": 80.0, "m2": 60.0} for d in scoring_dims}
        weights = {d: 1 / len(scoring_dims) for d in scoring_dims}
        out = calc.calculate_composite_index(scores, weights)
        assert out["m1"] == pytest.approx(80.0)
        assert out["m2"] == pytest.approx(60.0)

    def test_rank_models_orders_desc(self):
        calc = IndexCalculator()
        ranking = calc.rank_models({"a": 50.0, "b": 90.0, "c": 70.0})
        # 返回形状为 (名次, model_id, 综合指数)
        assert [mid for _, mid, _ in ranking] == ["b", "c", "a"]
        assert [rk for rk, _, _ in ranking] == [1, 2, 3]
        assert ranking[0][2] == 90.0

    def test_rank_models_top_n(self):
        calc = IndexCalculator()
        assert len(calc.rank_models({"a": 1.0, "b": 2.0, "c": 3.0}, top_n=2)) == 2

    def test_compare_models_runs(self, scoring_dims):
        """回归: compare_models 内有一处推导式键名先用后定义, 一调用就 NameError。"""
        calc = IndexCalculator()
        scores = {d: {"m1": 80.0, "m2": 60.0} for d in scoring_dims}
        out = calc.compare_models(["m1", "m2"], scores)
        assert set(out["models"]) == {"m1", "m2"}
        assert out["models"]["m1"]["composite_index"] == pytest.approx(80.0)

    def test_missing_dimension_does_not_crash(self, scoring_dims):
        calc = IndexCalculator()
        scores = {d: {"m1": 50.0} for d in scoring_dims[:-1]}
        weights = {d: 1 / len(scoring_dims) for d in scoring_dims}
        out = calc.calculate_composite_index(scores, weights)
        assert "m1" in out and out["m1"] > 0
