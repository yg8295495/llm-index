"""测试 API 接口 (v5, 2026-09-20)

维度数量、预设个数这类期望值全部从 config/ 推导, 配置改版时测试自动跟随,
不再像 v3 测试那样把 "4 维 / developer 预设" 写死后集体变红。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import router
from src.collector.registry import BenchmarkRegistry


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestConfigEndpoints:
    def test_health_check(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_list_dimensions_matches_config(self, client, scoring_dims):
        r = client.get("/dimensions")
        assert r.status_code == 200
        data = r.json()
        assert {d["key"] for d in data} == set(scoring_dims)
        for d in data:
            assert d["name"], f"维度 {d['key']} 缺中文名"
            assert d["sources"], f"维度 {d['key']} 没有任何数据源"

    def test_dimension_weights_sum_to_one(self, client):
        data = client.get("/dimensions").json()
        assert abs(sum(d["weight"] for d in data) - 1.0) < 1e-6

    def test_list_sources_covers_registry(self, client, benchmarks_cfg):
        data = client.get("/sources").json()
        keys = {s["key"] for s in data}
        expected = set()
        for dim_key, dim in benchmarks_cfg["dimensions"].items():
            if dim_key == "tags":
                continue
            expected |= set((dim.get("sources") or {}).keys())
        assert expected <= keys, f"接口漏报数据源: {expected - keys}"
        for s in data:
            assert s["name"]
            assert s["dimension"]

    def test_sources_filter_by_dimension(self, client, scoring_dims):
        for dim in scoring_dims:
            data = client.get(f"/sources?dimension={dim}").json()
            assert {s["dimension"] for s in data} == {dim}

    def test_list_presets_matches_config(self, client, settings):
        data = client.get("/presets").json()
        assert set(data.keys()) == set(settings["presets"].keys())
        for name, p in data.items():
            assert p["weights"], f"预设 {name} 无权重"
            assert abs(sum(p["weights"].values()) - 1.0) < 1e-6

    def test_get_weights_default_valid(self, client, scoring_dims):
        data = client.get("/weights").json()
        assert data["valid"] is True
        assert abs(data["sum"] - 1.0) < 1e-6
        assert set(data["weights"].keys()) == set(scoring_dims)

    def test_get_weights_by_preset(self, client, settings, scoring_dims):
        name = next(iter(settings["presets"]))
        data = client.get(f"/weights?preset_name={name}").json()
        assert data["preset_name"] == name
        assert data["valid"] is True
        assert set(data["weights"].keys()) == set(scoring_dims)


class TestDataEndpoints:
    def test_models_endpoint_returns_list(self, client):
        r = client.get("/models")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_radar_indicator_count_matches_dims(self, client, scoring_dims):
        r = client.get("/radar?model_ids=openai/gpt-5.6-terra")
        assert r.status_code == 200
        data = r.json()
        assert "indicator" in data and "series" in data
        assert len(data["indicator"]) == len(scoring_dims)

    def test_registry_and_api_agree(self, client):
        """接口与 registry 必须同源, 不能再出现两套维度定义"""
        api_dims = {d["key"] for d in client.get("/dimensions").json()}
        assert api_dims == set(BenchmarkRegistry.list_dimensions())
