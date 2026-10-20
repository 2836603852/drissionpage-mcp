# -*- coding: utf-8 -*-
"""Tool-level smoke tests using a fake mcp collector + monkey-patched browser.

These tests don't need a real Chromium; we inject fake tab/browser objects
through the ``browser_manager`` singleton and verify each tool's response
shape and error handling. Goal: catch tool-layer regressions (wiring,
parameter parsing, response payload), not DrissionPage's own behaviour.
"""

import asyncio
from types import SimpleNamespace
from typing import Any, Callable, Dict

import pytest

from drissionpage_mcp.browser_manager import BrowserSession, TabInfo, browser_manager
from drissionpage_mcp.tools.actions import register_actions_tools
from drissionpage_mcp.tools.element_operations import (
    GetPageContentParams,
    register_element_operations_tools,
)
from drissionpage_mcp.tools.javascript import RunJsParams, register_javascript_tools
from drissionpage_mcp.tools.network import register_network_tools
from drissionpage_mcp.tools.page_management import (
    ConnectBrowserParams,
    HistoryActionParams,
    NavigateParams,
    register_page_management_tools,
)
from drissionpage_mcp.tools.screenshot import register_screenshot_tools


class _ToolCollector:
    """Stand-in for ``FastMCP`` that just collects decorated tool callables."""

    def __init__(self):
        self.tools: Dict[str, Callable[..., Any]] = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


@pytest.fixture
def tools():
    """Collect all registered tools into a name->callable dict."""
    mcp = _ToolCollector()
    register_actions_tools(mcp)
    register_element_operations_tools(mcp)
    register_javascript_tools(mcp)
    register_network_tools(mcp)
    register_page_management_tools(mcp)
    register_screenshot_tools(mcp)
    return mcp.tools


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Clear singleton state — never replace the instance itself, because
    tool modules already hold a reference via ``from ..browser_manager
    import browser_manager`` and rebinding the module attribute won't
    reach them."""
    browser_manager.sessions.clear()
    browser_manager.default_session_id = None
    browser_manager.fixed_debug_port = None
    yield
    browser_manager.sessions.clear()
    browser_manager.default_session_id = None
    browser_manager.fixed_debug_port = None


def _run(coro):
    return asyncio.run(coro)


# ---------- fake browser/tab plumbing ----------

class _FakeTab:
    def __init__(self, url="https://example.com", title="Example",
                 html="<html><body>hi</body></html>"):
        self.url = url
        self.title = title
        self.html = html
        self.calls = []

    def get(self, url, timeout=None):
        self.url = url
        self.calls.append(("get", url, timeout))

    def back(self):
        self.calls.append(("back",))

    def forward(self):
        self.calls.append(("forward",))

    def refresh(self):
        self.calls.append(("refresh",))

    def run_js(self, script, *args, timeout=None):
        self.calls.append(("run_js", script))
        if "navigator.userAgent" in script:
            return "FakeUA/1.0"
        if "innerText" in script:
            return "hello world"
        return {"ok": True, "script_len": len(script)}


def _install_fake_session(tab: _FakeTab) -> BrowserSession:
    """Inject a session into the live singleton whose active tab is ``tab``."""
    session = BrowserSession(
        browser_id="fake-1",
        browser=SimpleNamespace(tab_ids=[], get_tab=lambda *a, **k: tab, latest_tab=tab),
        debug_port=9223,
        debugger_address="127.0.0.1:9223",
    )
    session.tabs = {"t1": TabInfo(tab_id="t1", tab=tab, url=tab.url, title=tab.title)}
    session.active_tab_id = "t1"
    # Bypass update_tab_info's dependency on a real Chromium.
    session.update_tab_info = lambda: None
    browser_manager.sessions[session.browser_id] = session
    browser_manager.default_session_id = session.browser_id
    return session


# ---------- tests ----------


@pytest.mark.parametrize("params", [None, ConnectBrowserParams()])
def test_connect_browser_accepts_omitted_address(tools, monkeypatch, params):
    calls = []

    def connect(address, browser_id):
        calls.append((address, browser_id))
        return SimpleNamespace(browser_id="attached", debug_port=9223,
                               debugger_address="127.0.0.1:9223", tabs={})

    monkeypatch.setattr(browser_manager, "connect_browser", connect)
    out = _run(tools["dp_connect_browser"](params))
    assert out["success"] is True
    assert out["debug_port"] == 9223
    assert calls == [(None, None)]


def test_connect_browser_forwards_custom_address_and_id(tools, monkeypatch):
    calls = []

    def connect(address, browser_id):
        calls.append((address, browser_id))
        return SimpleNamespace(browser_id=browser_id, debug_port=38318,
                               debugger_address=address, tabs={})

    monkeypatch.setattr(browser_manager, "connect_browser", connect)
    out = _run(tools["dp_connect_browser"](
        ConnectBrowserParams(address="127.0.0.1:38318", browser_id="shop")
    ))
    assert out["success"] is True
    assert out["browser_id"] == "shop"
    assert out["debugger_address"] == "127.0.0.1:38318"
    assert calls == [("127.0.0.1:38318", "shop")]

def test_navigate_returns_success_and_url(tools):
    tab = _FakeTab(url="https://old.example.com")
    _install_fake_session(tab)

    out = _run(tools["dp_navigate"](NavigateParams(url="https://new.example.com")))
    assert out["success"] is True
    assert out["url"] == "https://new.example.com"
    assert tab.calls[0][0] == "get"


def test_history_action_routes_to_correct_call(tools):
    tab = _FakeTab()
    _install_fake_session(tab)

    out = _run(tools["dp_history_action"](HistoryActionParams(action="back")))
    assert out["success"] is True
    assert out["action"] == "back"
    assert tab.calls[-1] == ("back",)

    _run(tools["dp_history_action"](HistoryActionParams(action="forward")))
    assert tab.calls[-1] == ("forward",)

    _run(tools["dp_history_action"](HistoryActionParams(action="refresh")))
    assert tab.calls[-1] == ("refresh",)


def test_get_page_content_html_mode(tools):
    tab = _FakeTab(html="<html><body><p>page-body</p></body></html>")
    _install_fake_session(tab)

    out = _run(tools["dp_get_page_content"](GetPageContentParams(mode="html")))
    assert out["success"] is True
    assert out["mode"] == "html"
    assert "page-body" in out["content"]
    assert out["truncated"] is False


def test_get_page_content_text_mode_uses_js(tools):
    tab = _FakeTab()
    _install_fake_session(tab)

    out = _run(tools["dp_get_page_content"](GetPageContentParams(mode="text")))
    assert out["success"] is True
    assert out["mode"] == "text"
    assert out["content"] == "hello world"


def test_run_js_normalizes_dict_result(tools):
    tab = _FakeTab()
    _install_fake_session(tab)

    out = _run(tools["dp_run_js"](RunJsParams(script="return 1+1")))
    assert out["success"] is True
    assert out["result"]["ok"] is True


def test_browser_not_connected_returns_structured_error(tools):
    # No session installed — get_tab() raises BrowserNotConnectedError,
    # tool_handler translates it into a structured payload.
    out = _run(tools["dp_run_js"](RunJsParams(script="return 1")))
    assert out["success"] is False
    assert out["error_type"] == "BrowserNotConnectedError"


def test_list_browsers_empty(tools):
    out = _run(tools["dp_list_browsers"]())
    assert out["success"] is True
    assert out["browsers"] == []
    assert out["default_browser_id"] is None


def test_list_browsers_with_one_session(tools):
    tab = _FakeTab()
    _install_fake_session(tab)

    out = _run(tools["dp_list_browsers"]())
    assert out["success"] is True
    assert len(out["browsers"]) == 1
    assert out["default_browser_id"] == "fake-1"
