# -*- coding: utf-8 -*-
"""
DrissionPage MCP screenshot and snapshot tools.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from ._common import get_tab, tool_handler

# ============ Parameter Models ============

class ScreenshotParams(BaseModel):
    """Screenshot parameters."""
    locator: Optional[str] = Field(None, description="Element locator; if omitted, capture current viewport")
    full_page: bool = Field(False, description="Capture full page (ignored when locator is set)")
    format: Literal["png", "jpeg", "webp"] = Field("png", description="Image format")
    save_path: Optional[str] = Field(
        None,
        description="Output path; if omitted, return base64 data URL only without writing to disk",
    )
    timeout: float = Field(10.0, description="Element lookup timeout when locator is set")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class GetPageSnapshotParams(BaseModel):
    """Page snapshot parameters."""
    max_depth: int = Field(10, description="Maximum DOM tree depth to walk")
    text_limit: int = Field(100, description="Maximum text length per node")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


def register_screenshot_tools(mcp):
    """Register screenshot and snapshot tools."""

    @mcp.tool()
    @tool_handler
    async def dp_screenshot(params: ScreenshotParams = None) -> dict:
        """Take screenshot

        Capture a screenshot of page or element.

        - If ``save_path`` is provided, the image is written to disk and the path is returned.
        - Otherwise the image is returned as a base64 data URL without touching disk
          (uses DrissionPage's ``as_base64`` argument directly).
        """
        if params is None:
            params = ScreenshotParams()

        tab = get_tab(params.browser_id)

        if params.locator:
            ele = tab.ele(params.locator, timeout=params.timeout)
            if not ele:
                return {
                    "success": False,
                    "error": f"Element not found: {params.locator}",
                }
            target = ele
        else:
            target = tab

        if params.save_path:
            if params.locator or not params.full_page:
                saved = target.get_screenshot(path=params.save_path)
            else:
                saved = target.get_screenshot(path=params.save_path, full_page=True)
            return {
                "success": True,
                "format": params.format,
                "path": str(saved) if saved else params.save_path,
            }

        if params.locator:
            b64 = target.get_screenshot(as_base64=params.format)
        else:
            b64 = target.get_screenshot(as_base64=params.format, full_page=params.full_page)

        return {
            "success": True,
            "format": params.format,
            "base64": b64,
            "data_url": f"data:image/{params.format};base64,{b64}",
        }

    @mcp.tool()
    @tool_handler
    async def dp_take_snapshot(params: GetPageSnapshotParams = None) -> dict:
        """Take page snapshot

        Capture a structured DOM snapshot for AI consumption: a nested tree of
        ``{tag, text, attrs, children}`` rooted at ``document.body``.
        """
        if params is None:
            params = GetPageSnapshotParams()

        tab = get_tab(params.browser_id)
        url = getattr(tab, "url", "")
        title = getattr(tab, "title", "")

        snapshot_data = tab.run_js(
            """
            const MAX_DEPTH = arguments[0];
            const TEXT_LIMIT = arguments[1];

            function getSnapshot(element, depth) {
                if (depth > MAX_DEPTH) return null;

                const result = {
                    tag: element.tagName ? element.tagName.toLowerCase() : '',
                    text: '',
                    attrs: {},
                    children: []
                };

                if (element.id) result.attrs.id = element.id;
                if (element.className && typeof element.className === 'string') {
                    result.attrs.class = element.className;
                }
                if (element.name) result.attrs.name = element.name;
                if (element.href) result.attrs.href = element.href;
                if (element.src) result.attrs.src = element.src;
                if (element.type) result.attrs.type = element.type;
                if (element.placeholder) result.attrs.placeholder = element.placeholder;
                if (element.value) result.attrs.value = element.value;
                const aria = element.getAttribute && element.getAttribute('aria-label');
                if (aria) result.attrs['aria-label'] = aria;

                if (element.innerText) {
                    result.text = element.innerText.substring(0, TEXT_LIMIT);
                }

                for (const child of element.children) {
                    const childSnapshot = getSnapshot(child, depth + 1);
                    if (childSnapshot && childSnapshot.tag) {
                        result.children.push(childSnapshot);
                    }
                }

                return result;
            }

            return document.body ? getSnapshot(document.body, 0) : null;
            """,
            params.max_depth,
            params.text_limit,
        )

        return {
            "success": True,
            "url": url,
            "title": title,
            "snapshot": snapshot_data,
        }
