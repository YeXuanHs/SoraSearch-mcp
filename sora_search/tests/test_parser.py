# -*- coding: utf-8 -*-
"""Offline parser tests: real cn fixture + synthetic www (/ck/) fixture."""
import base64
from pathlib import Path
from urllib.parse import quote

from sora_search.parser import (
    decode_ck_href,
    detect_host,
    extract_next_url,
    is_bot_page,
    parse_page,
)

FIXTURE_CN = Path(__file__).parent / "fixtures" / "cn_page1.html"

# Real /ck/ jump link captured live from www.bing.com SERP (nav link, same format
# as result links). Decodes to: /search?q=python%e6%95%99%e7%a8%8b&webscp=1&FORM=HDRWSC
CK_REAL = (
    "https://www.bing.com/ck/a?!&&p=30ce2097ce6dcb8df88619536d227e7eef31c111"
    "b2ba614b6097c7c1d3a6b5f3JmltdHM9MTc5MTU5MDQwMA&ptn=3&ver=2&hsh=4"
    "&fclid=15398b33-047a-6458-0f81-9c8e052a6566"
    "&u=a1L3NlYXJjaD9xPXB5dGhvbiVlNiU5NSU5OSVlNyVhOCU4YiZ3ZWJzY3A9MSZGT1JNPUhEUldTQw&ntb=1"
)


def _ck_href(target: str) -> str:
    token = "a1" + base64.b64encode(target.encode("utf-8")).decode("ascii")
    return f"https://www.bing.com/ck/a?!&&p=deadbeef&ptn=3&ver=2&hsh=4&u={quote(token, safe='')}&ntb=1"


def _www_html() -> str:
    return f"""<html><head><title>golang - 搜索</title></head><body>
<div id="b_results">
<li class="b_algo"><h2><a href="{_ck_href('https://example.com/real-page')}">Example Real Page</a></h2>
<div class="b_caption"><p>3 天之前 · 这是摘要正文内容。</p></div></li>
<li class="b_algo"><h2><a href="https://direct.example.org/doc">Direct Doc</a></h2>
<div class="b_caption"><p>普通摘要无日期。</p></div></li>
</div>
<div class="b_pag"><a class="sb_pagS">2</a><a class="sb_pagN" href="/search?q=golang&first=21&FORM=PORE">下一页</a></div>
<span class="sb_count">约 1,234 个结果</span>
</body></html>"""


def test_detect_host_cn_first():
    assert detect_host("https://cn.bing.com/search?q=a") == "cn"
    assert detect_host("cn.bing.com") == "cn"
    assert detect_host("https://www.bing.com/search?q=a") == "www"
    assert detect_host("www.bing.com") == "www"
    assert detect_host("https://bing.com/search?q=a") == "www"
    assert detect_host("https://example.com/") == "unknown"


def test_decode_ck_href_real_capture():
    decoded = decode_ck_href(CK_REAL)
    assert decoded.startswith("/search?q=python")
    assert "FORM=HDRWSC" in decoded


def test_decode_ck_href_roundtrip():
    target = "https://docs.python.org/zh-cn/3/tutorial/index.html"
    assert decode_ck_href(_ck_href(target)) == target


def test_decode_ck_href_passthrough():
    direct = "https://www.runoob.com/python/python-tutorial.html"
    assert decode_ck_href(direct) == direct
    assert decode_ck_href("https://www.bing.com/ck/a?!&&p=abc") == "https://www.bing.com/ck/a?!&&p=abc"
    assert decode_ck_href("") == ""


def test_parse_cn_fixture():
    html = FIXTURE_CN.read_text(encoding="utf-8")
    page = parse_page(
        html,
        base_url="https://cn.bing.com/search?q=python%E6%95%99%E7%A8%8B&setlang=zh-CN&ensearch=0&first=1",
        query="python教程",
        page=1,
        first=1,
    )
    assert page.host == "cn"
    assert page.cur_page_text == "1"
    assert "结果" in page.total_text
    assert page.bot is False
    assert len(page.results) == 10
    assert page.next_url is not None and "first=" in page.next_url
    for r in page.results:
        assert r.title, "title must not be empty"
        assert r.url.startswith("http"), r.url
        assert r.domain, "domain must be extracted"
    assert sum(1 for r in page.results if r.snippet) >= 8


def test_parse_www_ck_and_date():
    page = parse_page(
        _www_html(),
        base_url="https://www.bing.com/search?q=golang&first=11",
        query="golang",
        page=2,
        first=11,
    )
    assert page.host == "www"
    assert page.cur_page_text == "2"
    assert len(page.results) == 2
    first, second = page.results
    assert first.url == "https://example.com/real-page"
    assert first.raw_href.startswith("https://www.bing.com/ck/a")
    assert first.date == "3 天之前"
    assert first.snippet == "这是摘要正文内容。"
    assert second.url == "https://direct.example.org/doc"
    assert second.date == ""
    assert page.next_url == "https://www.bing.com/search?q=golang&first=21&FORM=PORE"


def test_extract_next_url_missing():
    assert extract_next_url("<html><body>no pager</body></html>", "https://cn.bing.com/") is None


def test_is_bot_page():
    assert is_bot_page("<html><head><title>验证 - 必应</title></head><body></body></html>") is True
    assert is_bot_page("") is True
    html = FIXTURE_CN.read_text(encoding="utf-8")
    assert is_bot_page(html) is False
