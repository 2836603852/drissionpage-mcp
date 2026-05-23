# -*- coding: utf-8 -*-
"""
DrissionPage MCP browser manager.
"""

import socket
import sys
import uuid
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, List, Optional

from DrissionPage import Chromium, ChromiumOptions

from .config import BrowserConfig, Config


@dataclass
class TabInfo:
    """Tracked tab metadata."""
    tab_id: str
    tab: Any
    url: str = ""
    title: str = ""


@dataclass
class BrowserSession:
    """Browser session state."""
    browser_id: str
    browser: Chromium
    debug_port: Optional[int] = None
    debugger_address: Optional[str] = None
    active_tab_id: Optional[str] = None
    tabs: Dict[str, TabInfo] = field(default_factory=dict)

    def update_tab_info(self):
        """Refresh tracked tab metadata."""
        try:
            tab_ids = [str(tid) for tid in self.browser.tab_ids]

            # Remove tabs that no longer exist.
            stale_tab_ids = [tid for tid in self.tabs.keys() if tid not in tab_ids]
            for stale in stale_tab_ids:
                self.tabs.pop(stale, None)

            # Refresh all current tabs (not only newly discovered ones).
            for tab_id in tab_ids:
                tab = self.browser.get_tab(tab_id)
                if tab_id not in self.tabs:
                    self.tabs[tab_id] = TabInfo(
                        tab_id=tab_id,
                        tab=tab,
                        url=getattr(tab, 'url', ''),
                        title=getattr(tab, 'title', '')
                    )
                else:
                    self.tabs[tab_id].tab = tab
                    self.tabs[tab_id].url = getattr(tab, 'url', '')
                    self.tabs[tab_id].title = getattr(tab, 'title', '')

            if self.active_tab_id not in self.tabs:
                self.active_tab_id = next(iter(self.tabs), None)
        except Exception as exc:
            # Best-effort refresh: never abort callers, but surface for debugging.
            try:
                print(
                    f"[BrowserSession.update_tab_info] refresh failed: {exc!r}",
                    file=sys.stderr,
                    flush=True,
                )
            except Exception:
                pass


class BrowserManager:
    """Browser instance manager (singleton)."""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.sessions: Dict[str, BrowserSession] = {}
        self.default_session_id: Optional[str] = None
        self.config: Config = Config()
        self.fixed_debug_port: Optional[int] = None

    def set_config(self, config: Config):
        """Set runtime configuration."""
        self.config = config

        configured_port = getattr(config.browser, "debug_port", None)
        if configured_port is not None:
            self._bind_debug_port(int(configured_port))

    def _pick_free_port(self) -> int:
        """Pick a currently free localhost port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return int(sock.getsockname()[1])

    def _extract_port(self, address: str) -> Optional[int]:
        """Extract port from a debugger address string."""
        try:
            return int(str(address).rsplit(":", 1)[1])
        except Exception:
            return None

    def _bind_debug_port(self, port: int) -> int:
        """Bind the manager to a single fixed debug port."""
        if port <= 0:
            raise ValueError("Debug port must be a positive integer")
        if self.fixed_debug_port is not None and self.fixed_debug_port != port:
            raise ValueError(
                f"Debug port already fixed to {self.fixed_debug_port}; refusing to switch to {port}"
            )
        if self.fixed_debug_port is None:
            self.fixed_debug_port = int(port)
        return self.fixed_debug_port

    def get_debug_port(self) -> int:
        """Get the fixed debug port, allocating it once if needed."""
        configured_port = getattr(self.config.browser, "debug_port", None)
        if configured_port is not None:
            return self._bind_debug_port(int(configured_port))
        if self.fixed_debug_port is None:
            self._bind_debug_port(self._pick_free_port())
        return self.fixed_debug_port

    def _create_options(self, browser_config: Optional[BrowserConfig] = None) -> ChromiumOptions:
        """Create Chromium options."""
        config = browser_config or self.config.browser
        options = ChromiumOptions()

        debug_port = config.debug_port or self.get_debug_port()
        options.set_local_port(debug_port)

        return options

    def _apply_alert_policy(self, browser: Chromium, browser_config: BrowserConfig) -> None:
        """Apply default JavaScript dialog handling policy."""
        try:
            if browser_config.auto_handle_alert and browser_config.auto_accept_alert:
                # Follow DrissionPage global default behavior:
                # browser.set.auto_handle_alert()
                browser.set.auto_handle_alert()
            else:
                browser.set.auto_handle_alert(
                    on_off=browser_config.auto_handle_alert,
                    accept=browser_config.auto_accept_alert,
                )
            return
        except Exception:
            pass

        # Fallback to current tab-level policy when browser-level API is unavailable.
        try:
            tab = browser.latest_tab
            if browser_config.auto_handle_alert and browser_config.auto_accept_alert:
                tab.set.auto_handle_alert()
            else:
                tab.set.auto_handle_alert(
                    on_off=browser_config.auto_handle_alert,
                    accept=browser_config.auto_accept_alert,
                )
        except Exception:
            pass

    def create_browser(
        self,
        browser_id: Optional[str] = None,
        proxy: Optional[str] = None,
        debug_port: Optional[int] = None,
    ) -> BrowserSession:
        """Create a new browser instance."""

        selected_port = self.get_debug_port() if debug_port is None else self._bind_debug_port(int(debug_port))

        browser_config = BrowserConfig(debug_port=selected_port)

        options = self._create_options(browser_config)

        if proxy:
            options.set_proxy(proxy)

        browser = Chromium(addr_or_opts=options)
        self._apply_alert_policy(browser, browser_config)

        session_id = browser_id or f"browser_{uuid.uuid4().hex[:8]}"
        session = BrowserSession(
            browser_id=session_id,
            browser=browser,
            debug_port=browser_config.debug_port,
            debugger_address=f"127.0.0.1:{browser_config.debug_port}",
        )

        # Initialize tabs.
        session.update_tab_info()
        if session.tabs:
            session.active_tab_id = list(session.tabs.keys())[0]

        self.sessions[session_id] = session

        if self.default_session_id is None:
            self.default_session_id = session_id

        return session

    def connect_browser(
        self,
        address: str,
        browser_id: Optional[str] = None
    ) -> BrowserSession:
        """Connect to an existing browser."""
        port = self._extract_port(address)
        if port is None:
            raise ValueError(f"Invalid debugger address: {address}")
        self._bind_debug_port(port)

        browser = Chromium(addr_or_opts=address)
        self._apply_alert_policy(browser, self.config.browser)

        session_id = browser_id or f"browser_{uuid.uuid4().hex[:8]}"
        session = BrowserSession(
            browser_id=session_id,
            browser=browser,
            debug_port=port,
            debugger_address=address,
        )

        # Initialize tabs.
        session.update_tab_info()
        if session.tabs:
            session.active_tab_id = list(session.tabs.keys())[0]

        self.sessions[session_id] = session

        if self.default_session_id is None:
            self.default_session_id = session_id

        return session

    def get_session(self, session_id: Optional[str] = None) -> Optional[BrowserSession]:
        """Get browser session by id (or default session)."""
        if session_id:
            return self.sessions.get(session_id)
        if self.default_session_id:
            return self.sessions.get(self.default_session_id)
        return None

    def get_active_tab(self, session_id: Optional[str] = None) -> Optional[Any]:
        """Get current active tab."""
        session = self.get_session(session_id)
        if not session:
            return None

        session.update_tab_info()

        # Prefer tracked active tab to avoid latest_tab returning mixed/proxy object types.
        if session.active_tab_id and session.active_tab_id in session.tabs:
            return session.tabs[session.active_tab_id].tab

        # Fallback to browser.latest_tab and normalize if it is a tab id string.
        try:
            latest = session.browser.latest_tab
            if isinstance(latest, str):
                tab = session.browser.get_tab(latest)
                session.active_tab_id = latest
                if latest not in session.tabs:
                    session.tabs[latest] = TabInfo(
                        tab_id=latest,
                        tab=tab,
                        url=getattr(tab, 'url', ''),
                        title=getattr(tab, 'title', '')
                    )
                return tab
            return latest
        except Exception:
            pass

        # Last fallback: first tracked tab.
        if session.tabs:
            first_tab_id = next(iter(session.tabs))
            session.active_tab_id = first_tab_id
            return session.tabs[first_tab_id].tab

        return None

    def set_active_tab(self, tab_id: str, session_id: Optional[str] = None) -> bool:
        """Set active tab id in tracked session."""
        session = self.get_session(session_id)
        if not session:
            return False

        if tab_id in session.tabs:
            session.active_tab_id = tab_id
            return True

        return False

    def close_tab(self, tab_id: str, session_id: Optional[str] = None) -> bool:
        """Close a tab."""
        session = self.get_session(session_id)
        if not session:
            return False

        if tab_id in session.tabs:
            try:
                session.tabs[tab_id].tab.close()
                del session.tabs[tab_id]
                if session.active_tab_id == tab_id:
                    session.active_tab_id = list(session.tabs.keys())[0] if session.tabs else None
                return True
            except Exception:
                return False

        return False

    def close_session(self, session_id: str) -> bool:
        """Close browser session."""
        session = self.sessions.get(session_id)
        if session:
            try:
                session.browser.quit()
            except Exception:
                pass
            del self.sessions[session_id]
            if self.default_session_id == session_id:
                self.default_session_id = next(iter(self.sessions), None)
            return True
        return False

    def close_all(self):
        """Close all browser sessions."""
        for session in list(self.sessions.values()):
            try:
                session.browser.quit()
            except Exception:
                pass
        self.sessions.clear()
        self.default_session_id = None

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all sessions and tab metadata."""
        result = []
        for session_id, session in self.sessions.items():
            session.update_tab_info()
            tabs_info = []
            for tab_id, tab_info in session.tabs.items():
                tabs_info.append({
                    "tab_id": tab_id,
                    "url": tab_info.url,
                    "title": tab_info.title,
                })

            result.append({
                "browser_id": session_id,
                "debug_port": session.debug_port,
                "debugger_address": session.debugger_address,
                "active_tab_id": session.active_tab_id,
                "tabs": tabs_info,
                "is_default": session_id == self.default_session_id,
            })

        return result


# Global browser manager singleton.
browser_manager = BrowserManager()
