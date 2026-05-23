# -*- coding: utf-8 -*-
"""Shared helpers for tool modules."""

import functools
from typing import Any, Callable, Optional

from ..browser_manager import browser_manager
from ..exceptions import BrowserNotConnectedError, DrissionPageMcpError


def get_tab(browser_id: Optional[str] = None):
    """Return active tab or raise BrowserNotConnectedError."""
    tab = browser_manager.get_active_tab(browser_id)
    if not tab:
        raise BrowserNotConnectedError("Browser not connected")
    return tab


def get_session(browser_id: Optional[str] = None):
    """Return browser session or raise BrowserNotConnectedError."""
    session = browser_manager.get_session(browser_id)
    if not session:
        raise BrowserNotConnectedError("Browser not connected")
    return session


def resolve_tab_id(session, tab) -> Optional[str]:
    """Resolve a tab id from tab object and tracked session tabs."""
    tab_id = str(getattr(tab, "tab_id", "") or getattr(tab, "_tab_id", "")).strip()
    if tab_id and tab_id in session.tabs:
        return tab_id
    for tid, info in session.tabs.items():
        if info.tab == tab:
            return tid
    return tab_id or None


def tool_handler(func: Callable) -> Callable:
    """Wrap a tool coroutine with unified error handling.

    On success the inner function's dict is returned as-is (it should already
    contain ``success: True``). On failure we return a structured error dict
    derived from ``DrissionPageMcpError.to_dict`` when possible.
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> dict:
        try:
            return await func(*args, **kwargs)
        except DrissionPageMcpError as exc:
            return exc.to_dict()
        except Exception as exc:  # noqa: BLE001 - last-resort tool boundary
            return {"success": False, "error": str(exc)}

    return wrapper
