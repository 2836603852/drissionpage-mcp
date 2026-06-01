# -*- coding: utf-8 -*-
"""
DrissionPage MCP WebSocket frame tools.

``dp_listen_*`` (network.py) captures HTTP request/response packets, but it does
*not* surface individual WebSocket frames. WS frames arrive as a stream of CDP
events (``Network.webSocketFrameReceived`` / ``...Sent``), which the one-shot
``dp_run_cdp`` cannot subscribe to. This module registers driver-level callbacks
(``driver.set_callback``) that accumulate frames into a bounded, thread-safe
server-side buffer, then exposes tools to drain and group them.

Mirrors the listen/wait/stop shape already used for HTTP packets.
"""

import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from pydantic import BaseModel, Field

from ._common import get_driver, get_tab, tab_key, tool_handler

# ============ Parameter Models ============

class WsListenStartParams(BaseModel):
    """Start WebSocket frame capture."""
    max_frames: int = Field(2000, description="Ring-buffer capacity; oldest frames drop first")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class WsGetFramesParams(BaseModel):
    """Read captured WebSocket frames."""
    wsid: Optional[str] = Field(None, description="Filter by a single WebSocket connection id (CDP requestId)")
    direction: Optional[str] = Field(None, description="Filter by direction: 'received' or 'sent'")
    limit: int = Field(100, description="Max frames to return (most recent first)")
    drain: bool = Field(False, description="If true, remove returned frames from the buffer")
    decode_json: bool = Field(True, description="Best-effort parse of JSON text payloads (opcode==1 only; opcode!=1 payloads are base64 binary per CDP and left untouched)")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class WsStopParams(BaseModel):
    """Stop WebSocket frame capture."""
    clear: bool = Field(True, description="Clear the buffer after detaching callbacks")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


# ============ Server-side capture state ============

# CDP event names for the WebSocket lifecycle.
_EV_CREATED = "Network.webSocketCreated"
_EV_RECV = "Network.webSocketFrameReceived"
_EV_SENT = "Network.webSocketFrameSent"
_EV_CLOSED = "Network.webSocketClosed"

_LOCK = threading.Lock()
_BUFFERS: Dict[str, Deque[Dict[str, Any]]] = {}
_CONNS: Dict[str, Dict[str, Dict[str, Any]]] = {}   # key -> {wsid: {url, created_ts}}


def _push(key: str, frame: Dict[str, Any]) -> None:
    with _LOCK:
        buf = _BUFFERS.get(key)
        if buf is not None:
            buf.append(frame)


def _make_frame_cb(key: str, direction: str):
    def _cb(**kwargs):
        resp = kwargs.get("response") or {}
        payload = resp.get("payloadData")
        _push(key, {
            "ts": kwargs.get("timestamp"),
            "wsid": str(kwargs.get("requestId", "")),
            "direction": direction,
            "opcode": resp.get("opcode"),
            "mask": resp.get("mask"),
            "len": len(payload) if isinstance(payload, str) else None,
            "payload": payload,
        })
    return _cb


def _make_created_cb(key: str):
    def _cb(**kwargs):
        wsid = str(kwargs.get("requestId", ""))
        with _LOCK:
            _CONNS.setdefault(key, {})[wsid] = {
                "url": kwargs.get("url"),
                "created_ts": time.time(),
            }
    return _cb


def _make_closed_cb(key: str):
    def _cb(**kwargs):
        wsid = str(kwargs.get("requestId", ""))
        with _LOCK:
            conns = _CONNS.get(key)
            if conns and wsid in conns:
                conns[wsid]["closed_ts"] = time.time()
    return _cb


def _maybe_decode(payload: Any, opcode: Any, decode_json: bool):
    # Per CDP, only opcode==1 is UTF-8 text; opcode!=1 payloadData is base64
    # binary and must be left untouched (matches the param docstring).
    if not decode_json or opcode != 1 or not isinstance(payload, str):
        return payload
    s = payload.lstrip()
    if not s or s[0] not in "{[":
        return payload
    try:
        import json
        return json.loads(payload)
    except Exception:
        return payload


def register_websocket_tools(mcp):
    """Register WebSocket frame capture tools."""

    @mcp.tool()
    @tool_handler
    async def dp_ws_listen_start(params: WsListenStartParams) -> dict:
        """Start WebSocket frame capture

        Enable the Network domain and subscribe to WebSocket lifecycle/frame
        events on the active tab. Frames stream into a bounded server-side
        buffer; read them with ``dp_ws_get_frames``.
        """
        tab = get_tab(params.browser_id)
        driver = get_driver(tab)
        key = tab_key(tab)

        # Network.enable is idempotent; DrissionPage's own listener may also use
        # it, so we never disable it on stop (only detach our frame callbacks).
        tab.run_cdp("Network.enable")

        with _LOCK:
            resumed = key in _BUFFERS
            # Idempotent: re-calling does NOT wipe frames already captured.
            # To start fresh, call dp_ws_stop(clear=True) first.
            if not resumed:
                _BUFFERS[key] = deque(maxlen=max(1, params.max_frames))
            _CONNS.setdefault(key, {})

        driver.set_callback(_EV_CREATED, _make_created_cb(key))
        driver.set_callback(_EV_RECV, _make_frame_cb(key, "received"))
        driver.set_callback(_EV_SENT, _make_frame_cb(key, "sent"))
        driver.set_callback(_EV_CLOSED, _make_closed_cb(key))

        return {
            "success": True,
            "tab": key,
            "resumed": resumed,
            "max_frames": params.max_frames if not resumed else _BUFFERS[key].maxlen,
            "events": [_EV_CREATED, _EV_RECV, _EV_SENT, _EV_CLOSED],
            "hint": ("Resumed existing capture (buffer kept); dp_ws_stop(clear=True) to reset."
                     if resumed else "Trigger WS traffic, then call dp_ws_get_frames."),
        }

    @mcp.tool()
    @tool_handler
    async def dp_ws_get_frames(params: WsGetFramesParams) -> dict:
        """Read captured WebSocket frames

        Return buffered frames (most recent first), optionally filtered by
        connection id / direction. JSON text payloads are parsed by default.
        """
        tab = get_tab(params.browser_id)
        key = tab_key(tab)

        with _LOCK:
            buf = _BUFFERS.get(key)
            if buf is None:
                return {"success": False, "error": "WS capture not started for this tab"}
            # Snapshot (shallow) under the lock, then compute the reported count
            # under the lock too — never touch `buf` after releasing it.
            frames: List[Dict[str, Any]] = list(buf)
            conns = dict(_CONNS.get(key, {}))
            total_buffered = len(buf)
            if params.drain:
                buf.clear()

        if params.wsid:
            frames = [f for f in frames if f["wsid"] == params.wsid]
        if params.direction:
            frames = [f for f in frames if f["direction"] == params.direction]

        frames = list(reversed(frames))[: max(0, params.limit)]
        # Copy each frame before decoding so we never mutate the dicts still
        # referenced by the ring buffer (non-draining reads stay non-destructive).
        out = []
        for f in frames:
            g = dict(f)
            g["payload"] = _maybe_decode(g.get("payload"), g.get("opcode"), params.decode_json)
            out.append(g)

        return {
            "success": True,
            "tab": key,
            "total_buffered": total_buffered,
            "returned": len(out),
            "connections": conns,
            "frames": out,
        }

    @mcp.tool()
    @tool_handler
    async def dp_ws_stop(params: WsStopParams) -> dict:
        """Stop WebSocket frame capture

        Detach the frame callbacks (leaves Network.enable in place). Optionally
        clear the buffer.
        """
        tab = get_tab(params.browser_id)
        driver = get_driver(tab)
        key = tab_key(tab)

        for ev in (_EV_CREATED, _EV_RECV, _EV_SENT, _EV_CLOSED):
            driver.set_callback(ev, None)

        with _LOCK:
            buffered = len(_BUFFERS.get(key, []))
            if params.clear:
                _BUFFERS.pop(key, None)
                _CONNS.pop(key, None)

        return {"success": True, "tab": key, "buffered_before_clear": buffered}
