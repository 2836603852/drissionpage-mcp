# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.1] - 2026-06-01

### Fixed (debugger / websocket — AI-usability hardening)
- **Non-blocking stepping**: `_wait_for_pause` no longer `time.sleep`-polls inside the
  async handler (which stalled the whole asyncio loop); now event-driven via a per-tab
  `threading.Event` run through `asyncio.to_thread`.
- **No silent freezes**: `dp_set_breakpoint`/`dp_set_xhr_breakpoint` auto-enable the
  Debugger domain, so a breakpoint can never pause the page with no listener/record.
- **Fail loud**: `dp_eval_on_frame` now surfaces `exceptionDetails` as `success:False`
  (silent=True meant thrown JS was hidden behind success:True); `run_cdp` error dicts in
  step/eval are surfaced too.
- **Non-destructive reads**: `dp_ws_get_frames` copies each frame before decoding instead
  of mutating the dicts still in the ring buffer; opcode!=1 payloads left untouched
  (matches the docstring); `total_buffered` computed under the lock.
- **Idempotent capture**: `dp_ws_listen_start` no longer silently wipes an existing
  buffer (returns `resumed`); re-`dp_debugger_enable` no longer discards a live pause.
- **Robust keying / no leaks**: `tab_key` guards the `tab_id` property raising
  BrowserConnectError; `_STATE` is pruned for dead tabs; removed dead `_ACTIVE` map and
  a no-op `f = f` line.
- **Headless decompile script**: `idahead_decompile.py` writes markers for unresolved /
  None-decompile targets and exits non-zero when zero functions were emitted (so an AI
  batch can tell a false-success empty run from a real one).

## [1.2.0] - 2026-05-31

### Added
- **WebSocket frame capture** (`tools/websocket.py`, 3 tools): `dp_ws_listen_start`
  / `dp_ws_get_frames` / `dp_ws_stop`. Subscribes to CDP `Network.webSocketFrame*`
  events via `driver.set_callback` into a bounded, thread-safe server-side buffer —
  closing the gap left by `dp_listen_*` (HTTP packets only) and `dp_run_cdp`
  (request/response only, no event stream). Frames expose direction / opcode /
  length / payload, grouped by connection id, with best-effort JSON decoding.
- **Interactive debugger** (`tools/debugger.py`, 10 tools): `dp_debugger_enable`,
  `dp_set_breakpoint`, `dp_set_xhr_breakpoint`, `dp_remove_breakpoint`,
  `dp_debugger_status`, `dp_resume`, `dp_step_over`, `dp_step_into`, `dp_step_out`,
  `dp_eval_on_frame`. Subscribes to `Debugger.paused`/`resumed`/`scriptParsed`,
  keeps the current pause state server-side, and exposes set-breakpoint → inspect
  stack → step → evaluate-on-frame. `dp_eval_on_frame` reads locals/closure at the
  pause site (the key move for recovering signature inputs).
- Shared CDP-driver helpers `get_driver` / `tab_key` in `tools/_common.py`.

### Changed
- Tool count 31 → **44** (31 core + 3 ws-frame + 10 debugger). Startup log and
  README tool tables updated accordingly.
- Verified against DrissionPage 4.1.1.4 (callbacks fire; `run_cdp` Debugger
  commands work while the renderer is paused).

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
