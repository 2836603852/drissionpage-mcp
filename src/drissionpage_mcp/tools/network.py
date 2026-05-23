# -*- coding: utf-8 -*-
"""
DrissionPage MCP network listening tools.
"""

import json
import time
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ..exceptions import NetworkTimeoutError
from ._common import get_tab, tool_handler

# ============ Parameter Models ============

class ListenStartParams(BaseModel):
    """Start-listening parameters."""
    targets: Union[str, List[str]] = Field(..., description="URL patterns or keywords to listen for")
    is_regex: bool = Field(False, description="Use regex pattern matching")
    method: Optional[Union[str, List[str], bool]] = Field(None, description="HTTP method filters")
    res_type: Optional[Union[str, List[str], bool]] = Field(None, description="Resource type filters")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class ListenWaitParams(BaseModel):
    """Wait-for-packet parameters."""
    timeout: float = Field(10.0, description="Wait timeout in seconds")
    raise_error: bool = Field(False, description="Raise timeout error when no packet is captured")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class CaptureApiParams(BaseModel):
    """One-shot API capture parameters."""
    url_pattern: str = Field(..., description="URL matching pattern")
    method: Optional[str] = Field(None, description="Optional HTTP method filter, e.g. 'POST'")
    timeout: float = Field(10.0, description="Wait timeout in seconds")
    trigger_action: Optional[str] = Field(None, description="Optional trigger action description")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


# ============ Helper Functions ============

def _is_packet_valid(packet: Any) -> bool:
    """Return True if captured packet object is valid."""
    return bool(packet) and not isinstance(packet, (list, tuple))


def _wait_one_packet(tab, timeout: float):
    """Wait one packet with bounded timeout."""
    packet = tab.listen.wait(timeout=timeout)
    if _is_packet_valid(packet):
        return packet
    if isinstance(packet, (list, tuple)):
        for item in packet:
            if _is_packet_valid(item):
                return item
    return None


def _parse_packet(packet) -> Dict[str, Any]:
    """Normalize captured packet payload."""
    request_payload: Dict[str, Any] = {}
    response_payload: Dict[str, Any] = {}
    result = {
        "tab_id": str(getattr(packet, "tab_id", "")),
        "target": getattr(packet, "target", None),
        "is_failed": bool(getattr(packet, "is_failed", False)),
        "url": getattr(packet, "url", ""),
        "method": getattr(packet, "method", ""),
        "frame_id": getattr(packet, "frameId", None),
        "resource_type": getattr(packet, "resourceType", ""),
    }

    request = getattr(packet, "request", None)
    if request:
        request_payload = {
            "url": getattr(request, "url", result["url"]),
            "method": getattr(request, "method", result["method"]),
            "headers": dict(getattr(request, "headers", {}) or {}),
            "params": dict(getattr(request, "params", {}) or {}),
            "post_data": None,
        }
        body = getattr(request, "postData", None)
        if body:
            if isinstance(body, str):
                request_payload["post_data"] = body[:5000]
            else:
                try:
                    request_payload["post_data"] = str(body)[:5000]
                except Exception:
                    pass

    response = getattr(packet, "response", None)
    if response:
        response_payload = {
            "status": getattr(response, "statusCode", None),
            "status_text": getattr(response, "statusText", None),
            "headers": dict(getattr(response, "headers", {}) or {}),
            "body": None,
        }

        body = getattr(response, "body", None)
        if body:
            if isinstance(body, str):
                try:
                    response_payload["body"] = json.loads(body)
                except Exception:
                    response_payload["body"] = body[:10000]
            elif isinstance(body, (dict, list)):
                response_payload["body"] = body
            else:
                try:
                    response_payload["body"] = str(body)[:10000]
                except Exception:
                    pass

    if result["is_failed"]:
        fail_info = getattr(packet, "fail_info", None)
        if fail_info:
            result["fail_info"] = {
                "error_text": getattr(fail_info, "errorText", None),
                "blocked_reason": getattr(fail_info, "blockedReason", None),
                "canceled": getattr(fail_info, "canceled", None),
            }

    result["request"] = request_payload
    result["response"] = response_payload
    return result


def _packet_result(packet_info: Dict[str, Any]) -> Dict[str, Any]:
    """Return unified packet/result payload."""
    return {
        "packet": packet_info,
        "request": packet_info.get("request", {}),
        "response": packet_info.get("response", {}),
    }


def _safe_listener_status(listener) -> Dict[str, Any]:
    """Build listener status payload (best-effort, may rely on DP private fields).

    DrissionPage exposes ``listener.listening`` and ``listener.targets`` as public
    attributes; the rest (``_is_regex``, ``_method``, ``_running_*``) are private
    and may break across DP versions. Returned values are best-effort.
    """
    if listener is None:
        return {
            "is_listening": False,
            "targets": [],
            "is_regex": False,
            "methods": [],
            "resource_types": [],
            "running_requests": 0,
            "running_targets": 0,
        }

    def _normalize_filter(value):
        if value is True:
            return True
        if isinstance(value, set):
            return sorted(value)
        if isinstance(value, (list, tuple)):
            return list(value)
        return value

    try:
        targets_raw = getattr(listener, "targets", [])
        if targets_raw is True:
            targets = True
        elif isinstance(targets_raw, set):
            targets = sorted(targets_raw)
        else:
            targets = list(targets_raw or [])
    except Exception:
        targets = []

    return {
        "is_listening": bool(getattr(listener, "listening", False)),
        "targets": targets,
        "is_regex": bool(getattr(listener, "_is_regex", False)),
        "methods": _normalize_filter(getattr(listener, "_method", [])),
        "resource_types": _normalize_filter(getattr(listener, "_res_type", [])),
        "running_requests": int(getattr(listener, "_running_requests", 0) or 0),
        "running_targets": int(getattr(listener, "_running_targets", 0) or 0),
    }


def register_network_tools(mcp):
    """Register network listening tools."""

    @mcp.tool()
    @tool_handler
    async def dp_listen_start(params: ListenStartParams) -> dict:
        """Start listening to network requests

        Start network listening for matching requests (XHR/Fetch/WebSocket).
        """
        tab = get_tab(params.browser_id)
        tab.listen.start(
            params.targets,
            is_regex=params.is_regex,
            method=params.method,
            res_type=params.res_type,
        )
        status = _safe_listener_status(getattr(tab, "listen", None))

        return {
            "success": True,
            **status,
            "message": "Listening started",
        }

    @mcp.tool()
    @tool_handler
    async def dp_listen_wait(params: ListenWaitParams = None) -> dict:
        """Wait for one captured packet

        Wait for and return one network packet captured by current listener.
        """
        if params is None:
            params = ListenWaitParams()

        tab = get_tab(params.browser_id)
        packet = _wait_one_packet(tab, timeout=params.timeout)

        if packet is None:
            if params.raise_error:
                raise NetworkTimeoutError(f"Timed out waiting for packet: {params.timeout}s")
            return {
                "success": False,
                "error": "Timeout waiting for packet",
                "timeout": params.timeout,
            }

        packet_info = _parse_packet(packet)
        return {
            "success": True,
            **_packet_result(packet_info),
        }

    @mcp.tool()
    @tool_handler
    async def dp_capture_api(params: CaptureApiParams) -> dict:
        """Capture API response in one call

        Start listening, wait for one matching packet, then stop listening. Method
        filtering is delegated to the underlying listener; we do not re-filter here.
        """
        tab = get_tab(params.browser_id)
        if params.method:
            tab.listen.start(params.url_pattern, method=params.method)
        else:
            tab.listen.start(params.url_pattern)

        try:
            deadline = time.time() + max(0.1, float(params.timeout))
            packet_info = None
            while time.time() < deadline:
                remaining = deadline - time.time()
                packet = _wait_one_packet(tab, timeout=max(0.1, remaining))
                if packet is None:
                    break
                candidate = _parse_packet(packet)
                if not candidate.get("url"):
                    continue
                packet_info = candidate
                break

            if not packet_info:
                return {
                    "success": False,
                    "error": "Timeout waiting for API response",
                    "url_pattern": params.url_pattern,
                }

            return {
                "success": True,
                **_packet_result(packet_info),
                "url": packet_info.get("url"),
                "method": packet_info.get("method"),
                "trigger_action": params.trigger_action,
            }
        finally:
            try:
                tab.listen.stop()
            except Exception:
                pass
