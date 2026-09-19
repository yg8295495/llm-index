"""Level 1: 官方 REST/GraphQL API 策略

适用于: OpenAI / Anthropic / DeepSeek 等官方 API
"""


class ApiStrategy:
    """官方 API 策略骨架(Phase 1 stub)"""

    def __init__(self, base_url: str = "", headers: dict | None = None, timeout: int = 30):
        self.base_url = base_url
        self.headers = headers or {}
        self.timeout = timeout

    def fetch(self, endpoint: str = "", method: str = "GET", **kwargs):
        """执行请求并返回原始响应数据(由 collector parse)

        Phase 1 占位。Phase 2 用 httpx 实现。
        """
        raise NotImplementedError(
            f"ApiStrategy.fetch() 尚未实现. endpoint={endpoint}, method={method}"
        )
