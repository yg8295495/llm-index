"""Level 4: Playwright 渲染策略

适用于: JS-heavy 页面 / Cloudflare 防护 / 反爬场景
"""


class PlaywrightStrategy:
    """Playwright 策略骨架(Phase 1 stub)"""

    def __init__(
        self,
        url: str = "",
        headless: bool = True,
        browser_path: str = "",
        user_agent: str = "",
        wait_selector: str | None = None,
        timeout: int = 30000,
    ):
        self.url = url
        self.headless = headless
        self.browser_path = browser_path
        self.user_agent = user_agent
        self.wait_selector = wait_selector
        self.timeout = timeout

    def fetch(self) -> str:
        """渲染后返回 HTML 文本或 DOM(由 collector parse)

        Phase 1 占位。P1 阶段用项目本地 Chrome 实现。
        """
        raise NotImplementedError(f"PlaywrightStrategy.fetch() 尚未实现. url={self.url}")
