# -*- coding: utf-8 -*-
"""Configuration for SoraSearch-mcp (env-overridable)."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # entry points
    search_entry: str = os.environ.get("SORA_BING_ENTRY", "https://www.bing.com/search")
    baidu_entry: str = os.environ.get("SORA_BAIDU_ENTRY", "https://www.baidu.com/s")
    market: str = os.environ.get("SORA_MKT", "zh-CN")
    setlang: str = os.environ.get("SORA_SETLANG", "zh-CN")
    user_agent: str = os.environ.get(
        "SORA_UA",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    )

    http_timeout: int = _env_int("SORA_HTTP_TIMEOUT", 25)
    max_pages_per_call: int = _env_int("SORA_MAX_PAGES", 5)
    page_delay: float = _env_float("SORA_PAGE_DELAY", 1.2)  # seconds between pages
    retry_times: int = _env_int("SORA_RETRY", 2)

    # browser backend (Playwright persistent profile)
    browser_profile: str = os.environ.get("SORA_BROWSER_PROFILE", "sora_profile")
    browser_headless: bool = os.environ.get("SORA_BROWSER_HEADLESS", "1") != "0"
    browser_timeout: int = _env_int("SORA_BROWSER_TIMEOUT", 30000)

    # default backend order
    backends: str = os.environ.get("SORA_BACKENDS", "http,browser")


SETTINGS = Settings()
