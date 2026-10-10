# -*- coding: utf-8 -*-
"""MCP server: web-search (from-scratch Bing + Baidu SERP scrapers).

Tools:
  bing_search / bing_next    - Bing, verified paging
  baidu_search / baidu_next  - Baidu (plain web results), verified paging
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from .config import SETTINGS
from .service import search

server = MCPServer(
    name="sora-search",
    title="Web Search (Bing + Baidu, from scratch)",
    description=(
        "Scrape Bing / Baidu search result pages (title / URL / snippet) with "
        "verified paging. Paging follows engine-issued next links and verifies "
        "every page against the engine's own page marker + URL-overlap check; "
        "when an engine soft-limits paging, the server falls back to the "
        "persistent-browser backend."
    ),
    version="0.2.0",
)


@server.tool(
    description=(
        "Search Bing and return organic results (title, URL, domain, snippet, date) "
        "with verified paging. `page` is the 1-based page to start from, `pages` is "
        "how many consecutive verified pages to return (10 results per page). "
        "Paging follows Bing-issued next links and every page is verified against "
        "Bing's own page marker + URL-overlap check; when Bing soft-limits paging "
        "(re-serves page 1), the server falls back to the persistent-browser backend. "
        "The response includes `pages_fetched`, `has_next`, `next_page`, `warnings` "
        "and a `complete` flag (false when fewer than the requested pages verified)."
    )
)
async def bing_search(query: str, page: int = 1, pages: int = 1, backend: str = "auto") -> str:
    resp = await search(query, page=page, pages=pages, backend=backend or "auto")
    return resp.to_json()


@server.tool(
    description=(
        "Fetch the next page(s) of a previous Bing search. Same as bing_search but "
        "makes paging intent explicit: pass the original query and the 1-based page "
        "number from the previous response's `next_page` field."
    )
)
async def bing_next(query: str, page: int, pages: int = 1, backend: str = "auto") -> str:
    resp = await search(query, page=page, pages=pages, backend=backend or "auto")
    return resp.to_json()


@server.tool(
    description=(
        "Search Baidu (plain web results only: 文库/video/百科 cards and ads are "
        "skipped) and return organic results (title, URL, domain, snippet, date) "
        "with verified paging. `page` is the 1-based page to start from, `pages` is "
        "how many consecutive verified pages to return. Paging follows "
        "Baidu-issued next links (`pn=`) and every page is verified against "
        "Baidu's own page marker + URL-overlap check. Baidu HTTP fetching is "
        "usually blocked by the safe-verify page, so `auto` will fall back to "
        "the persistent-browser backend; the response includes `pages_fetched`, "
        "`has_next`, `next_page`, `warnings` and a `complete` flag."
    )
)
async def baidu_search(query: str, page: int = 1, pages: int = 1, backend: str = "auto") -> str:
    resp = await search(query, page=page, pages=pages, backend=backend or "auto", engine="baidu")
    return resp.to_json()


@server.tool(
    description=(
        "Fetch the next page(s) of a previous Baidu search. Same as baidu_search "
        "but makes paging intent explicit: pass the original query and the "
        "1-based page number from the previous response's `next_page` field."
    )
)
async def baidu_next(query: str, page: int, pages: int = 1, backend: str = "auto") -> str:
    resp = await search(query, page=page, pages=pages, backend=backend or "auto", engine="baidu")
    return resp.to_json()


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
