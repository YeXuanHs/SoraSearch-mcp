# -*- coding: utf-8 -*-
"""Parse Bing SERP HTML.

Dual adaptation (per 302 landing host):
  - cn.bing.com : result links are usually direct URLs.
  - www.bing.com: result links may be `/ck/a?...&u=a1<base64>` jump links;
    the real target is decoded from the `u` parameter ("a1" prefix + base64).

Both flavours share the same DOM contract, verified live on 2026-10-10:
  results : `li.b_algo` under `#b_results` (10 per page)
  title   : `h2` / `h2 a`
  snippet : `.b_caption p` (fallback: first `p` in the item)
  pager   : `.sb_pagS` = current page marker, `a.sb_pagN` = issued next link
  total   : `.sb_count`
"""
from __future__ import annotations

import base64
import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from .models import SoraPage, SoraResult, HostKind

_SNIPPET_SELECTORS = (".b_caption p", ".b_caption", "p")

# "2026年9月7日 · snippet..." / "3 天之前 · snippet..." -> date + snippet
_DATE_SPLIT_RE = re.compile(r"^(.{1,40}?)\s*[·•]\s*(.+)$", re.S)
_DATE_LIKE_RE = re.compile(
    r"(\d{4}\s*年|\d+\s*(秒|分钟|小时|天|周|个月|月|年)\s*(之前|前)|昨天|前天|今天)"
)

_BOT_TITLE_RE = re.compile(
    r"captcha|verify you are|human verification|access denied|too many requests"
    r"|验证|人机|请验证",
    re.I,
)
_BOT_SELECTORS = (
    "#b_captcha, .b_captcha, "
    "iframe[src*=captcha], form[action*=validate], input[name*=captcha]"
)


def detect_host(url_or_host: str) -> HostKind:
    """Classify the SERP host as www / cn / unknown. cn must be checked first."""
    host = (url_or_host or "").strip().lower()
    if "://" in host:
        try:
            host = urlparse(host).hostname or host
        except Exception:
            pass
    if host == "cn.bing.com" or host.endswith(".cn.bing.com"):
        return "cn"
    if host == "bing.com" or host.endswith(".bing.com"):
        return "www"
    return "unknown"


def decode_ck_href(href: str) -> str:
    """Decode a Bing `/ck/a` jump link to its real target.

    Verified live: the `u` query value is `a1` + base64(target).
    Returns `href` unchanged when it is not a decodable ck link.
    """
    if not href or "/ck/" not in href:
        return href
    try:
        values = parse_qs(urlparse(href).query).get("u") or []
    except Exception:
        return href
    if not values:
        return href
    token = values[0]
    if len(token) < 3 or not token.startswith("a1"):
        return href
    b64 = token[2:]
    b64 += "=" * (-len(b64) % 4)
    try:
        decoded = base64.b64decode(b64).decode("utf-8", errors="replace").strip()
    except Exception:
        return href
    if decoded and ("://" in decoded or decoded.startswith("/")):
        return decoded
    return href


def is_bot_page(html: str) -> bool:
    """True when Bing served a verification / anti-bot page instead of results."""
    if not html:
        return True
    soup = BeautifulSoup(html, "lxml")
    if soup.select_one(_BOT_SELECTORS):
        return True
    title = soup.title.get_text(strip=True) if soup.title else ""
    has_results = bool(soup.select("#b_results li.b_algo") or soup.select("li.b_algo"))
    return (not has_results) and bool(_BOT_TITLE_RE.search(title))


def extract_next_url(html: str, base_url: str) -> str | None:
    """Return the Bing-issued next-page URL (absolute), or None."""
    soup = BeautifulSoup(html, "lxml")
    el = soup.select_one("a.sb_pagN")
    href = (el.get("href") or "").strip() if el else ""
    if not href:
        return None
    return urljoin(base_url, href)


def _split_date(snippet: str) -> tuple[str, str]:
    m = _DATE_SPLIT_RE.match(snippet)
    if m and _DATE_LIKE_RE.search(m.group(1)):
        return m.group(1).strip(), m.group(2).strip()
    return "", snippet


def parse_page(
    html: str,
    *,
    base_url: str,
    query: str,
    page: int,
    first: int,
) -> SoraPage:
    """Parse one SERP document into a SoraPage (page-local ranks 1..N)."""
    soup = BeautifulSoup(html, "lxml")
    host = detect_host(base_url)

    items = soup.select("#b_results li.b_algo") or soup.select("li.b_algo")
    results: list[SoraResult] = []
    for index, li in enumerate(items, start=1):
        h2 = li.select_one("h2")
        if not h2:
            continue
        anchor = h2.select_one("a[href]")
        title = h2.get_text(separator=" ", strip=True)
        raw_href = (anchor.get("href") or "").strip() if anchor else ""
        url = decode_ck_href(raw_href)
        if url.startswith("/") and not url.startswith("//"):
            url = urljoin(base_url, url)
        if not title or not url or url.startswith("javascript:"):
            continue
        snippet = ""
        for selector in _SNIPPET_SELECTORS:
            el = li.select_one(selector)
            if el:
                snippet = el.get_text(separator=" ", strip=True)
                if snippet:
                    break
        date, snippet = _split_date(snippet)
        try:
            domain = urlparse(url).hostname or ""
        except Exception:
            domain = ""
        results.append(
            SoraResult(
                rank=index,
                page=page,
                title=title,
                url=url,
                domain=domain,
                snippet=snippet,
                date=date,
                raw_href=raw_href,
            )
        )

    cur_el = soup.select_one(".sb_pagS")
    cur_page_text = cur_el.get_text(strip=True) if cur_el else ""
    total_el = soup.select_one(".sb_count")
    total_text = total_el.get_text(separator=" ", strip=True) if total_el else ""

    answers: list[str] = []
    for box in soup.select(".b_ans")[:3]:
        text = box.get_text(separator=" ", strip=True)
        if text:
            answers.append(text[:400])

    return SoraPage(
        query=query,
        page=page,
        first=first,
        url=base_url,
        host=host,
        results=results,
        cur_page_text=cur_page_text,
        total_text=total_text,
        answers=answers,
        next_url=extract_next_url(html, base_url),
        bot=is_bot_page(html),
    )
