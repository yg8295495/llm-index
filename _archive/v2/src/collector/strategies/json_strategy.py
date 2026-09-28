"""Level 2: 官方 JSON 端点策略

适用于: 静态 JSON / JSONP / swebench.com 那种嵌入 <script> 的 JSON
"""


class JsonStrategy:
    """JSON 端点策略骨架(Phase 1 stub)"""

    def __init__(self, url: str = "", headers: dict | None = None, timeout: int = 30):
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout

    def fetch(self) -> dict | list:
        """拉取并解析 JSON,返回 dict 或 list

        Phase 1 占位。Phase 2 用 httpx 或 Playwright getElementById 实现。
        """
        raise NotImplementedError(f"JsonStrategy.fetch() 尚未实现. url={self.url}")
