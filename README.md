# SoraSearch-mcp 🔍

从 0 编写的搜索 MCP Server：爬取 **Bing / 百度**搜索结果页，返回每条结果的**标题 / URL / 摘要**，支持 **verified 翻页**（每页必验，绝不把重复页冒充新页）。

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-2.x-green)](https://modelcontextprotocol.io)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

## ✨ 特性

- 🔍 **双引擎**：Bing + 百度，统一的响应格式
- 📄 **Verified 翻页**：只跟随引擎下发的"下一页"链接，每页用引擎页码标记 + URL 重叠率双信号校验
- 🔗 **真实直链**：Bing `/ck/` 跳转链解码、百度 `mu=` 属性提取，拿到可直接打开的 URL
- 🛡️ **双后端兜底**：HTTP（Chrome 指纹）优先，被软限流/验证页时自动切持久化浏览器
- 🧹 **干净结果**：百度只收普通网页结果，文库/视频/百科卡片、AI 总结与广告自动跳过

## 🚀 快速开始

```bash
git clone https://github.com/YeXuanHs/SoraSearch-mcp.git
cd SoraSearch-mcp
pip install -e .
playwright install chromium   # 浏览器兜底后端需要

# 离线测试（不联网）
python -m pytest sora_search/tests -q

# 启动 MCP (stdio)
SoraSearch-mcp
# 或
python -m sora_search
```

MCP 客户端配置示例（stdio）：

```json
{
  "mcpServers": {
    "web-search": {
      "command": "python",
      "args": ["-m", "sora_search"],
      "cwd": "/path/to/SoraSearch-mcp"
    }
  }
}
```

## 🛠️ 工具

| 工具 | 说明 |
|---|---|
| `bing_search(query, page=1, pages=1, backend="auto")` | 搜 Bing，返回 verified 页面与合并结果 |
| `bing_next(query, page, pages=1, backend="auto")` | Bing 翻页（`page` 取上次响应的 `next_page`） |
| `baidu_search(query, page=1, pages=1, backend="auto")` | 搜百度（只收普通网页结果） |
| `baidu_next(query, page, pages=1, backend="auto")` | 百度翻页 |

响应示例：

```json
{
  "query": "python asyncio 教程",
  "engine": "bing",
  "backend": "http",
  "pages_fetched": [1],
  "has_next": true,
  "next_page": 2,
  "result_count": 10,
  "complete": true,
  "warnings": [],
  "results": [
    {
      "rank": 1,
      "page": 1,
      "title": "Python asyncio 模块 | 菜鸟教程",
      "url": "https://www.runoob.com/python3/python-asyncio.html",
      "domain": "www.runoob.com",
      "snippet": "Python asyncio 模块 asyncio 是标准库中的一个模块…",
      "date": ""
    }
  ]
}
```

## ⚙️ 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `SORA_BING_ENTRY` | `https://www.bing.com/search` | Bing 入口（跟随 302） |
| `SORA_BAIDU_ENTRY` | `https://www.baidu.com/s` | 百度入口 |
| `SORA_MKT` / `SORA_SETLANG` | `zh-CN` | 市场/语言 |
| `SORA_BACKENDS` | `http,browser` | auto 模式后端顺序 |
| `SORA_MAX_PAGES` | `5` | 单次最多 verified 页数 |
| `SORA_HTTP_TIMEOUT` | `25` | HTTP 超时（秒） |
| `SORA_BROWSER_PROFILE` | `sora_profile` | 持久化浏览器目录 |
| `SORA_BROWSER_HEADLESS` | `1` | 浏览器是否 headless |

## 🔬 实测发现（为什么从 0 写）

Bing（2026-10-10，国内网络）：

- `www.bing.com` 会 302 到 `cn.bing.com`；cn 多为直链，www 可能是 `/ck/a?...&u=a1<base64>` 跳转链
- 手工拼 `first=` 会被**软限流**：Bing 忽略翻页参数、重复返回第 1 页（`cur=1`、10 条 URL 全同）
- 跟随 Bing 下发的"下一页"链接可翻页（`cur=2`、结果不同）；但同一 IP 高频后也会被软限流
- `count=` 参数被忽略（恒 10 条/页）

百度（2026-10-10）：

- 普通结果 `#content_left div.result`，真实 URL 在 `mu=` 属性里（`h3 a[href]` 是不可逆的 `/link?` 跳转链）
- HTTP 直抓偶发"百度安全验证"；被拦时自动切浏览器后端

## 📐 设计

- **双域适配（Bing）**：跟随 302 落到哪就用哪套逻辑（`parser.detect_host` 区分 www/cn；`/ck/` 按 `a1+base64` 解码）
- **只跟随下发链接翻页**：不手工拼偏移
- **每页必验**：引擎页码标记必须等于期望页码；与已收录页 URL 重叠率 ≥60% 即判为软限流并拒绝该页
- **双后端**：HTTP（curl_cffi Chrome 指纹 + Cookie 会话）优先；被限流时自动切 Playwright 持久化浏览器

## 📁 结构

```
SoraSearch-mcp/
├── sora_search/
│   ├── server.py          # MCP Server（4 个工具）
│   ├── service.py         # 双引擎编排：verified 翻页 + 兜底链
│   ├── parser.py          # Bing 解析（www/cn 双适配 + ck 解码）
│   ├── baidu_parser.py    # 百度解析（mu 直链 + 日期拆分）
│   ├── http_backend.py    # HTTP 后端（curl_cffi）
│   ├── browser_backend.py # 浏览器后端（持久化 profile）
│   ├── models.py          # 数据模型
│   ├── config.py          # 环境变量配置
│   └── tests/             # 22 个离线测试 + 真实夹具
├── pyproject.toml
├── README.md
└── LICENSE
```

## 📄 License

[MIT](LICENSE)
