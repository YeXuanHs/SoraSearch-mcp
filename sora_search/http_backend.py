# -*- coding: utf-8 -*-
"""HTTP backend: curl_cffi (Chrome TLS impersonation + cookie session).

Entry is always https://www.bing.com/search; domestic networks 302 to
cn.bing.com automatically. The caller adapts per landing host (www vs cn)
via parser.detect_host. Paging always follows Bing-issued `a.sb_pagN` links.
"""
from __future__ import annotations

import asyncio
import random
from urllib.parse import urlencode

from curl_cffi import requests as creq

from .config import SETTINGS

_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Ch-Ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
}


def build_search_url(query: str, first: int) -> str:
    params = {
        "q": query,
        "setlang": SETTINGS.setlang,
        "ensearch": "0",
        "first": str(first),
    }
    return f"{SETTINGS.search_entry}?{urlencode(params)}"


def build_baidu_url(query: str, pn: int = 0) -> str:
    params = {"wd": query, "pn": str(pn), "ie": "utf-8"}
    return f"{SETTINGS.baidu_entry}?{urlencode(params)}"


class HttpBackend:
    """SERP fetching over an impersonated HTTP session (Bing + Baidu)."""

    name = "http"

    def __init__(self, session: creq.AsyncSession | None = None) -> None:
        self._owns_session = session is None
        self._session = session or creq.AsyncSession(
            impersonate="chrome", timeout=SETTINGS.http_timeout
        )
        self._session.headers.update(_HEADERS)
        self._session.headers.setdefault("User-Agent", SETTINGS.user_agent)

    async def fetch(
        self, url: str, referer: str | None = None, engine: str = "bing"
    ) -> tuple[str, str]:
        """GET a SERP URL; returns (html, effective_url). Retries transient errors."""
        last_err: Exception | None = None
        for attempt in range(1 + SETTINGS.retry_times):
            try:
                headers = {"Referer": referer} if referer else None
                # small jitter between requests inside the retry loop too
                if attempt:
                    await asyncio.sleep(0.5 + random.random())
                resp = await self._session.get(
                    url, headers=headers, allow_redirects=True, max_redirects=5
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"{engine} HTTP {resp.status_code} for {url[:120]}")
                return resp.text, str(resp.url)
            except Exception as exc:  # noqa: BLE001 - retried, then raised
                last_err = exc
        assert last_err is not None
        raise last_err

    async def aclose(self) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None  # type: ignore[assignment]
