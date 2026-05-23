# -*- coding: utf-8 -*-
"""
DrissionPage MCP Element Operations Tools
"""

import re
import time
from html import unescape
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field

from ..exceptions import ElementNotFoundError
from ._common import get_tab, tool_handler

# ============ Parameter Models ============

class FindElementParams(BaseModel):
    """Find element parameters"""
    locator: str = Field(..., description="Element locator, e.g. #id, .class, text:button, xpath://div")
    timeout: float = Field(10.0, description="Wait timeout in seconds")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class FindElementsParams(BaseModel):
    """Find multiple elements parameters"""
    locator: str = Field(..., description="Element locator")
    timeout: float = Field(10.0, description="Wait timeout in seconds")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class ClickParams(BaseModel):
    """Click parameters"""
    locator: str = Field(..., description="Element locator")
    button: Literal["left", "right", "middle"] = Field("left", description="Mouse button")
    click_count: int = Field(1, description="Click count (2 for double click)")
    timeout: float = Field(10.0, description="Wait timeout in seconds")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class FillParams(BaseModel):
    """Fill parameters"""
    locator: str = Field(..., description="Element locator")
    value: str = Field(..., description="Value to fill")
    clear_first: bool = Field(True, description="Clear before filling")
    timeout: float = Field(10.0, description="Wait timeout in seconds")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class SelectParams(BaseModel):
    """Select parameters"""
    locator: str = Field(..., description="Select element locator")
    value: str = Field(..., description="Value or text to select")
    by: Literal["value", "text", "index"] = Field("text", description="Selection method")
    timeout: float = Field(10.0, description="Wait timeout in seconds")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class ClickToUploadParams(BaseModel):
    """Click upload element with file paths parameters."""
    locator: str = Field(..., description="Upload trigger element locator")
    file_paths: Union[str, List[str]] = Field(..., description="File path or path list")
    by_js: bool = Field(False, description="Whether to click by JavaScript")
    timeout: float = Field(10.0, description="Element lookup timeout in seconds")
    wait_timeout: Optional[float] = Field(10.0, description="Optional wait timeout for upload paths inputted")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class GetTextParams(BaseModel):
    """Get text parameters"""
    locator: str = Field(..., description="Element locator")
    timeout: float = Field(10.0, description="Wait timeout in seconds")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


class GetPageContentParams(BaseModel):
    """Get page content parameters"""
    mode: Literal["html", "text"] = Field("html", description="Return raw HTML or visible text")
    max_length: int = Field(50000, description="Maximum characters to return; content beyond this is truncated")
    browser_id: Optional[str] = Field(None, description="Browser instance ID")


# ============ Helper Functions ============

def _find_element(tab, locator: str, timeout: float = 10.0):
    """Find element or raise ElementNotFoundError."""
    ele = tab.ele(locator, timeout=timeout)
    if not ele:
        raise ElementNotFoundError(locator, timeout)
    return ele


def _normalize_file_paths(file_paths: Union[str, List[str]]) -> List[str]:
    """Normalize file path arguments to non-empty string list."""
    if isinstance(file_paths, str):
        values = [file_paths]
    else:
        values = [str(path) for path in file_paths]
    return [item for item in values if item and item.strip()]


def _truncate(text: str, limit: int) -> tuple:
    """Return (text, truncated_flag, total_length)."""
    if text is None:
        return "", False, 0
    total = len(text)
    if total <= limit:
        return text, False, total
    return text[:limit], True, total


# ============ Tool Functions ============

def register_element_operations_tools(mcp):
    """Register element operation tools"""

    @mcp.tool()
    @tool_handler
    async def dp_find_element(params: FindElementParams) -> dict:
        """Find a single element

        Find an element on the page using a locator.
        Supports multiple locator syntaxes: #id, .class, text:button, xpath://, tag:tagname, @attr=value
        """
        tab = get_tab(params.browser_id)
        try:
            ele = _find_element(tab, params.locator, params.timeout)
        except ElementNotFoundError as exc:
            return {
                "success": True,
                "found": False,
                "error": str(exc),
            }

        return {
            "success": True,
            "found": True,
            "tag": ele.tag,
            "text": ele.text[:200] if ele.text else None,
            "attrs": {
                "id": ele.attr("id"),
                "class": ele.attr("class"),
                "name": ele.attr("name"),
                "href": ele.attr("href"),
                "src": ele.attr("src"),
            },
        }

    @mcp.tool()
    @tool_handler
    async def dp_find_elements(params: FindElementsParams) -> dict:
        """Find multiple elements

        Find all matching elements on the page using a locator.
        """
        tab = get_tab(params.browser_id)
        eles = tab.eles(params.locator, timeout=params.timeout)

        elements = []
        for i, ele in enumerate(eles[:50]):
            elements.append({
                "index": i,
                "tag": ele.tag,
                "text": ele.text[:100] if ele.text else None,
            })

        return {
            "success": True,
            "count": len(eles),
            "elements": elements,
        }

    @mcp.tool()
    @tool_handler
    async def dp_click(params: ClickParams) -> dict:
        """Click an element"""
        tab = get_tab(params.browser_id)
        ele = _find_element(tab, params.locator, params.timeout)

        if params.click_count == 2:
            ele.click.multi()
        elif params.button == "right":
            ele.click.right()
        elif params.button == "middle":
            ele.click.middle()
        else:
            ele.click()

        return {
            "success": True,
            "locator": params.locator,
        }

    @mcp.tool()
    @tool_handler
    async def dp_fill(params: FillParams) -> dict:
        """Fill an input field"""
        tab = get_tab(params.browser_id)
        ele = _find_element(tab, params.locator, params.timeout)

        if params.clear_first:
            ele.clear()
        ele.input(params.value)

        return {
            "success": True,
            "locator": params.locator,
            "value": params.value,
        }

    @mcp.tool()
    @tool_handler
    async def dp_select(params: SelectParams) -> dict:
        """Select from dropdown"""
        tab = get_tab(params.browser_id)
        ele = _find_element(tab, params.locator, params.timeout)

        if params.by == "value":
            ele.select.by_value(params.value, timeout=params.timeout)
        elif params.by == "index":
            ele.select.by_index(int(params.value), timeout=params.timeout)
        else:
            ele.select.by_text(params.value, timeout=params.timeout)

        return {
            "success": True,
            "locator": params.locator,
            "value": params.value,
        }

    @mcp.tool()
    @tool_handler
    async def dp_click_to_upload(params: ClickToUploadParams) -> dict:
        """Click upload trigger element and set file paths in one step."""
        tab = get_tab(params.browser_id)
        paths = _normalize_file_paths(params.file_paths)
        if not paths:
            return {
                "success": False,
                "error": "file_paths cannot be empty",
            }

        ele = _find_element(tab, params.locator, params.timeout)
        click_to_upload = getattr(getattr(ele, "click", None), "to_upload", None)
        if not callable(click_to_upload):
            return {
                "success": False,
                "error": "Target element does not support click.to_upload()",
            }

        click_to_upload(paths if len(paths) > 1 else paths[0], by_js=params.by_js)

        waited = None
        if params.wait_timeout is not None:
            waiter = getattr(getattr(tab, "wait", None), "upload_paths_inputted", None)
            if callable(waiter):
                upload_list = getattr(tab, "_upload_list", None)
                if upload_list is None:
                    waited = bool(waiter())
                else:
                    deadline = time.perf_counter() + max(0.0, float(params.wait_timeout))
                    waited = False
                    while time.perf_counter() < deadline:
                        if not getattr(tab, "_upload_list", None):
                            waited = True
                            break
                        time.sleep(0.01)

        return {
            "success": True,
            "locator": params.locator,
            "count": len(paths),
            "file_paths": paths,
            "by_js": params.by_js,
            "upload_paths_inputted": waited,
        }

    @mcp.tool()
    @tool_handler
    async def dp_get_text(params: GetTextParams) -> dict:
        """Get the text content of an element."""
        tab = get_tab(params.browser_id)
        ele = _find_element(tab, params.locator, params.timeout)
        return {
            "success": True,
            "text": ele.text,
        }

    @mcp.tool()
    @tool_handler
    async def dp_get_page_content(params: GetPageContentParams = None) -> dict:
        """Get current page content as raw HTML or visible text.

        - ``mode="html"`` returns ``tab.html``.
        - ``mode="text"`` returns ``document.body.innerText`` (falls back to HTML tag stripping).
        """
        if params is None:
            params = GetPageContentParams()

        tab = get_tab(params.browser_id)

        if params.mode == "html":
            content = getattr(tab, "html", "") or ""
        else:
            content = ""
            if hasattr(tab, "run_js"):
                try:
                    js_text = tab.run_js("return document.body ? document.body.innerText : ''")
                    if isinstance(js_text, str):
                        content = js_text
                except Exception:
                    pass
            if not content:
                html = getattr(tab, "html", "") or ""
                stripped = re.sub(r"<[^>]+>", " ", html)
                content = re.sub(r"\s+", " ", unescape(stripped)).strip()

        out, truncated, total = _truncate(content, params.max_length)
        return {
            "success": True,
            "mode": params.mode,
            "content": out,
            "url": getattr(tab, "url", ""),
            "truncated": truncated,
            "total_length": total,
        }
