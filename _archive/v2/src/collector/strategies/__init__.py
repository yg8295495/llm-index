"""Collector 采集策略 — 4 级优先级

Level 1: 官方 API(GET/POST REST 或 GraphQL)
Level 2: 官方 JSON 端点(返回 application/json,无身份验证或简单 API key)
Level 3: 静态 HTML 页面(requests + BeautifulSoup 即可)
Level 4: Playwright 渲染(JS-heavy / 反爬场景)

每个策略暴露一个 fetch() 接口,返回原始数据(由 collector 自己 parse)。
Phase 1 只有骨架,具体实现在 P1 / P2 阶段填充。
"""

from .api import ApiStrategy
from .json_strategy import JsonStrategy
from .playwright import PlaywrightStrategy
from .static import StaticStrategy

__all__ = ["ApiStrategy", "JsonStrategy", "StaticStrategy", "PlaywrightStrategy"]
