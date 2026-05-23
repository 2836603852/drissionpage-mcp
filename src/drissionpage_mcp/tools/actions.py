# -*- coding: utf-8 -*-
"""
DrissionPage MCP actions and dialog tools.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from ._common import get_tab, tool_handler

# ============ Parameter Models ============

class ScrollParams(BaseModel):
    """Scroll parameters."""
    direction: Literal["up", "down", "left", "right", "top", "bottom"] = Field(
        ..., description="Scroll direction"
    )
    distance: int = Field(300, description="Scroll distance in pixels (ignored for top/bottom)")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class HandleAlertParams(BaseModel):
    """Alert handling parameters."""
    action: Literal["accept", "dismiss"] = Field("accept", description="Accept or dismiss dialog")
    prompt_text: Optional[str] = Field(None, description="Input text for prompt dialogs")
    timeout: float = Field(2.0, description="Wait timeout for dialog in seconds")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


def register_actions_tools(mcp):
    """Register actions and dialog tools."""

    @mcp.tool()
    @tool_handler
    async def dp_scroll(params: ScrollParams) -> dict:
        """Scroll page

        Scroll in the specified direction on the current page.
        """
        tab = get_tab(params.browser_id)

        if params.direction == "up":
            tab.scroll.up(params.distance)
        elif params.direction == "down":
            tab.scroll.down(params.distance)
        elif params.direction == "left":
            tab.scroll.left(params.distance)
        elif params.direction == "right":
            tab.scroll.right(params.distance)
        elif params.direction == "top":
            tab.scroll.to_top()
        elif params.direction == "bottom":
            tab.scroll.to_bottom()

        return {
            "success": True,
            "direction": params.direction,
            "distance": params.distance if params.direction not in ("top", "bottom") else None,
        }

    @mcp.tool()
    @tool_handler
    async def dp_handle_alert(params: HandleAlertParams = None) -> dict:
        """Handle browser dialog

        Accept or dismiss alert/confirm/prompt dialogs.
        """
        if params is None:
            params = HandleAlertParams()

        tab = get_tab(params.browser_id)

        if params.action == "accept":
            tab.handle_alert(
                accept=True,
                next_one=True,
                send=params.prompt_text,
                timeout=params.timeout,
            )
        else:
            tab.handle_alert(accept=False, next_one=True, timeout=params.timeout)

        return {
            "success": True,
            "action": params.action,
        }
