"""Level 3: 静态 HTML 页面策略

适用于: 服务端渲染的简单 HTML 页面(无 JS 渲染)
"""


class StaticStrategy:
    """静态 HTML 策略骨架(Phase 1 stub)"""

    def __init__(self, url: str = "", headers: dict | None = None, timeout: int = 30):
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout

    def fetch(self) -> str:
        """拉取 HTML 文本(由 collector parse)

        Phase 1 占位。Phase 2 用 httpx + BeautifulSoup 实现。
        """
        raise NotImplementedError(f"StaticStrategy.fetch() 尚未实现. url={self.url}")
