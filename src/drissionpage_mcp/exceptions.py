# -*- coding: utf-8 -*-
"""
DrissionPage MCP exception definitions.

Only exceptions that are actually raised by the codebase are defined here.
The shared ``tool_handler`` decorator surfaces ``DrissionPageMcpError`` via
``to_dict()`` so subclasses get structured error payloads for free.
"""

from typing import Any, Optional


class DrissionPageMcpError(Exception):
    """Base exception for DrissionPage MCP."""

    def __init__(self, message: str, details: Optional[Any] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {
            "success": False,
            "error": True,
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }


class BrowserNotConnectedError(DrissionPageMcpError):
    """No browser session is currently connected."""


class ElementNotFoundError(DrissionPageMcpError):
    """Element could not be located within timeout."""

    def __init__(self, locator: str, timeout: float):
        super().__init__(
            message=f"Element not found: {locator} (timeout: {timeout}s)",
            details={"locator": locator, "timeout": timeout},
        )


class NetworkTimeoutError(DrissionPageMcpError):
    """Listener did not capture any matching packet within timeout."""
