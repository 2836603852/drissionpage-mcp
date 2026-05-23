# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-05-23

### Added
- **HTTP transport**: new CLI flags `--transport {stdio,http,sse,streamable-http}`,
  `--host`, `--port`. stdio remains default; HTTP enables remote / containerized
  deployments via FastMCP's native streamable HTTP server.
- **Tool-level smoke tests** (`tests/test_tool_smoke.py`): 8 cases covering
  navigate / history_action / get_page_content (html+text) / run_js / list_browsers
  / not-connected error path, using a fake mcp collector + injected fake browser.
- **GitHub Actions CI** (`.github/workflows/ci.yml`): pytest on Python 3.10 & 3.12,
  ruff lint, py_compile sanity check.

### Changed
- **PyPI name**: `drissionpage-mcp` → `drissionpage-mcp-server` (the original
  name is squatted by an unrelated project on PyPI). CLI command name
  remains `drissionpage-mcp`.
- Renamed internal helper `_run_on_active_tab(browser_id, action, ...)` →
  `_run_on_active_tab(browser_id, task, ...)` to avoid keyword collision when
  callers pass `action=...` in `extra`.
- ruff config migrated to `[tool.ruff.lint]` (new layout) and ignores E501
  (handled by black).

### Fixed
- `dp_history_action` returning `success: False` due to a duplicate `action`
  keyword in the helper call (introduced in 1.0.0 during the 3→1 merge).

## [1.0.0] - 2026-05-23

### Added
- Initial public release.
- 31 lean-mode tools across 6 categories (browser / tabs / page / wait /
  element / JS-CDP / network / screenshot / actions).
- `--debug-port` and mutually-exclusive `--auto-port` CLI flags;
  default debug port is **9223** (avoids colliding with a user-launched
  Chromium on the standard 9222).
- `browser://status` resource exposing live browser session metadata.
- Stdio transport via FastMCP.

### Notes
- Compared to a kitchen-sink wrapper, several low-value or redundant tools
  were intentionally removed or merged:
  - removed: `dp_get_tab`, `dp_wait_ele_displayed`, `dp_upload_file`,
    `dp_get_page_info`, `dp_listen_stop`.
  - merged: navigation back/forward/refresh → `dp_history_action(action)`;
    HTML and text extraction → `dp_get_page_content(mode)`.
