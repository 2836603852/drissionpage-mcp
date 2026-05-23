# -*- coding: utf-8 -*-
"""Unit tests for pure helper functions in tools modules."""

import asyncio
from types import SimpleNamespace

from drissionpage_mcp.exceptions import (
    BrowserNotConnectedError,
    DrissionPageMcpError,
    ElementNotFoundError,
)
from drissionpage_mcp.tools._common import tool_handler
from drissionpage_mcp.tools.element_operations import _normalize_file_paths, _truncate
from drissionpage_mcp.tools.network import _is_packet_valid, _parse_packet, _safe_listener_status

# ---------- element_operations helpers ----------

def test_normalize_file_paths_string_input():
    assert _normalize_file_paths("a.png") == ["a.png"]


def test_normalize_file_paths_list_input():
    assert _normalize_file_paths(["a.png", " b.png ", "", "  "]) == ["a.png", " b.png "]


def test_normalize_file_paths_filters_blank_only():
    assert _normalize_file_paths(["", "   "]) == []


def test_truncate_short_text_unchanged():
    text, truncated, total = _truncate("hello", 100)
    assert (text, truncated, total) == ("hello", False, 5)


def test_truncate_long_text_clipped_with_metadata():
    text, truncated, total = _truncate("x" * 200, 50)
    assert truncated is True
    assert total == 200
    assert len(text) == 50


def test_truncate_handles_none():
    assert _truncate(None, 100) == ("", False, 0)


# ---------- network helpers ----------

def test_is_packet_valid():
    assert _is_packet_valid(SimpleNamespace(url="x")) is True
    assert _is_packet_valid(None) is False
    assert _is_packet_valid([]) is False
    assert _is_packet_valid(()) is False


def test_parse_packet_extracts_request_response():
    packet = SimpleNamespace(
        tab_id="t1",
        target="api",
        is_failed=False,
        url="https://api.example.com/x",
        method="POST",
        frameId="f1",
        resourceType="XHR",
        request=SimpleNamespace(
            url="https://api.example.com/x",
            method="POST",
            headers={"X-Test": "1"},
            params={"k": "v"},
            postData='{"a":1}',
        ),
        response=SimpleNamespace(
            statusCode=200,
            statusText="OK",
            headers={"Content-Type": "application/json"},
            body='{"ok": true}',
        ),
    )
    parsed = _parse_packet(packet)
    assert parsed["tab_id"] == "t1"
    assert parsed["url"] == "https://api.example.com/x"
    assert parsed["method"] == "POST"
    assert parsed["request"]["headers"] == {"X-Test": "1"}
    assert parsed["request"]["post_data"] == '{"a":1}'
    # Body should be decoded to dict when valid JSON.
    assert parsed["response"]["body"] == {"ok": True}


def test_parse_packet_keeps_raw_body_on_invalid_json():
    packet = SimpleNamespace(
        tab_id="t1",
        target=None,
        is_failed=False,
        url="https://x",
        method="GET",
        frameId=None,
        resourceType="",
        request=None,
        response=SimpleNamespace(
            statusCode=200,
            statusText="OK",
            headers={},
            body="not json",
        ),
    )
    assert _parse_packet(packet)["response"]["body"] == "not json"


def test_safe_listener_status_no_listener():
    status = _safe_listener_status(None)
    assert status["is_listening"] is False
    assert status["targets"] == []


def test_safe_listener_status_normalizes_set_methods():
    listener = SimpleNamespace(
        listening=True,
        targets={"a", "b"},
        _is_regex=False,
        _method={"GET", "POST"},
        _res_type=True,
        _running_requests=2,
        _running_targets=1,
    )
    status = _safe_listener_status(listener)
    assert status["is_listening"] is True
    assert status["targets"] == ["a", "b"]
    assert status["methods"] == ["GET", "POST"]
    assert status["resource_types"] is True
    assert status["running_requests"] == 2


# ---------- tool_handler decorator ----------

def _run(coro):
    return asyncio.run(coro)


def test_tool_handler_passes_through_success():
    @tool_handler
    async def fn(payload):
        return {"success": True, "value": payload}

    out = _run(fn(42))
    assert out == {"success": True, "value": 42}


def test_tool_handler_translates_drissionpage_error_via_to_dict():
    @tool_handler
    async def fn():
        raise ElementNotFoundError("#x", 5.0)

    out = _run(fn())
    assert out["success"] is False
    assert out["error_type"] == "ElementNotFoundError"
    assert out["details"] == {"locator": "#x", "timeout": 5.0}


def test_tool_handler_translates_browser_not_connected():
    @tool_handler
    async def fn():
        raise BrowserNotConnectedError("Browser not connected")

    out = _run(fn())
    assert out["success"] is False
    assert out["error_type"] == "BrowserNotConnectedError"
    assert out["message"] == "Browser not connected"


def test_tool_handler_falls_back_for_unknown_exception():
    @tool_handler
    async def fn():
        raise RuntimeError("boom")

    out = _run(fn())
    assert out == {"success": False, "error": "boom"}


def test_drissionpage_mcp_error_to_dict_shape():
    err = DrissionPageMcpError("oops", details={"why": "test"})
    assert err.to_dict() == {
        "success": False,
        "error": True,
        "error_type": "DrissionPageMcpError",
        "message": "oops",
        "details": {"why": "test"},
    }
