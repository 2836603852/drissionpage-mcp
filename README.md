# DrissionPage MCP

[![PyPI](https://img.shields.io/badge/pypi-drissionpage--mcp-blue)](https://pypi.org/project/drissionpage-mcp/)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-compatible-orange)](https://modelcontextprotocol.io/)

> A lean [Model Context Protocol](https://modelcontextprotocol.io/) server that gives LLM agents a browser, powered by [DrissionPage](https://github.com/g1879/DrissionPage). Alternative to `chrome-devtools-mcp` and `playwright-mcp` with a smaller surface area and Chinese-friendly defaults.

基于 [DrissionPage](https://github.com/g1879/DrissionPage) 的浏览器自动化 MCP Server。**31 个核心工具**，覆盖浏览器/标签页/导航/元素/JS/CDP/网络监听/截图，适合 LLM Agent 驱动真实 Chromium 完成网页操作、抓取、调试与逆向。

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

### 安装

```bash
pip install drissionpage-mcp
```

源码安装：

```bash
git clone https://github.com/2836603852/drissionpage-mcp.git
cd drissionpage-mcp
pip install -e .
```

### 在 MCP 客户端中配置

**Claude Code / Cursor / Codex 等**（`mcp.json`）：

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

  --debug-port PORT   固定 Chromium 调试端口 (1-65535)，默认 9223
  --auto-port         启动时自动挑选空闲端口（与 --debug-port 互斥）
```

**默认 9223 的设计原因**：避免与用户手动起在 9222 的浏览器撞车。多实例并发时务必加 `--auto-port`。

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

```python
# 1. 检查当前实例是否已有浏览器
dp_list_browsers()

# 2a. 没有：新建一个
dp_new_browser()

# 2b. 已有：直接复用返回里的 browser_id

# 3. 操作页面
dp_navigate({"url": "https://example.com"})
dp_wait_doc_loaded()
dp_click({"locator": "button:登录"})

# 4. 抓接口
dp_capture_api({
  "url_pattern": "/api/user/profile",
  "method": "GET",
  "timeout": 10
})
```

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
