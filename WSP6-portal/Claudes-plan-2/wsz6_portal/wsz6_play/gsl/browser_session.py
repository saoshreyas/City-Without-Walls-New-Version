"""
wsz6_play/gsl/browser_session.py

Dataclasses used exclusively by GSL browser-mode execution.

BrowserPlayerCtx  — one player's Playwright BrowserContext + Page
BrowserSession    — extends GSLSession with Playwright handles and
                    a registry of BrowserPlayerCtx objects.

Playwright is imported only under TYPE_CHECKING so this module can be
safely imported by the production server without requiring playwright
to be installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from .context import GSLSession

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page


@dataclass
class BrowserPlayerCtx:
    """Playwright state for one player in a browser-mode GSL run."""
    display_name:  str
    username:      str                   # Django username (for login form)
    raw_password:  str                   # plaintext password (for login form)
    browser_ctx:   Any = None            # playwright.async_api.BrowserContext
    page:          Any = None            # playwright.async_api.Page
    role_token:    str | None = None     # set after Start_game navigation
    game_page_url: str | None = None


@dataclass
class BrowserSession(GSLSession):
    """GSL execution context for browser mode.

    Extends GSLSession so all api-mode context fields (game_slug,
    session_key, role_manager, etc.) remain available for assertions
    and hybrid commands.
    """
    playwright_instance: Any  = None            # Playwright handle
    browser:             Any  = None            # Browser (Chromium)
    browser_players:     dict = field(default_factory=dict)
    # display_name → BrowserPlayerCtx
    base_url:            str  = 'http://127.0.0.1:8000'
    default_timeout:     int  = 30_000          # ms; override with --gsl-timeout
