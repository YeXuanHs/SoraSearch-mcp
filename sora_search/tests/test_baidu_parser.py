# -*- coding: utf-8 -*-
"""Offline Baidu parser tests: real fixture (persistent-profile capture)."""
from pathlib import Path

from sora_search import baidu_parser
from sora_search.baidu_parser import (
    detect_host,
    extract_next_url,
    is_bot_page,
    parse_page,
)

FIXTURE = Path(__file__).parent / "fixtures" / "baidu_page1.html"
BASE = "https://www.baidu.com/s?wd=python%E6%95%99%E7%A8%8B&pn=0&ie=utf-8"


def test_detect_host():
    assert detect_host("https://www.baidu.com/s?wd=a") == "www"
    assert detect_host("www.baidu.com") == "www"
    assert detect_host("https://baidu.com/s?wd=a") == "www"
    assert detect_host("https://example.com/") == "unknown"


def test_parse_fixture_plain_results_only():
    html = FIXTURE.read_text(encoding="utf-8")
    page = parse_page(html, base_url=BASE, query="python教程", page=1, first=0)
    assert page.host == "www"
    assert page.cur_page_text == "1"
    assert page.bot is False
    assert page.next_url is not None and "pn=10" in page.next_url
    # 7 plain `div.result` items; result-op cards (wenku/video/baike) excluded
    assert len(page.results) == 7
    first = page.results[0]
    assert first.title.startswith("Python 教程")
    assert first.url == "https://docs.python.org/zh-cn/3/tutorial/index.html"
    assert first.domain == "docs.python.org"
    assert first.snippet, "snippet must not be empty"
    assert "/link?" in first.raw_href
    for item in page.results:
        assert item.title, "title must not be empty"
        assert item.url.startswith("http"), item.url
        assert "/link?" not in item.url, "mu= must be the real target"
        assert item.domain, "domain must be extracted"
    assert sum(1 for r in page.results if r.snippet) >= 6


def test_parse_fixture_date_split():
    html = FIXTURE.read_text(encoding="utf-8")
    page = parse_page(html, base_url=BASE, query="python教程", page=1, first=0)
    dated = [r for r in page.results if r.date]
    assert dated, "expected at least one date-prefixed snippet"
    second = page.results[1]
    assert second.date == "2025年10月17日"
    assert not second.snippet.startswith("2025年")
    assert page.results[0].date == ""


def test_parse_skips_opaque_links_without_mu():
    html = """<html><head><title>x_百度搜索</title></head><body>
<div id="content_left">
<div class="result c-container"><h3><a href="http://www.baidu.com/link?url=abc">NoMu</a></h3></div>
<div class="result c-container" mu="https://example.com/real"><h3><a href="http://www.baidu.com/link?url=def">HasMu</a></h3>
<div class="cos-color-text-tiny summary-gap_68jXq"><div class="cos-line-clamp-2">摘要正文。</div></div></div>
</div></body></html>"""
    page = parse_page(html, base_url=BASE, query="x", page=1, first=0)
    assert len(page.results) == 1
    assert page.results[0].url == "https://example.com/real"
    assert page.results[0].snippet == "摘要正文。"


def test_extract_next_url():
    html = FIXTURE.read_text(encoding="utf-8")
    nxt = extract_next_url(html, BASE)
    assert nxt is not None
    assert nxt.startswith("https://www.baidu.com/s?")
    assert "pn=10" in nxt
    assert extract_next_url("<html><body>no pager</body></html>", BASE) is None


def test_is_bot_page_safe_verify():
    verify_html = (
        "<html><head><title>百度安全验证</title></head>"
        "<body><div>拖动滑块完成验证</div></body></html>"
    )
    assert is_bot_page(verify_html, "https://www.baidu.com/s?wd=a") is True
    assert is_bot_page("", "https://www.baidu.com/s?wd=a") is True
    assert (
        is_bot_page(
            "<html><head><title>x</title></head><body></body></html>",
            "https://wappass.baidu.com/static/captcha/tuxing_v2.html",
        )
        is True
    )
    assert is_bot_page(FIXTURE.read_text(encoding="utf-8"), BASE) is False
    assert baidu_parser._is_usable_url("http://nourl.ubs.baidu.com/61344") is False
