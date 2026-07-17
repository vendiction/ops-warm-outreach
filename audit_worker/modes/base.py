"""Shared base for the three audit modes. Handles the stealth browser lifecycle
(patchright, imported lazily) and resilient helpers for the site-agnostic bits:
finding the email field, clicking a button by likely text. Site DOMs vary wildly, so
these are best-effort heuristics — expect per-vertical tuning once real audits run."""
from config import get_config

_EMAIL_SELECTORS = [
    'input[type="email"]',
    'input[name*="email" i]',
    'input[id*="email" i]',
    'input[placeholder*="email" i]',
]


class BaseMode:
    def __init__(self, funnel_url: str, inbox_email: str, proxy_url: str = "",
                 form_selector: str | None = None) -> None:
        self.funnel_url = funnel_url
        self.inbox_email = inbox_email
        self.proxy_url = proxy_url
        self.form_selector = form_selector

    async def run(self) -> None:
        from patchright.async_api import async_playwright  # lazy: keeps import light
        cfg = get_config()
        proxy = {"server": self.proxy_url} if self.proxy_url else None
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=cfg.headless, proxy=proxy)
            try:
                context = await browser.new_context(
                    locale="en-US",
                    viewport={"width": 1366, "height": 900},
                )
                page = await context.new_page()
                page.set_default_timeout(cfg.nav_timeout_ms)
                await self._flow(page)
            finally:
                await browser.close()

    async def _flow(self, page) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    # ---- helpers ----
    async def _goto(self, page, url: str) -> None:
        await page.goto(url, wait_until="domcontentloaded")

    async def _fill_first_email(self, page) -> bool:
        """Fill the first visible email input. Returns True if one was found."""
        selectors = ([self.form_selector + " input"] if self.form_selector else []) + _EMAIL_SELECTORS
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if await el.count() and await el.is_visible():
                    await el.fill(self.inbox_email)
                    return True
            except Exception:
                continue
        return False

    async def _click_text(self, page, options: list[str]) -> bool:
        """Click the first button/link whose text matches any option (case-insensitive)."""
        for text in options:
            try:
                btn = page.get_by_role("button", name=__import__("re").compile(text, __import__("re").I)).first
                if await btn.count():
                    await btn.click()
                    return True
                link = page.get_by_role("link", name=__import__("re").compile(text, __import__("re").I)).first
                if await link.count():
                    await link.click()
                    return True
            except Exception:
                continue
        return False

    async def _submit(self, page) -> bool:
        return await self._click_text(page, [
            "submit", "sign up", "subscribe", "get", "join", "continue", "next", "send", "download",
        ])
