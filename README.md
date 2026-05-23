# DrissionPage MCP

[![CI](https://github.com/2836603852/drissionpage-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/2836603852/drissionpage-mcp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-compatible-orange)](https://modelcontextprotocol.io/)
[![Status](https://img.shields.io/badge/status-source--only-yellow)](#-quick-start)

> A lean [Model Context Protocol](https://modelcontextprotocol.io/) server that gives LLM agents a browser, powered by [DrissionPage](https://github.com/g1879/DrissionPage). Alternative to `chrome-devtools-mcp` and `playwright-mcp` with a smaller surface area and Chinese-friendly defaults.

基于 [DrissionPage](https://github.com/g1879/DrissionPage) 的浏览器自动化 MCP Server。**31 个核心工具**，覆盖浏览器/标签页/导航/元素/JS/CDP/网络监听/截图，适合 LLM Agent 驱动真实 Chromium 完成网页操作、抓取、调试与逆向。

> ⚠️ **当前仅源码安装**：PyPI 上的 `drissionpage-mcp` 包名已被另一个无关项目（`jumodada/DrissionMCP`）占用。本项目的 PyPI 名计划为 `drissionpage-mcp-server`，尚未发布。**请按下面的源码方式安装，不要执行 `pip install drissionpage-mcp`**。

---

## ✨ Features

- ✅ **MCP 协议合规** — 基于官方 FastMCP 框架，stdio 传输，自动 schema
- ✅ **精简工具集** — 31 个高频工具，剔除冗余别名与低价值包装
- ✅ **端口可控** — 默认 9223，可固定 (`--debug-port`) 或自动挑空闲 (`--auto-port`)
- ✅ **多 session 管理** — 同实例下多浏览器/多标签并行追踪
- ✅ **网络抓包** — `dp_capture_api` 一站式 listen + wait + stop
- ✅ **CDP 直通** — `dp_run_cdp` 暴露任意 Chrome DevTools Protocol 命令
- ✅ **结构化 DOM 快照** — `dp_take_snapshot` 给 LLM 看的 JSON 树

## 🚀 Quick Start

### 安装（源码）

```bash
git clone https://github.com/2836603852/drissionpage-mcp.git
cd drissionpage-mcp
pip install -e .
```

安装完会在 PATH 注册一个 CLI 命令 `drissionpage-mcp`，这就是 MCP 客户端要拉起的可执行文件。

### 在 MCP 客户端中配置

**Claude Desktop / Claude Code / Cursor / Cline / Continue 等**（`mcp.json` 或客户端等价位置）：

```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp"
    }
  }
}
```

多实例并发场景，给每个加 `--auto-port` 自动错开调试端口：

```json
{
  "mcpServers": {
    "drissionpage-a": { "command": "drissionpage-mcp", "args": ["--auto-port"] },
    "drissionpage-b": { "command": "drissionpage-mcp", "args": ["--auto-port"] }
  }
}
```

## 🧩 启动参数

```
drissionpage-mcp [--debug-port PORT | --auto-port]
                 [--transport stdio|http|sse|streamable-http]
                 [--host HOST] [--port PORT]

Chromium 调试端口（互斥）:
  --debug-port PORT   固定 Chromium 调试端口 (1-65535)，默认 9223
  --auto-port         启动时自动挑选空闲端口（与 --debug-port 互斥）

MCP 传输层:
  --transport         stdio (默认) / http / sse / streamable-http
  --host              HTTP 模式下的绑定地址，默认 127.0.0.1
  --port              HTTP 模式下的端口，默认 8000
```

**默认 9223 的设计原因**：避免与用户手动起在 9222 的浏览器撞车。多实例并发时务必加 `--auto-port`。

### HTTP 模式（远程客户端 / 容器化部署）

```bash
drissionpage-mcp --transport http --host 0.0.0.0 --port 8000
```

启动后 MCP 客户端通过 `http://<host>:8000/` 连接（具体端点取决于客户端实现）。stdio 模式下 `--host` / `--port` 会被忽略。

## 📐 端口规则

- 每个 MCP 实例在启动时**固定一个**调试端口，全程复用，不中途切换。
- 工具调用中传入的 `debug_port` 必须与实例已固定的端口一致，否则报错。
- `dp_connect_browser({"address": "127.0.0.1:9223"})` 中地址端口同样必须一致。

## 🛠 工具总览（31 个）

| 分类 | 工具 |
|---|---|
| **浏览器** | `dp_new_browser` · `dp_connect_browser` · `dp_close_browser` · `dp_list_browsers` |
| **标签页** | `dp_list_tabs` · `dp_new_tab` · `dp_select_tab` · `dp_close_tabs` |
| **导航** | `dp_navigate` · `dp_history_action` (back/forward/refresh) |
| **等待** | `dp_wait_doc_loaded` · `dp_wait_url_change` · `dp_wait_new_tab` |
| **元素** | `dp_find_element` · `dp_find_elements` · `dp_click` · `dp_fill` · `dp_select` · `dp_get_text` · `dp_click_to_upload` |
| **内容** | `dp_get_page_content` (html/text) · `dp_take_snapshot` |
| **截图** | `dp_screenshot` |
| **网络** | `dp_listen_start` · `dp_listen_wait` · `dp_capture_api` |
| **执行** | `dp_run_js` · `dp_run_js_on_ele` · `dp_run_cdp` |
| **动作** | `dp_scroll` · `dp_handle_alert` |

并暴露一个 MCP Resource：`browser://status` 返回当前所有浏览器会话的实时状态。

## 💡 推荐工作流

> 下面是 LLM Agent 通过 MCP 协议依次发起的**工具调用**伪代码，不是 Python SDK。
> 实际由客户端（Claude Desktop / Cursor 等）通过 stdio JSON-RPC 与 server 通信。

```text
# 1. 检查当前实例是否已有浏览器
call dp_list_browsers

# 2a. 没有：新建一个
call dp_new_browser

# 2b. 已有：直接复用返回里的 browser_id

# 3. 操作页面
call dp_navigate         {"url": "https://example.com"}
call dp_wait_doc_loaded
call dp_click            {"locator": "text:登录"}

# 4. 抓接口
call dp_capture_api      {"url_pattern": "/api/user/profile",
                          "method": "GET", "timeout": 10}
```

### Locator 语法（来自 DrissionPage）

| 写法 | 含义 |
|---|---|
| `#submit` | id 选择器 |
| `.btn-primary` | class 选择器 |
| `text:登录` | 包含文本"登录"的元素 |
| `tag:button@text()=登录` | tag + 属性/文本组合 |
| `xpath://div[@class="x"]` | XPath |
| `css:div > a` | CSS selector |

## 🧪 开发

```bash
git clone https://github.com/2836603852/drissionpage-mcp.git
cd drissionpage-mcp
pip install -e ".[dev]"

# 编译检查
python -m py_compile src/drissionpage_mcp/*.py src/drissionpage_mcp/tools/*.py

# 跑测试
python -m pytest -q
```

## 🗺 Roadmap

- [x] 独立 PyPI 包名：`drissionpage-mcp-server`（v1.1.0，待发布）
- [x] streamable HTTP transport（`--transport http`）
- [x] 工具级 smoke 测试（`tests/test_tool_smoke.py`，8 用例）
- [x] CI（GitHub Actions：pytest 矩阵 + ruff）
- [ ] 发布到 PyPI
- [ ] 工具调用示例集（`docs/recipes/`）

## 🤝 Contributing

Issues 和 PR 都欢迎。建议：

1. 提 PR 前先开 issue 讨论方向，避免无效工作。
2. 新增工具需配套测试（参考 `tests/test_helpers.py`）。
3. 保持 lean mode 原则——不要为了"看起来全"加冗余包装；DrissionPage 已经能做的事，用 `dp_run_js` / `dp_run_cdp` 组合即可。

## 📄 License

[MIT](LICENSE) © 2026 DrissionPage MCP Contributors

## 🙏 Acknowledgements

- [DrissionPage](https://github.com/g1879/DrissionPage) — 底层浏览器自动化框架
- [FastMCP](https://github.com/prefecthq/fastmcp) — MCP 服务端框架
- [Model Context Protocol](https://modelcontextprotocol.io/) — 协议规范
