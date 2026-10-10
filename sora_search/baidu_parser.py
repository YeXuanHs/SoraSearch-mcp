# -*- coding: utf-8 -*-
"""Parse Baidu SERP HTML (www.baidu.com/s).

Contract verified live on 2026-10-10 (new cosc card layout):
  results : `#content_left div.result` (plain web results only; `result-op`
            cards like AI-summary/wenku/video/baike and ad blocks are skipped)
  title   : `h3` / `h3 a` (text)
  url     : `div.result[mu]` attribute — the real target. The `h3 a[href]`
            is a `/link?url=...` jump link that cannot be decoded offline.
  snippet : `[class*=summary-gap]` (fallback `.cos-line-clamp-2`, `.c-abstract`)
  pager   : `#page strong` = current page marker ("1", "2", ...);
            next = `#page a` whose text contains "下一页" (class names are
            hashed, e.g. `n next_d-g2R`, so match on text + non-empty href)
  total   : `.nums_text` when present (often just "百度为您找到以下结果")

Bot detection: Baidu safe-verify page has title "百度安全验证" and no
`div.result` items; it may also arrive via redirect to `wappass.baidu.com`.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .models import SoraPage, SoraResult, HostKind

_RESULT_SELECTOR = "#content_left div.result"
_SNIPPET_SELECTORS = ("[class*=summary-gap]", ".cos-line-clamp-2", ".c-abstract")

# Baidu glues the date to the snippet without separator:
#   "2025年10月17日安装选项界面..." -> date + snippet
#   "3天前Python入门..."           -> date + snippet
_DATE_PREFIX_RE = re.compile(
    r"^(?P<date>(?:\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)"
    r"|(?:\d+\s*(?:秒|分钟|小时|天|周|个月|月|年)\s*(?:之前|前))"
    r"|(?:昨天|前天|今天))(?P<rest>.+)$",
    re.S,
)

_BOT_TITLE_RE = re.compile(r"百度安全验证|安全验证|captcha|验证码", re.I)


def detect_host(url_or_host: str) -> HostKind:
    """Baidu only has one SERP host; keep the same HostKind contract."""
    host = (url_or_host or "").strip().lower()
    if "://" in host:
        try:
            host = urlparse(host).hostname or host
        except Exception:
            pass
    if host == "baidu.com" or host.endswith(".baidu.com"):
        return "www"
    return "unknown"


def is_bot_page(html: str, effective_url: str = "") -> bool:
    """True when Baidu served the safe-verify page instead of results."""
    if not html:
        return True
    if "wappass.baidu.com" in (effective_url or ""):
        return True
    soup = BeautifulSoup(html, "lxml")
    if soup.select(_RESULT_SELECTOR):
        return False
    title = soup.title.get_text(strip=True) if soup.title else ""
    return bool(_BOT_TITLE_RE.search(title))


def extract_next_url(html: str, base_url: str) -> str | None:
    """Return the Baidu-issued next-page URL (absolute), or None."""
    soup = BeautifulSoup(html, "lxml")
    for anchor in soup.select("#page a"):
        text = anchor.get_text(strip=True)
        href = (anchor.get("href") or "").strip()
        if "下一页" in text and href:
            return urljoin(base_url, href)
    return None


def _split_date(snippet: str) -> tuple[str, str]:
    match = _DATE_PREFIX_RE.match(snippet)
    if match and len(match.group("rest").strip()) >= 4:
        return match.group("date").strip(), match.group("rest").strip()
    return "", snippet


def _is_usable_url(url: str) -> bool:
    if not url or url.startswith("javascript:"):
        return False
    lowered = url.lower()
    # Baidu internal placeholders, never real results.
    if "nourl.ubs.baidu.com" in lowered:
        return False
    return lowered.startswith(("http://", "https://"))


def parse_page(
    html: str,
    *,
    base_url: str,
    query: str,
    page: int,
    first: int,
) -> SoraPage:
    """Parse one Baidu SERP document into a SoraPage (page-local ranks 1..N).

    Reuses the SoraPage/SoraResult models: `first` carries the `pn=` offset,
    `host` is "www" for www.baidu.com (Baidu has no www/cn split).
    """
    soup = BeautifulSoup(html, "lxml")

    results: list[SoraResult] = []
    for element in soup.select(_RESULT_SELECTOR):
        heading = element.select_one("h3")
        if not heading:
            continue
        title = heading.get_text(separator=" ", strip=True)
        # Real target lives in mu=; the anchor href is an opaque /link? jump.
        url = (element.get("mu") or "").strip()
        anchor = heading.select_one("a[href]")
        raw_href = (anchor.get("href") or "").strip() if anchor else ""
        if not _is_usable_url(url):
            # Fallback: direct href (older layout) — skip opaque jump links.
            if raw_href.startswith(("http://", "https://")) and "/link?" not in raw_href:
                url = raw_href
            else:
                continue
        if not title or not url:
            continue
        snippet = ""
        for selector in _SNIPPET_SELECTORS:
            node = element.select_one(selector)
            if node:
                snippet = node.get_text(separator=" ", strip=True)
                if snippet:
                    break
        date, snippet = _split_date(snippet)
        try:
            domain = urlparse(url).hostname or ""
        except Exception:
            domain = ""
        results.append(
            SoraResult(
                rank=len(results) + 1,
                page=page,
                title=title,
                url=url,
                domain=domain,
                snippet=snippet,
                date=date,
                raw_href=raw_href,
            )
        )

    cur_el = soup.select_one("#page strong")
    cur_page_text = cur_el.get_text(strip=True) if cur_el else ""
    total_el = soup.select_one(".nums_text")
    total_text = total_el.get_text(separator=" ", strip=True) if total_el else ""
    if not total_text:
        hint = soup.find("span", string=re.compile(r"为您找到"))
        if hint:
            total_text = hint.get_text(separator=" ", strip=True)

    return SoraPage(
        query=query,
        page=page,
        first=first,
        url=base_url,
        host=detect_host(base_url),
        results=results,
        cur_page_text=cur_page_text,
        total_text=total_text,
        answers=[],
        next_url=extract_next_url(html, base_url),
        bot=is_bot_page(html, base_url),
    )
