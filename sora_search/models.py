# -*- coding: utf-8 -*-
"""Data models for SoraSearch-mcp."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

HostKind = Literal["www", "cn", "unknown"]


@dataclass
class SoraResult:
    """One organic search result."""

    rank: int          # global rank within this call (1-based, after dedupe)
    page: int          # SERP page number (1-based)
    title: str
    url: str           # resolved real URL (/ck/ jump links decoded)
    domain: str = ""
    snippet: str = ""
    date: str = ""     # leading date prefix when Bing prepends one ("3 天之前 · ...")
    raw_href: str = ""  # original href attribute in the DOM

    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "page": self.page,
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "snippet": self.snippet,
            "date": self.date,
        }


@dataclass
class SoraPage:
    """One parsed SERP page (Bing or Baidu — same shape)."""

    query: str
    page: int          # logical page number we believe this is (1-based)
    first: int         # paging offset used/requested (`first=` for Bing, `pn=` for Baidu)
    url: str           # effective URL the HTML came from
    host: HostKind
    results: list[SoraResult] = field(default_factory=list)
    cur_page_text: str = ""   # engine's own current-page marker ("1", "2", ...)
    total_text: str = ""      # total hint (Bing `.sb_count` / Baidu `.nums_text`)
    answers: list[str] = field(default_factory=list)  # Bing `.b_ans` boxes, truncated
    next_url: str | None = None  # engine-issued next-page URL (absolute), if any
    bot: bool = False


@dataclass
class SearchResponse:
    """Assembled multi-page search response."""

    query: str
    backend: str       # "http" or "browser"
    host: HostKind
    total_text: str
    requested_page: int
    requested_pages: int
    pages: list[SoraPage] = field(default_factory=list)
    results: list[SoraResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    complete: bool = True  # False when fewer than the requested pages verified
    engine: str = "bing"   # "bing" or "baidu"

    @property
    def pages_fetched(self) -> list[int]:
        return [p.page for p in self.pages]

    @property
    def has_next(self) -> bool:
        return bool(self.pages and self.pages[-1].next_url)

    @property
    def next_page(self) -> int | None:
        return (self.pages[-1].page + 1) if self.has_next else None

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "engine": self.engine,
            "backend": self.backend,
            "host": self.host,
            "total": self.total_text,
            "requested": {"page": self.requested_page, "pages": self.requested_pages},
            "pages_fetched": self.pages_fetched,
            "has_next": self.has_next,
            "next_page": self.next_page,
            "result_count": len(self.results),
            "complete": self.complete,
            "warnings": self.warnings,
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
