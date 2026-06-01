# -*- coding: utf-8 -*-
"""
DrissionPage MCP interactive debugger tools.

The one-shot ``dp_run_cdp`` can *send* ``Debugger.*`` commands but cannot
*receive* the ``Debugger.paused`` event, so on its own it can set a breakpoint
yet never know when/where execution stopped. This module subscribes to the
Debugger event stream via ``driver.set_callback`` and keeps the current paused
state server-side, exposing a normal set-breakpoint / inspect / step / resume
workflow plus on-frame expression evaluation (the part that actually matters
for reversing: reading variables at the pause site).

Notes / constraints:
- While JS is paused the renderer is frozen, but ``Debugger.*`` commands travel
  on the CDP control channel and still work, so stepping is safe.
- Callbacks fire on DrissionPage's CDP event thread; paused state is guarded by
  a lock.
"""

import asyncio
import threading
import time
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from ._common import get_driver, get_session, get_tab, tab_key, tool_handler

# ============ Parameter Models ============

class DebuggerEnableParams(BaseModel):
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class SetBreakpointParams(BaseModel):
    """Set a URL/line breakpoint (Debugger.setBreakpointByUrl)."""
    url: Optional[str] = Field(None, description="Exact script URL to break in")
    url_regex: Optional[str] = Field(None, description="Regex matching script URL (use instead of url)")
    line: int = Field(..., description="0-based line number")
    column: Optional[int] = Field(None, description="0-based column number")
    condition: Optional[str] = Field(None, description="JS condition expression; break only when truthy")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class XhrBreakpointParams(BaseModel):
    """Break when an XHR/fetch URL contains a substring (DOMDebugger.setXHRBreakpoint)."""
    url_substring: str = Field("", description="Substring to match; empty string breaks on any request")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class RemoveBreakpointParams(BaseModel):
    breakpoint_id: str = Field(..., description="Breakpoint id returned by dp_set_breakpoint")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class StepParams(BaseModel):
    """Step / resume control."""
    wait: float = Field(2.0, description="Seconds to wait for the next paused event (0 = don't wait)")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class StatusParams(BaseModel):
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class EvalOnFrameParams(BaseModel):
    """Evaluate an expression in a paused call frame (Debugger.evaluateOnCallFrame)."""
    expression: str = Field(..., description="JS expression to evaluate at the pause site")
    call_frame_id: Optional[str] = Field(None, description="Target call frame id; defaults to the top frame")
    return_by_value: bool = Field(True, description="Return a JSON value instead of a remote object handle")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


# ============ Server-side debugger state ============

_LOCK = threading.Lock()
# key -> {"paused": <summary or None>, "scripts": {scriptId: url}, "enabled": bool}
_STATE: Dict[str, Dict[str, Any]] = {}


def _state(key: str) -> Dict[str, Any]:
    st = _STATE.get(key)
    if st is None:
        st = {"paused": None, "scripts": {}, "enabled": False, "event": threading.Event()}
        _STATE[key] = st
    return st


def _get_event(key: str) -> threading.Event:
    with _LOCK:
        return _state(key)["event"]


def _prune_dead(browser_id: Optional[str]) -> None:
    """Drop state for tabs that no longer exist, bounding _STATE growth."""
    try:
        session = get_session(browser_id)
        live = set(session.tabs.keys())
    except Exception:
        return
    with _LOCK:
        for k in [k for k in _STATE if k not in live]:
            _STATE.pop(k, None)


def _summarize_paused(scripts: Dict[str, str], kwargs: Dict[str, Any]) -> Dict[str, Any]:
    frames = []
    for fr in kwargs.get("callFrames", []) or []:
        loc = fr.get("location", {}) or {}
        sid = str(loc.get("scriptId", ""))
        frames.append({
            "callFrameId": fr.get("callFrameId"),
            "functionName": fr.get("functionName") or "(anonymous)",
            "url": fr.get("url") or scripts.get(sid, ""),
            "scriptId": sid,
            "line": loc.get("lineNumber"),
            "column": loc.get("columnNumber"),
            "scopes": [s.get("type") for s in (fr.get("scopeChain") or [])],
        })
    return {
        "reason": kwargs.get("reason"),
        "hitBreakpoints": kwargs.get("hitBreakpoints") or [],
        "frame_count": len(frames),
        "callFrames": frames,
        "captured_at": time.time(),
    }


def _make_paused_cb(key: str):
    def _cb(**kwargs):
        with _LOCK:
            st = _state(key)
            st["paused"] = _summarize_paused(st["scripts"], kwargs)
            st["event"].set()
    return _cb


def _make_resumed_cb(key: str):
    def _cb(**kwargs):
        with _LOCK:
            _state(key)["paused"] = None
    return _cb


def _make_script_cb(key: str):
    def _cb(**kwargs):
        sid = str(kwargs.get("scriptId", ""))
        url = kwargs.get("url") or ""
        if sid:
            with _LOCK:
                scripts = _state(key)["scripts"]
                if len(scripts) < 5000:
                    scripts[sid] = url
    return _cb


def _get_paused(key: str):
    with _LOCK:
        st = _STATE.get(key)
        return st["paused"] if st else None


def _wait_for_pause_blocking(key: str, timeout: float):
    """Block on the pause Event (run via asyncio.to_thread so the event loop
    is never stalled). Event-driven, so a re-pause wakes immediately instead of
    being missed by a fixed-interval poll."""
    if timeout > 0:
        _get_event(key).wait(timeout)
    return _get_paused(key)


def _ensure_enabled(tab, driver, key: str):
    """Idempotently enable the Debugger domain + subscribe to events. Auto-called
    by set-breakpoint so a breakpoint can never freeze the page with no listener."""
    with _LOCK:
        already = _state(key)["enabled"]
        _state(key)["enabled"] = True
    if already:
        return {"already_enabled": True}
    driver.set_callback("Debugger.scriptParsed", _make_script_cb(key))
    driver.set_callback("Debugger.paused", _make_paused_cb(key))
    driver.set_callback("Debugger.resumed", _make_resumed_cb(key))
    return tab.run_cdp("Debugger.enable")


def _top_frame_id(key: str) -> Optional[str]:
    paused = _get_paused(key)
    if paused and paused.get("callFrames"):
        return paused["callFrames"][0].get("callFrameId")
    return None


def register_debugger_tools(mcp):
    """Register interactive debugger tools."""

    @mcp.tool()
    @tool_handler
    async def dp_debugger_enable(params: DebuggerEnableParams) -> dict:
        """Enable the interactive debugger

        Turn on the Debugger domain and subscribe to paused/resumed/scriptParsed
        events on the active tab. Required before setting breakpoints.
        """
        tab = get_tab(params.browser_id)
        driver = get_driver(tab)
        key = tab_key(tab)
        _prune_dead(params.browser_id)
        # Idempotent: re-enabling never wipes a live paused summary.
        result = _ensure_enabled(tab, driver, key)
        return {"success": True, "tab": key, "debugger": result}

    @mcp.tool()
    @tool_handler
    async def dp_set_breakpoint(params: SetBreakpointParams) -> dict:
        """Set a line breakpoint

        Break at ``line`` (0-based) in a script identified by ``url`` or
        ``url_regex``. Optional ``condition`` makes it conditional.
        """
        tab = get_tab(params.browser_id)
        if not params.url and not params.url_regex:
            return {"success": False, "error": "Provide url or url_regex"}
        if params.line < 0:
            return {"success": False, "error": "line must be >= 0"}
        # Auto-enable so the breakpoint's pause is always observed (never a
        # frozen page with no server-side record).
        _ensure_enabled(tab, get_driver(tab), tab_key(tab))

        args: Dict[str, Any] = {"lineNumber": params.line}
        if params.url_regex:
            args["urlRegex"] = params.url_regex
        else:
            args["url"] = params.url
        if params.column is not None:
            args["columnNumber"] = params.column
        if params.condition:
            args["condition"] = params.condition

        result = tab.run_cdp("Debugger.setBreakpointByUrl", **args)
        return {"success": True, "breakpoint": result}

    @mcp.tool()
    @tool_handler
    async def dp_set_xhr_breakpoint(params: XhrBreakpointParams) -> dict:
        """Break on XHR/fetch

        Pause when a request URL contains ``url_substring`` (empty = any). Pauses
        land in the Debugger just like a line breakpoint.
        """
        tab = get_tab(params.browser_id)
        # Auto-enable Debugger so the XHR pause is observed, not a silent freeze.
        _ensure_enabled(tab, get_driver(tab), tab_key(tab))
        result = tab.run_cdp("DOMDebugger.setXHRBreakpoint", url=params.url_substring)
        return {"success": True, "url_substring": params.url_substring, "result": result}

    @mcp.tool()
    @tool_handler
    async def dp_remove_breakpoint(params: RemoveBreakpointParams) -> dict:
        """Remove a line breakpoint by id."""
        tab = get_tab(params.browser_id)
        result = tab.run_cdp("Debugger.removeBreakpoint", breakpointId=params.breakpoint_id)
        return {"success": True, "removed": params.breakpoint_id, "result": result}

    @mcp.tool()
    @tool_handler
    async def dp_debugger_status(params: StatusParams) -> dict:
        """Report current pause state

        Non-blocking read of whether execution is paused and, if so, the current
        call stack summary (function / url / line / scope types per frame).
        """
        tab = get_tab(params.browser_id)
        key = tab_key(tab)
        # Single lock acquisition → consistent snapshot of all three fields.
        with _LOCK:
            st = _STATE.get(key) or {}
            paused = st.get("paused")
            enabled = bool(st.get("enabled"))
            script_count = len(st.get("scripts", {}))
        return {
            "success": True,
            "tab": key,
            "enabled": enabled,
            "is_paused": paused is not None,
            "scripts_seen": script_count,
            "paused": paused,
        }

    def _step(cmd: str):
        async def _runner(params: StepParams) -> dict:
            tab = get_tab(params.browser_id)
            key = tab_key(tab)
            with _LOCK:
                st = _state(key)
                if st["paused"] is None and cmd != "resume":
                    return {"success": False, "error": "Not paused; nothing to step"}
                st["paused"] = None        # cleared until next Debugger.paused
                st["event"].clear()
            res = tab.run_cdp(f"Debugger.{cmd}")
            if isinstance(res, dict) and res.get("error"):
                return {"success": False, "tab": key, "action": cmd, "error": res["error"]}
            # Wait off the event loop; event-driven wakeup, not a fixed poll.
            paused = await asyncio.to_thread(_wait_for_pause_blocking, key, params.wait)
            return {
                "success": True,
                "tab": key,
                "action": cmd,
                "is_paused": paused is not None,
                "paused": paused,
            }
        return _runner

    # The four control verbs share one implementation (_step) but are
    # registered explicitly so each gets a clear name and docstring.

    @mcp.tool(name="dp_resume")
    @tool_handler
    async def dp_resume(params: StepParams) -> dict:
        """Resume execution until the next breakpoint."""
        return await _step("resume")(params)

    @mcp.tool(name="dp_step_over")
    @tool_handler
    async def dp_step_over(params: StepParams) -> dict:
        """Step over the current statement."""
        return await _step("stepOver")(params)

    @mcp.tool(name="dp_step_into")
    @tool_handler
    async def dp_step_into(params: StepParams) -> dict:
        """Step into a called function."""
        return await _step("stepInto")(params)

    @mcp.tool(name="dp_step_out")
    @tool_handler
    async def dp_step_out(params: StepParams) -> dict:
        """Step out of the current function."""
        return await _step("stepOut")(params)

    @mcp.tool()
    @tool_handler
    async def dp_eval_on_frame(params: EvalOnFrameParams) -> dict:
        """Evaluate an expression at the pause site

        Read locals / closure / signature inputs in the paused call frame. This
        is the highest-value debugger tool for reversing: inspect the exact
        values feeding a signature right before it is produced.
        """
        tab = get_tab(params.browser_id)
        key = tab_key(tab)
        if _get_paused(key) is None:
            return {"success": False, "error": "Not paused; cannot evaluate on a call frame"}

        frame_id = params.call_frame_id or _top_frame_id(key)
        if not frame_id:
            return {"success": False, "error": "No call frame available"}

        result = tab.run_cdp(
            "Debugger.evaluateOnCallFrame",
            callFrameId=frame_id,
            expression=params.expression,
            returnByValue=params.return_by_value,
            silent=True,
        )
        # silent=True means a thrown JS error is NOT a CDP error; surface it.
        if isinstance(result, dict):
            if result.get("error"):
                return {"success": False, "tab": key, "call_frame_id": frame_id, "error": result["error"]}
            if result.get("exceptionDetails"):
                return {
                    "success": False, "tab": key, "call_frame_id": frame_id,
                    "exception": result["exceptionDetails"], "result": result.get("result"),
                }
        return {"success": True, "tab": key, "call_frame_id": frame_id, "result": result}
