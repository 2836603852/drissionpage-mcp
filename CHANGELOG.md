# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
