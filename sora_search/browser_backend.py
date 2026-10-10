# -*- coding: utf-8 -*-
"""Browser backend: Playwright persistent Chromium profile.

Used when the HTTP backend hits Bing's soft paging limit (Bing ignores the
paging parameter and re-serves page 1). The persistent profile accumulates
session trust across runs; a brand-new profile may still be limited at first.
"""
from __future__ import annotations

import asyncio
import sys

from .config import SETTINGS


class BrowserBackend:
    """Fetch SERP HTML through a persistent Chromium profile (Bing + Baidu)."""

    name = "browser"

    def __init__(
        self,
        profile_dir: str | None = None,
        headless: bool | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        self._profile = profile_dir or SETTINGS.browser_profile
        self._headless = SETTINGS.browser_headless if headless is None else headless
        self._timeout = timeout_ms or SETTINGS.browser_timeout
        self._pw = None
        self._ctx = None
        self._page = None
        self._lock = asyncio.Lock()

    async def _ensure_page(self):  # -> playwright.async_api.Page
        if self._page is not None:
            return self._page
        async with self._lock:
            if self._page is not None:
                return self._page
            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()
            args: list[str] = []
            if not self._headless and sys.platform == "win32":
                # headed but hidden off-screen: fewer bot signals than headless
                args = ["--window-position=-32000,-32000", "--window-size=1440,900"]
            self._ctx = await self._pw.chromium.launch_persistent_context(
                user_data_dir=self._profile,
                headless=self._headless,
                user_agent=SETTINGS.user_agent,
                locale="zh-CN",
                viewport={"width": 1440, "height": 900},
                args=args,
            )
            pages = self._ctx.pages
            self._page = pages[0] if pages else await self._ctx.new_page()
            return self._page

    async def fetch(
        self, url: str, referer: str | None = None, engine: str = "bing"
    ) -> tuple[str, str]:
        """GET a SERP URL; returns (html, effective_url)."""
        # Baidu may land on the safe-verify page: wait for either results or
        # the verify title, then let the parser classify via is_bot_page().
        selector = (
            "#content_left div.result, title"
            if engine == "baidu"
            else "#b_results li.b_algo"
        )
        page = await self._ensure_page()
        async with self._lock:
            last_err: Exception | None = None
            for _ in range(2):
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=self._timeout)
                    await page.wait_for_selector(
                        selector, state="attached", timeout=self._timeout
                    )
                    await page.wait_for_timeout(1200)
                    return await page.content(), page.url
                except Exception as exc:  # noqa: BLE001 - retried, then raised
                    last_err = exc
                    await asyncio.sleep(1.0)
            assert last_err is not None
            raise last_err

    async def aclose(self) -> None:
        try:
            if self._ctx is not None:
                await self._ctx.close()
        finally:
            self._ctx = None
            self._page = None
            if self._pw is not None:
                await self._pw.stop()
                self._pw = None
