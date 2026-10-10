# -*- coding: utf-8 -*-
"""Offline service-logic tests (no network): verify / dedupe / assembly."""
from sora_search.models import SoraPage, SoraResult, SearchResponse
from sora_search.service import (
    dedupe_results,
    first_of_url,
    normalize_url,
    verify_page,
)


def _page(cur: str, urls: list[str], *, bot: bool = False, next_url: str | None = None, page: int = 1) -> SoraPage:
    return SoraPage(
        query="q",
        page=page,
        first=1,
        url="https://cn.bing.com/search?q=q",
        host="cn",
        results=[
            SoraResult(rank=i + 1, page=page, title=f"t{i}", url=u) for i, u in enumerate(urls)
        ],
        cur_page_text=cur,
        next_url=next_url,
        bot=bot,
    )


def test_normalize_url():
    assert normalize_url("HTTP://Example.COM/a/?b=1#frag") == "http://example.com/a?b=1"
    assert normalize_url("https://example.com/") == "https://example.com/"
    assert normalize_url("https://example.com/x/") == "https://example.com/x"
    assert normalize_url("not a url") == "not a url"


def test_first_of_url():
    assert first_of_url("https://cn.bing.com/search?q=a&first=21", 3) == 21
    assert first_of_url("https://cn.bing.com/search?q=a", 2) == 11
    assert first_of_url("https://cn.bing.com/search?q=a&first=bad", 2) == 11


def test_verify_page_ok():
    page = _page("2", [f"https://e.com/p2-{i}" for i in range(5)])
    prev = {f"https://e.com/p1-{i}" for i in range(10)}
    ok, _ = verify_page(2, page, prev)
    assert ok is True


def test_verify_page_marker_mismatch():
    page = _page("1", [f"https://e.com/x-{i}" for i in range(5)])
    ok, reasons = verify_page(2, page, None)
    assert ok is False
    assert any("expected page 2" in r for r in reasons)


def test_verify_page_duplicate_of_previous():
    urls = [f"https://e.com/same-{i}" for i in range(5)]
    page = _page("", urls)  # no marker: overlap check must still catch it
    ok, reasons = verify_page(2, page, set(urls))
    assert ok is False
    assert any("duplicate" in r for r in reasons)


def test_verify_page_empty_and_bot():
    ok, _ = verify_page(1, _page("1", []), None)
    assert ok is False
    ok, reasons = verify_page(1, _page("1", ["https://e.com/a"], bot=True), None)
    assert ok is False
    assert reasons == ["bot/verification page"]


def test_dedupe_results_global_ranks():
    p1 = _page("1", ["https://e.com/a", "https://e.com/b", "https://e.com/c"])
    p2 = _page("2", ["https://e.com/b", "https://e.com/d"], page=2)
    out = dedupe_results([p1, p2])
    assert [r.url for r in out] == ["https://e.com/a", "https://e.com/b", "https://e.com/c", "https://e.com/d"]
    assert [r.rank for r in out] == [1, 2, 3, 4]
    assert [r.page for r in out] == [1, 1, 1, 2]


def test_search_response_props():
    p1 = _page("1", ["https://e.com/a"], next_url="https://cn.bing.com/search?q=q&first=11")
    resp = SearchResponse(
        query="q", backend="http", host="cn", total_text="约 10 个结果",
        requested_page=1, requested_pages=1, pages=[p1],
        results=[SoraResult(rank=1, page=1, title="t", url="https://e.com/a")],
    )
    assert resp.pages_fetched == [1]
    assert resp.has_next is True
    assert resp.next_page == 2
    d = resp.to_dict()
    assert d["result_count"] == 1 and d["complete"] is True
    assert d["requested"] == {"page": 1, "pages": 1}
