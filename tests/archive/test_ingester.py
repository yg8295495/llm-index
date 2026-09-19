"""测试数据采集模块"""

import pytest
from src.ingester import BenchIngester, PriceIngester, AgentIngester


class TestBenchIngester:
    """测试基准数据采集器"""

    def test_init(self):
        """测试初始化"""
        ingester = BenchIngester()
        assert ingester is not None
        assert len(ingester.ingesters) > 0

    @pytest.mark.asyncio
    async def test_ingest_all(self):
        """测试采集所有基准数据"""
        ingester = BenchIngester()
        results = await ingester.ingest_all()
        assert isinstance(results, dict)


class TestPriceIngester:
    """测试价格数据采集器"""

    def test_init(self):
        """测试初始化"""
        ingester = PriceIngester()
        assert ingester is not None
        assert ingester.api_base is not None

    def test_calculate_weighted_price(self):
        """测试加权价格计算"""
        ingester = PriceIngester()
        weighted = ingester.calculate_weighted_price(0.01, 0.02, 0.5)
        assert weighted == 0.015


class TestAgentIngester:
    """测试 Agent 评测数据采集器"""

    def test_init(self):
        """测试初始化"""
        ingester = AgentIngester()
        assert ingester is not None
        assert len(ingester.ingesters) > 0

    def test_aggregate_agent_scores(self):
        """测试聚合 Agent 得分"""
        ingester = AgentIngester()
        eval_results = {
            "test_eval": [
                {"score": 80},
                {"score": 90},
                {"score": 70}
            ]
        }
        aggregated = ingester.aggregate_agent_scores("test_agent", eval_results)
        assert "test_eval" in aggregated
        assert aggregated["test_eval"] == 80.0
