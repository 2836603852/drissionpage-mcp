# -*- coding: utf-8 -*-
"""
DrissionPage MCP tools package.
"""

from .actions import register_actions_tools
from .debugger import register_debugger_tools
from .element_operations import register_element_operations_tools
from .javascript import register_javascript_tools
from .network import register_network_tools
from .page_management import register_page_management_tools
from .screenshot import register_screenshot_tools
from .websocket import register_websocket_tools

__all__ = [
    "register_page_management_tools",
    "register_element_operations_tools",
    "register_javascript_tools",
    "register_network_tools",
    "register_screenshot_tools",
    "register_actions_tools",
    "register_websocket_tools",
    "register_debugger_tools",
]
