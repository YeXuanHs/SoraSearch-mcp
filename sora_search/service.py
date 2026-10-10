# -*- coding: utf-8 -*-
"""Search orchestration: verify real paging, dedupe, assemble SearchResponse.

Works for both engines (Bing + Baidu):
  * Always follow engine-issued next-page links; never hand-build offsets.
  * Verify every page: the engine's own page marker must match the expected
    page number, and URL overlap with previously accepted pages must stay
    below threshold. Both signals catch soft-limits / re-served pages.
  * On soft-limit / bot page in HTTP mode, fall back to the browser backend.
"""
from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from typing import Literal
from urllib.parse import parse_qs, urlparse

from . import baidu_parser, parser as bing_parser
from .browser_backend import BrowserBackend
from .http_backend import HttpBackend, build_baidu_url, build_search_url
from .models import SoraPage, SoraResult, SearchResponse

Engine = Literal["bing", "baidu"]

log = logging.getLogger("sora_search.service")

FIRST_STEP = 10
OVERLAP_LIMIT = 0.6  # >=60% URL overlap with accepted pages => paging ignored


def normalize_url(url: str) -> str:
    """Normalize for dedupe/overlap: lowercase scheme+host, strip fragment/queries kept."""
    text = url.strip()
    try:
        parts = urlparse(text)
    except Exception:
        return text
    if not parts.netloc:
        return text
    scheme = (parts.scheme or "http").lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    if parts.query:
        return f"{scheme}://{netloc}{path}?{parts.query}"
    return f"{scheme}://{netloc}{path}"


def first_of_url(url: str, fallback_page: int, engine: Engine = "bing") -> int:
    """Read the paging offset from an issued URL.

    Bing: `first=` (1-based, e.g. 1/11/21). Baidu: `pn=` (0-based, 0/10/20).
    Falls back to the conventional offset when the parameter is missing.
    """
    param = "pn" if engine == "baidu" else "first"
    try:
        values = parse_qs(urlparse(url).query).get(param) or []
        if values:
            return int(values[0])
    except (ValueError, TypeError):
        pass
    if engine == "baidu":
        return (fallback_page - 1) * FIRST_STEP
    return (fallback_page - 1) * FIRST_STEP + 1


def _engine_parser(engine: Engine) -> Callable[..., SoraPage]:
    return baidu_parser.parse_page if engine == "baidu" else bing_parser.parse_page


def _engine_label(engine: Engine) -> str:
    return "Baidu" if engine == "baidu" else "Bing"


def verify_page(
    expected_page: int,
    page: SoraPage,
    accepted_urls: set[str] | None,
    engine: Engine = "bing",
) -> tuple[bool, list[str]]:
    """Verify a fetched page really is `expected_page`. Returns (ok, reasons)."""
    reasons: list[str] = []
    if page.bot:
        return False, ["bot/verification page"]
    if not page.results:
        reasons.append("no results on page")
    if page.cur_page_text and page.cur_page_text != str(expected_page):
        reasons.append(
            f"{_engine_label(engine)} marker says page {page.cur_page_text}, "
            f"expected page {expected_page}"
        )
    if accepted_urls:
        urls = {normalize_url(r.url) for r in page.results}
        overlap = len(urls & accepted_urls) / max(len(urls), 1)
        if overlap >= OVERLAP_LIMIT:
            reasons.append(
                f"duplicate of previous pages (overlap {overlap:.0%} >= {OVERLAP_LIMIT:.0%})"
            )
    return (len(reasons) == 0), reasons


def dedupe_results(pages: list[SoraPage]) -> list[SoraResult]:
    """Merge accepted pages, dedupe by normalized URL, assign global ranks."""
    seen: set[str] = set()
    merged: list[SoraResult] = []
    for page in pages:
        for item in page.results:
            key = normalize_url(item.url)
            if key in seen:
                continue
            seen.add(key)
            merged.append(
                SoraResult(
                    rank=0,
                    page=page.page,
                    title=item.title,
                    url=item.url,
                    domain=item.domain,
                    snippet=item.snippet,
                    date=item.date,
                    raw_href=item.raw_href,
                )
            )
    for index, item in enumerate(merged, start=1):
        item.rank = index
    return merged


async def _run_pages(
    backend: HttpBackend | BrowserBackend,
    engine: Engine,
    query: str,
    start_page: int,
    start_url: str,
    max_pages: int,
) -> tuple[list[SoraPage], list[str]]:
    """Walk issued next-links from start_url; returns (accepted, warnings)."""
    parse_page = _engine_parser(engine)
    label = _engine_label(engine)
    accepted: list[SoraPage] = []
    accepted_urls: set[str] = set()
    warnings: list[str] = []
    url: str | None = start_url
    referer: str | None = None

    for offset in range(max_pages):
        logical_page = start_page + offset
        assert url is not None
        html, effective_url = await backend.fetch(url, referer, engine=engine)
        page = parse_page(
            html,
            base_url=effective_url,
            query=query,
            page=logical_page,
            first=first_of_url(effective_url, logical_page, engine),
        )
        ok, reasons = verify_page(logical_page, page, accepted_urls or None, engine)
        if not ok:
            warnings.append(
                f"page {logical_page} rejected on {backend.name}: {'; '.join(reasons)}"
            )
            break
        accepted.append(page)
        accepted_urls.update(normalize_url(r.url) for r in page.results)
        if offset < max_pages - 1:
            if not page.next_url:
                warnings.append(f"page {logical_page}: no next-page link issued by {label}")
                break
            referer = effective_url
            url = page.next_url
            await asyncio.sleep(1.0 + random.random())
    return accepted, warnings


async def search(
    query: str,
    page: int = 1,
    pages: int = 1,
    backend: str = "auto",
    backends: list[HttpBackend | BrowserBackend] | None = None,
    engine: Engine = "bing",
) -> SearchResponse:
    """Search an engine and return verified pages + merged results.

    Args:
        query: search keywords.
        page: logical page to start from (1-based; >1 walks issued links).
        pages: how many consecutive verified pages to return (>=1).
        backend: "auto" (http then browser), "http", or "browser".
        backends: optional pre-built backend instances (tests / reuse).
        engine: "bing" or "baidu".
    """
    from .config import SETTINGS

    if engine not in ("bing", "baidu"):
        raise ValueError(f"unknown engine: {engine!r}")

    query = (query or "").strip()
    if not query:
        raise ValueError("query must not be empty")
    page = max(1, int(page))
    pages = min(max(1, int(pages)), SETTINGS.max_pages_per_call)

    order = [b.strip().lower() for b in SETTINGS.backends.split(",") if b.strip()]
    if backend != "auto":
        order = [backend]
    order = [b for b in order if b in ("http", "browser")] or ["http"]

    owned = backends is None
    pool: dict[str, HttpBackend | BrowserBackend] = {}
    if backends is not None:
        for instance in backends:
            pool[instance.name] = instance

    def _get(name: str) -> HttpBackend | BrowserBackend:
        if name not in pool:
            pool[name] = HttpBackend() if name == "http" else BrowserBackend()
        return pool[name]

    all_warnings: list[str] = []
    last_error: Exception | None = None
    best: SearchResponse | None = None
    try:
        for name in order:
            inst = _get(name)
            try:
                # Walk from page 1 to the requested start via issued links so
                # every returned page is verified against the engine's own markers.
                start_url = build_baidu_url(query) if engine == "baidu" else build_search_url(query, 1)
                accepted, warnings = await _run_pages(
                    inst, engine, query, 1, start_url, page + pages - 1
                )
                base_warnings = list(all_warnings)
                if len(accepted) < page:
                    all_warnings.extend(warnings)
                    all_warnings.append(
                        f"{name}: only reached page {len(accepted)}, "
                        f"start page {page} unavailable"
                    )
                    continue
                wanted = accepted[page - 1 : page - 1 + pages]
                backend_warnings = base_warnings + warnings
                if len(wanted) < pages:
                    backend_warnings.append(
                        f"{name}: got {len(wanted)}/{pages} verified page(s) "
                        f"from page {page}"
                    )
                host = max({p.host for p in accepted}, key=lambda h: h != "unknown") if accepted else "unknown"
                total_text = next((p.total_text for p in accepted if p.total_text), "")
                candidate = SearchResponse(
                    query=query,
                    engine=engine,
                    backend=name,
                    host=host,  # type: ignore[arg-type]
                    total_text=total_text,
                    requested_page=page,
                    requested_pages=pages,
                    pages=wanted,
                    results=dedupe_results(wanted),
                    warnings=backend_warnings,
                    complete=(len(wanted) == pages),
                )
                if candidate.complete:
                    return candidate
                # Incomplete: remember the best so far and try the next backend.
                if best is None or len(candidate.results) > len(best.results):
                    best = candidate
                all_warnings = backend_warnings
                continue
            except Exception as exc:  # noqa: BLE001 - fall through to next backend
                last_error = exc
                log.warning("backend %s failed: %s", name, exc)
                all_warnings.append(f"{name} backend failed: {exc}")
                continue
        if best is not None:
            return best
        if all_warnings and last_error is None:
            # All backends walked but could not verify the requested start page
            # (e.g. engine soft-limited paging / bot page). Return an honest
            # empty response instead of raising, so MCP callers get warnings.
            return SearchResponse(
                query=query,
                engine=engine,
                backend="none",
                host="unknown",
                total_text="",
                requested_page=page,
                requested_pages=pages,
                pages=[],
                results=[],
                warnings=all_warnings,
                complete=False,
            )
        raise RuntimeError(
            f"all backends failed ({', '.join(order)}); "
            f"last error: {last_error}; warnings: {'; '.join(all_warnings)}"
        )
    finally:
        if owned:
            for inst in pool.values():
                try:
                    await inst.aclose()
                except Exception:  # noqa: BLE001 - best effort cleanup
                    pass
