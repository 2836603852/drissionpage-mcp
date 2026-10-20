# -*- coding: utf-8 -*-
"""
DrissionPage MCP Page Management Tools
"""

from typing import Any, Callable, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from ..browser_manager import browser_manager
from ._common import get_session, get_tab, resolve_tab_id, tool_handler

# ============ Parameter Models ============

class NewBrowserParams(BaseModel):
    """Create browser parameters"""
    proxy: Optional[str] = Field(None, description="Proxy server address")
    debug_port: Optional[int] = Field(
        None,
        ge=1,
        le=65535,
        description="Optional Chromium debugger port. If omitted, use the runtime default (normally 9223); explicit ports do not change that default.",
    )


class ConnectBrowserParams(BaseModel):
    """Connect browser parameters"""
    address: Optional[str] = Field(
        None,
        description="Existing browser debugger address, e.g. 127.0.0.1:38318. If omitted, connect to the runtime default (normally 127.0.0.1:9223). Does not launch a browser or change the default port.",
    )
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class CloseBrowserParams(BaseModel):
    """Close browser parameters"""
    browser_id: Optional[str] = Field(None, description="Browser instance ID, closes default browser if not specified")


class ListTabsParams(BaseModel):
    """List tabs parameters"""
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class NewTabParams(BaseModel):
    """Create new tab parameters"""
    url: Optional[str] = Field(None, description="URL to open")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class SelectTabParams(BaseModel):
    """Select tab parameters"""
    tab_id: str = Field(..., description="Tab ID or index")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class CloseTabsParams(BaseModel):
    """Close multiple tabs parameters"""
    tab_ids: Optional[Union[str, List[str]]] = Field(None, description="Tab IDs to close; omit to close all tabs")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class NavigateParams(BaseModel):
    """Navigate parameters"""
    url: str = Field(..., description="Target URL")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")
    timeout: float = Field(30.0, description="Timeout in seconds")


class HistoryActionParams(BaseModel):
    """Browser history action parameters"""
    action: Literal["back", "forward", "refresh"] = Field(
        ..., description="History action to perform on the current tab"
    )
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class WaitBasicParams(BaseModel):
    """Basic wait parameters"""
    timeout: float = Field(10.0, description="Timeout in seconds")
    raise_error: bool = Field(False, description="Raise wait error instead of returning timeout status")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class WaitTextChangeParams(WaitBasicParams):
    """Title/URL change wait parameters"""
    text: str = Field(..., description="Text to match against title or URL")
    exclude: bool = Field(False, description="If true, wait until title/URL no longer includes text")


class WaitNewTabParams(WaitBasicParams):
    """New-tab wait parameters"""
    curr_tab: Optional[str] = Field(None, description="Current tab id to compare against")


# ============ Helper Functions ============

def _build_tab_dict(session, tab_id: str, tab_obj=None) -> Dict[str, Any]:
    """Build normalized tab payload."""
    info = session.tabs.get(tab_id)
    if info:
        tab_obj = info.tab
    return {
        "tab_id": tab_id,
        "url": getattr(tab_obj, "url", info.url if info else ""),
        "title": getattr(tab_obj, "title", info.title if info else ""),
        "is_active": tab_id == session.active_tab_id,
    }


def _collect_tabs(session) -> List[Dict[str, Any]]:
    """Collect normalized tab list."""
    session.update_tab_info()
    return [_build_tab_dict(session, tab_id) for tab_id in session.tabs.keys()]


def _normalize_tab_ids(tab_ids: Optional[Union[str, List[str]]]) -> List[str]:
    """Normalize tab id inputs into string list."""
    if tab_ids is None:
        return []
    if isinstance(tab_ids, str):
        return [tab_ids]
    return [str(tab_id) for tab_id in tab_ids if str(tab_id).strip()]


def _wait_to_result(ok: bool, event: str, timeout: float, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Normalize wait result payload."""
    payload = {
        "success": bool(ok),
        "event": event,
        "timeout": timeout,
    }
    if extra:
        payload.update(extra)
    if not ok:
        payload["error"] = "Wait condition not met within timeout"
    return payload


def _run_on_active_tab(browser_id: Optional[str], task: Callable, **extra) -> Dict[str, Any]:
    """Resolve session + active tab, invoke ``task(tab)``, refresh tracking, return payload.

    ``task`` should perform one navigation-style call on ``tab`` (no return value
    needed). Returns a dict including ``url`` plus any ``extra`` fields supplied.
    The parameter is named ``task`` (not ``action``) so callers can pass
    ``action=...`` as part of ``extra`` without keyword collision.
    """
    session = get_session(browser_id)
    tab = get_tab(browser_id)
    task(tab)
    session.update_tab_info()
    resolved_tab_id = resolve_tab_id(session, tab)
    if resolved_tab_id:
        session.active_tab_id = resolved_tab_id
    payload = {
        "success": True,
        "url": getattr(tab, "url", ""),
    }
    if extra:
        payload.update(extra)
    return payload


def register_page_management_tools(mcp):
    """Register page management tools"""

    @mcp.tool()
    @tool_handler
    async def dp_new_browser(params: NewBrowserParams = None) -> dict:
        """Create a new browser instance"""
        if params is None:
            params = NewBrowserParams()

        session = browser_manager.create_browser(
            proxy=params.proxy,
            debug_port=params.debug_port,
        )

        return {
            "success": True,
            "browser_id": session.browser_id,
            "debug_port": session.debug_port,
            "debugger_address": session.debugger_address,
            "is_default": session.browser_id == browser_manager.default_session_id,
            "tabs_count": len(session.tabs),
        }

    @mcp.tool()
    @tool_handler
    async def dp_connect_browser(params: ConnectBrowserParams = None) -> dict:
        """Connect to an existing browser by debugger address."""
        if params is None:
            params = ConnectBrowserParams()
        session = browser_manager.connect_browser(
            address=params.address,
            browser_id=params.browser_id,
        )

        return {
            "success": True,
            "browser_id": session.browser_id,
            "debug_port": session.debug_port,
            "debugger_address": session.debugger_address,
            "tabs_count": len(session.tabs),
        }

    @mcp.tool()
    @tool_handler
    async def dp_close_browser(params: CloseBrowserParams = None) -> dict:
        """Close the specified browser instance."""
        if params is None:
            params = CloseBrowserParams()

        browser_id = params.browser_id or browser_manager.default_session_id
        if not browser_id:
            return {
                "success": False,
                "error": "No browser instance to close",
            }

        success = browser_manager.close_session(browser_id)
        return {
            "success": success,
            "browser_id": browser_id,
        }

    @mcp.tool()
    @tool_handler
    async def dp_list_browsers() -> dict:
        """List all browser instances and their tabs."""
        sessions = browser_manager.list_sessions()
        return {
            "success": True,
            "browsers": sessions,
            "default_browser_id": browser_manager.default_session_id,
        }

    @mcp.tool()
    @tool_handler
    async def dp_list_tabs(params: ListTabsParams = None) -> dict:
        """List all tabs of a browser session."""
        if params is None:
            params = ListTabsParams()

        session = get_session(params.browser_id)
        tabs = _collect_tabs(session)

        return {
            "success": True,
            "browser_id": session.browser_id,
            "tabs": tabs,
            "active_tab_id": session.active_tab_id,
        }

    @mcp.tool()
    @tool_handler
    async def dp_close_tabs(params: CloseTabsParams = None) -> dict:
        """Close specific tab ids, or all tabs when ``tab_ids`` is omitted."""
        if params is None:
            params = CloseTabsParams()

        session = get_session(params.browser_id)
        session.update_tab_info()

        target_ids = _normalize_tab_ids(params.tab_ids)
        if not target_ids:
            target_ids = list(session.tabs.keys())

        closed_ids: List[str] = []
        failed: List[Dict[str, str]] = []
        for tab_id in target_ids:
            if browser_manager.close_tab(tab_id, params.browser_id):
                closed_ids.append(tab_id)
            else:
                failed.append({"tab_id": tab_id, "error": "Failed to close tab"})

        session.update_tab_info()
        result = {
            "success": len(failed) == 0,
            "browser_id": session.browser_id,
            "closed_tab_ids": closed_ids,
            "failed": failed,
            "active_tab_id": session.active_tab_id,
            "remaining_tabs": _collect_tabs(session),
        }
        if failed:
            result["error"] = "Some tabs failed to close"
        return result

    @mcp.tool()
    @tool_handler
    async def dp_new_tab(params: NewTabParams) -> dict:
        """Create a new tab in the specified browser."""
        session = get_session(params.browser_id)

        if params.url:
            tab = session.browser.new_tab(url=params.url)
        else:
            tab = session.browser.new_tab()

        session.update_tab_info()
        tab_id = resolve_tab_id(session, tab)
        if tab_id:
            session.active_tab_id = tab_id

        return {
            "success": True,
            "tab_id": tab_id,
            "url": getattr(tab, "url", ""),
            "title": getattr(tab, "title", ""),
        }

    @mcp.tool()
    @tool_handler
    async def dp_select_tab(params: SelectTabParams) -> dict:
        """Set the specified tab as the active tab."""
        session = get_session(params.browser_id)

        if params.tab_id.isdigit():
            tab = session.browser.get_tab(int(params.tab_id))
        else:
            tab = session.browser.get_tab(params.tab_id)

        if not tab:
            return {
                "success": False,
                "error": f"Tab not found: {params.tab_id}",
            }

        tab.set.activate()
        session.update_tab_info()
        resolved_tab_id = resolve_tab_id(session, tab)
        if resolved_tab_id:
            session.active_tab_id = resolved_tab_id
        return {
            "success": True,
            "tab_id": resolved_tab_id or params.tab_id,
            "url": getattr(tab, "url", ""),
            "title": getattr(tab, "title", ""),
        }

    @mcp.tool()
    @tool_handler
    async def dp_navigate(params: NavigateParams) -> dict:
        """Navigate to the specified URL in the current tab."""
        result = _run_on_active_tab(
            params.browser_id,
            lambda tab: tab.get(params.url, timeout=params.timeout),
        )
        # Surface title alongside URL.
        tab = get_tab(params.browser_id)
        result["title"] = getattr(tab, "title", "")
        return result

    @mcp.tool()
    @tool_handler
    async def dp_history_action(params: HistoryActionParams) -> dict:
        """Perform a browser history action: back / forward / refresh."""
        action_map = {
            "back": lambda tab: tab.back(),
            "forward": lambda tab: tab.forward(),
            "refresh": lambda tab: tab.refresh(),
        }
        return _run_on_active_tab(
            params.browser_id, action_map[params.action], action=params.action
        )

    @mcp.tool()
    @tool_handler
    async def dp_wait_doc_loaded(params: WaitBasicParams = None) -> dict:
        """Wait page DOM/document load completed."""
        if params is None:
            params = WaitBasicParams()
        tab = get_tab(params.browser_id)
        ok = bool(tab.wait.doc_loaded(timeout=params.timeout, raise_err=params.raise_error))
        return _wait_to_result(ok, "doc_loaded", params.timeout, {"url": getattr(tab, "url", "")})

    @mcp.tool()
    @tool_handler
    async def dp_wait_url_change(params: WaitTextChangeParams) -> dict:
        """Wait page URL changed by include/exclude rule."""
        tab = get_tab(params.browser_id)
        ok = bool(
            tab.wait.url_change(
                text=params.text,
                exclude=params.exclude,
                timeout=params.timeout,
                raise_err=params.raise_error,
            )
        )
        return _wait_to_result(
            ok,
            "url_change",
            params.timeout,
            {"text": params.text, "exclude": params.exclude, "url": getattr(tab, "url", "")},
        )

    @mcp.tool()
    @tool_handler
    async def dp_wait_new_tab(params: WaitNewTabParams = None) -> dict:
        """Wait for newly opened tab."""
        if params is None:
            params = WaitNewTabParams()

        session = get_session(params.browser_id)
        session.update_tab_info()

        curr_tab = params.curr_tab
        if curr_tab and curr_tab not in session.tabs:
            curr_tab = None

        browser_newest_tab_id = str(getattr(session.browser, "_newest_tab_id", "") or "")
        if not curr_tab and browser_newest_tab_id in session.tabs:
            curr_tab = browser_newest_tab_id
        if not curr_tab:
            active_tab_id = session.active_tab_id
            if active_tab_id in session.tabs:
                curr_tab = active_tab_id
        if not curr_tab and session.tabs:
            curr_tab = next(iter(session.tabs.keys()))

        # DrissionPage may keep a stale _newest_tab_id after the previously newest tab is closed.
        # Reset it to a live tab before waiting so BrowserWaiter.new_tab() can detect the next change.
        if curr_tab and browser_newest_tab_id not in session.tabs:
            try:
                session.browser._newest_tab_id = curr_tab
            except Exception:
                pass

        new_tab_id = session.browser.wait.new_tab(
            timeout=params.timeout,
            curr_tab=curr_tab,
            raise_err=params.raise_error,
        )
        if not new_tab_id:
            return _wait_to_result(False, "new_tab", params.timeout, {"curr_tab": curr_tab})

        tab = session.browser.get_tab(new_tab_id)
        session.update_tab_info()
        resolved_tab_id = resolve_tab_id(session, tab) or str(new_tab_id)
        session.active_tab_id = resolved_tab_id
        return {
            "success": True,
            "event": "new_tab",
            "timeout": params.timeout,
            "browser_id": session.browser_id,
            "tab_id": resolved_tab_id,
            "tab": _build_tab_dict(session, resolved_tab_id, tab),
        }
