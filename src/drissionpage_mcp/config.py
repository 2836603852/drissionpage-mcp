# -*- coding: utf-8 -*-
"""
DrissionPage MCP configuration.
"""

from typing import Optional

from pydantic import BaseModel, Field


class BrowserConfig(BaseModel):
    """Browser configuration."""
    debug_port: Optional[int] = Field(
        None,
        description="Optional default debugging port for the current MCP runtime; if omitted, the first chosen port is reused within the runtime",
    )
    auto_handle_alert: bool = Field(True, description="Automatically handle JavaScript dialogs")
    auto_accept_alert: bool = Field(True, description="Accept dialogs when auto-handling is enabled")


class TimeoutConfig(BaseModel):
    """Timeout configuration."""
    base: float = Field(10.0, description="Base timeout in seconds")
    page_load: float = Field(30.0, description="Page load timeout in seconds")
    script: float = Field(30.0, description="Script execution timeout in seconds")
    element_wait: float = Field(10.0, description="Element wait timeout in seconds")
    network_wait: float = Field(10.0, description="Network wait timeout in seconds")


class ServerConfig(BaseModel):
    """MCP server configuration."""
    name: str = Field("DrissionPage MCP", description="Server name")
    version: str = Field("1.1.0", description="Server version")
    debug: bool = Field(False, description="Debug mode")


class Config(BaseModel):
    """Full configuration."""

    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    timeout: TimeoutConfig = Field(default_factory=TimeoutConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
