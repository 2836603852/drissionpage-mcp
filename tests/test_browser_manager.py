# -*- coding: utf-8 -*-
"""Unit tests for BrowserManager port-binding behavior."""

import socket
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
