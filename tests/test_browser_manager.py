# -*- coding: utf-8 -*-
"""Unit tests for BrowserManager port-binding behavior."""

import socket
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from drissionpage_mcp.browser_manager import BrowserManager
from drissionpage_mcp.config import BrowserConfig, Config


@pytest.fixture
def manager():
    """Fresh BrowserManager instance (singleton reset)."""
    BrowserManager._instance = None
    return BrowserManager()


def test_get_debug_port_picks_free_port_when_unset(manager):
    port = manager.get_debug_port()
    assert isinstance(port, int)
    assert 1024 <= port <= 65535
    # Subsequent call must return the same fixed port.
    assert manager.get_debug_port() == port


def test_set_config_with_explicit_port_locks_in(manager):
    cfg = Config(browser=BrowserConfig(debug_port=53761))
    manager.set_config(cfg)
    assert manager.fixed_debug_port == 53761
    assert manager.get_debug_port() == 53761


def test_bind_debug_port_rejects_mismatch(manager):
    manager._bind_debug_port(53761)
    with pytest.raises(ValueError, match="already fixed"):
        manager._bind_debug_port(53762)


def test_bind_debug_port_idempotent_for_same_value(manager):
    manager._bind_debug_port(53761)
    assert manager._bind_debug_port(53761) == 53761


def test_bind_debug_port_rejects_non_positive(manager):
    with pytest.raises(ValueError, match="positive"):
        manager._bind_debug_port(0)


def test_extract_port_handles_address_strings(manager):
    assert manager._extract_port("127.0.0.1:9222") == 9222
    assert manager._extract_port("localhost:55555") == 55555
    assert manager._extract_port("not-a-port") is None


def test_pick_free_port_returns_actually_free_port(manager):
    port = manager._pick_free_port()
    # Verify it's bindable (not in use).
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))


@pytest.fixture
def chromium_calls(monkeypatch):
    calls = []

    def construct(addr_or_opts):
        tab = SimpleNamespace(url="about:blank", title="Test", tab_id="t1")
        browser = SimpleNamespace(tab_ids=["t1"], get_tab=lambda _: tab, quit=Mock())
        calls.append((addr_or_opts, browser))
        return browser

    monkeypatch.setattr("drissionpage_mcp.browser_manager.Chromium", construct)
    return calls


def test_connect_custom_addresses_preserves_default_and_sessions(manager, chromium_calls):
    manager.set_config(Config(browser=BrowserConfig(debug_port=9223)))
    shop = manager.connect_browser("127.0.0.1:38318", browser_id="shop")
    workbench = manager.connect_browser("127.0.0.1:50982", browser_id="workbench")

    assert manager.get_debug_port() == 9223
    assert manager.get_session("shop") is shop
    assert manager.get_session("workbench") is workbench
    assert shop.debug_port == 38318
    assert workbench.debug_port == 50982
    assert manager.default_session_id == "shop"
    assert [options.address for options, _ in chromium_calls] == [
        "127.0.0.1:38318", "127.0.0.1:50982",
    ]
    assert all(options.is_existing_only for options, _ in chromium_calls)


@pytest.mark.parametrize("port", [9223, 53761])
def test_connect_without_address_uses_runtime_default(manager, chromium_calls, port):
    manager.set_config(Config(browser=BrowserConfig(debug_port=port)))
    session = manager.connect_browser()
    assert session.debug_port == port
    assert chromium_calls[0][0].address == f"127.0.0.1:{port}"
    assert chromium_calls[0][0].is_existing_only


def test_custom_create_does_not_rebind_default(manager, chromium_calls):
    manager.set_config(Config(browser=BrowserConfig(debug_port=9223)))
    custom = manager.create_browser(debug_port=53761)
    default = manager.create_browser()
    assert custom.debug_port == 53761
    assert default.debug_port == 9223
    assert manager.get_debug_port() == 9223
    assert [options.address for options, _ in chromium_calls] == [
        "127.0.0.1:53761", "127.0.0.1:9223",
    ]


@pytest.mark.parametrize("address", ["invalid", "127.0.0.1:0", "127.0.0.1:-1", "127.0.0.1:65536"])
def test_invalid_custom_address_never_constructs_browser(manager, chromium_calls, address):
    with pytest.raises(ValueError):
        manager.connect_browser(address)
    assert chromium_calls == []
    assert manager.sessions == {}


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_invalid_custom_create_port_never_constructs_browser(manager, chromium_calls, port):
    with pytest.raises(ValueError, match="1-65535"):
        manager.create_browser(debug_port=port)
    assert chromium_calls == []


def test_failed_attachment_keeps_default_and_does_not_register_session(manager, monkeypatch):
    manager.set_config(Config(browser=BrowserConfig(debug_port=9223)))

    def unavailable(addr_or_opts):
        assert addr_or_opts.address == "127.0.0.1:38318"
        assert addr_or_opts.is_existing_only
        raise ConnectionError("Browser not listening")

    monkeypatch.setattr("drissionpage_mcp.browser_manager.Chromium", unavailable)
    with pytest.raises(ConnectionError, match="not listening"):
        manager.connect_browser("127.0.0.1:38318")
    assert manager.get_debug_port() == 9223
    assert manager.sessions == {}
    assert manager.default_session_id is None


def test_shutdown_preserves_attached_browser_but_closes_created_browser(manager, chromium_calls):
    manager.set_config(Config(browser=BrowserConfig(debug_port=9223)))
    attached = manager.connect_browser("127.0.0.1:38318")
    created = manager.create_browser()
    manager.close_all()
    attached.browser.quit.assert_not_called()
    created.browser.quit.assert_called_once()
    assert manager.sessions == {}
    assert manager.default_session_id is None


def test_explicit_close_still_closes_attached_browser(manager, chromium_calls):
    attached = manager.connect_browser("127.0.0.1:38318", browser_id="shop")
    assert manager.close_session("shop") is True
    attached.browser.quit.assert_called_once()
