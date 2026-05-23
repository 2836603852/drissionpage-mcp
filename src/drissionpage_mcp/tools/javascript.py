# -*- coding: utf-8 -*-
"""
DrissionPage MCP JavaScript tools.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from ._common import get_tab, tool_handler


# ============ Parameter Models ============

class RunJsParams(BaseModel):
    """Run JavaScript parameters."""
    script: str = Field(..., description="JavaScript code")
    timeout: float = Field(30.0, description="Execution timeout in seconds")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class RunJsOnEleParams(BaseModel):
    """Run JavaScript on element parameters."""
    locator: str = Field(..., description="Element locator")
    script: str = Field(..., description="JavaScript code (use `this` as current element)")
    timeout: float = Field(10.0, description="Element lookup timeout in seconds")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class RunCdpParams(BaseModel):
    """Run CDP command parameters."""
    cmd: str = Field(..., description="CDP command name, e.g. Runtime.evaluate")
    cmd_args: Optional[Dict[str, Any]] = Field(None, description="CDP command argument map")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


# ============ Helper Functions ============

def _result_value(result: Any):
    """Convert runtime value to JSON-serializable payload when possible."""
    if result is None:
        return None
    if isinstance(result, (str, int, float, bool, list, dict)):
        return result
    return str(result)


def register_javascript_tools(mcp):
    """Register JavaScript tools."""

    @mcp.tool()
    @tool_handler
    async def dp_run_js(params: RunJsParams) -> dict:
        """Run JavaScript

        Execute JavaScript in page context.
        """
        tab = get_tab(params.browser_id)
        result = tab.run_js(params.script, timeout=params.timeout)
        return {
            "success": True,
            "result": _result_value(result),
        }

    @mcp.tool()
    @tool_handler
    async def dp_run_js_on_ele(params: RunJsOnEleParams) -> dict:
        """Run JavaScript on an element

        Execute JavaScript on a specific element where `this` references that element.
        """
        tab = get_tab(params.browser_id)
        ele = tab.ele(params.locator, timeout=params.timeout)
        if not ele:
            return {
                "success": False,
                "error": f"Element not found: {params.locator}",
            }

        result = ele.run_js(params.script)
        return {
            "success": True,
            "result": _result_value(result),
            "locator": params.locator,
        }

    @mcp.tool()
    @tool_handler
    async def dp_run_cdp(params: RunCdpParams) -> dict:
        """Run CDP command

        Execute a CDP command in current page context.
        """
        tab = get_tab(params.browser_id)
        kwargs = params.cmd_args or {}
        result = tab.run_cdp(params.cmd, **kwargs) if kwargs else tab.run_cdp(params.cmd)
        return {
            "success": True,
            "cmd": params.cmd,
            "result": _result_value(result),
        }
