# -*- coding: utf-8 -*-
"""Tests for the server CLI: --debug-port parsing and lifespan injection."""

import contextlib
import io
import sys

import pytest

from drissionpage_mcp import server
from drissionpage_mcp.browser_manager import BrowserManager


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Reset module-level state between tests so they're hermetic."""
    BrowserManager._instance = None
    server._cli_debug_port = None
    yield
    BrowserManager._instance = None
    server._cli_debug_port = None


def test_parse_cli_no_args_leaves_debug_port_unset():
    """Naked invocation leaves debug_port=None; main() resolves to DEFAULT_DEBUG_PORT."""
    ns = server._parse_cli_args([])
    assert ns.debug_port is None
    assert ns.auto_port is False
    assert server.DEFAULT_DEBUG_PORT == 9223


def test_parse_cli_with_explicit_port():
    ns = server._parse_cli_args(["--debug-port", "9876"])
    assert ns.debug_port == 9876
    assert ns.auto_port is False


def test_parse_cli_explicit_port_can_match_default():
    ns = server._parse_cli_args(["--debug-port", "9223"])
    assert ns.debug_port == 9223


def test_parse_cli_auto_port_flag():
    ns = server._parse_cli_args(["--auto-port"])
    assert ns.auto_port is True
    assert ns.debug_port is None


def test_parse_cli_auto_port_and_debug_port_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        with contextlib.redirect_stderr(io.StringIO()):
            server._parse_cli_args(["--auto-port", "--debug-port", "9876"])


def test_main_rejects_out_of_range_port(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["drissionpage-mcp", "--debug-port", "70000"])
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        with pytest.raises(SystemExit) as excinfo:
            server.main()
    assert excinfo.value.code == 2
    assert "1-65535" in buf.getvalue()


def test_main_rejects_zero(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["drissionpage-mcp", "--debug-port", "0"])
    with contextlib.redirect_stderr(io.StringIO()):
        with pytest.raises(SystemExit) as excinfo:
            server.main()
    assert excinfo.value.code == 2


def test_cli_port_propagates_into_lifespan_via_browser_manager():
    """Simulate the lifespan path that injects ``_cli_debug_port`` into Config."""
    server._cli_debug_port = 53761
    from drissionpage_mcp.config import Config

    cfg = Config()
    if server._cli_debug_port is not None:
        cfg.browser.debug_port = server._cli_debug_port

    mgr = BrowserManager()
    mgr.set_config(cfg)
    assert mgr.fixed_debug_port == 53761
    assert mgr.get_debug_port() == 53761


def test_lifespan_without_cli_port_uses_auto_picked():
    """If main() never ran (e.g. unit-test entry), the manager still falls back
    to socket-picked free port — this preserves the legacy auto-pick behaviour
    for callers that bypass the CLI."""
    server._cli_debug_port = None
    from drissionpage_mcp.config import Config

    cfg = Config()
    mgr = BrowserManager()
    mgr.set_config(cfg)
    port = mgr.get_debug_port()
    assert isinstance(port, int)
    assert 1024 <= port <= 65535


def test_main_locks_default_9223_when_no_cli_args(monkeypatch):
    """Naked `drissionpage-mcp` invocation should lock 9223 into _cli_debug_port,
    without actually starting the server (we monkeypatch mcp.run to a no-op)."""
    monkeypatch.setattr(sys, "argv", ["drissionpage-mcp"])
    monkeypatch.setattr(server.mcp, "run", lambda **kw: None)
    server.main()
    assert server._cli_debug_port == 9223


def test_main_auto_port_picks_free_port(monkeypatch):
    """--auto-port should resolve to a real free port, never the default 9223."""
    monkeypatch.setattr(sys, "argv", ["drissionpage-mcp", "--auto-port"])
    monkeypatch.setattr(server.mcp, "run", lambda **kw: None)
    server.main()
    assert isinstance(server._cli_debug_port, int)
    assert 1024 <= server._cli_debug_port <= 65535
    assert server._cli_debug_port != server.DEFAULT_DEBUG_PORT
