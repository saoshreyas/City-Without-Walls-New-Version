"""
wsz6_play/gsl/context.py

Shared mutable context objects threaded through the GSL executor.

GSLPlayer   — one human or mock player in the current run
GSLSession  — the full execution context for one script run
GSLContext  — lightweight read-only snapshot passed to Assert_custom functions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GSLPlayer:
    """Represents one player registered during a GSL script run."""
    display_name: str        # name used in all GSL commands
    token:        str        # RoleManager token (UUID hex); '' until Create_Session
    user_id:      int | None # Django user PK; None for guests
    is_mock:      bool       # True → account will be deleted on script exit


@dataclass
class GSLSession:
    """Shared mutable context for one script execution."""
    # Populated progressively as script commands execute
    game_slug:    str  = ''
    session_key:  str  = ''
    formulation:  Any  = None   # SZ_Formulation instance
    role_manager: Any  = None   # RoleManager instance
    game_runner:  Any  = None   # GameRunner instance
    players:      dict = field(default_factory=dict)   # display_name → GSLPlayer
    rng_seed:     int | None = None   # pending seed for next Start_game
    started:      bool = False
    on_error:     str  = 'stop'   # 'stop' | 'continue' | 'log'
    error_count:  int  = 0
    active_view:  dict = field(default_factory=dict)   # token → role_num


@dataclass
class GSLContext:
    """Read-only snapshot passed to Assert_custom user functions.

    Attributes match the spec §6.3 table exactly so user check-functions
    can rely on stable field names.
    """
    state:        Any        # current game state object (game-specific)
    session:      dict       # session_store dict snapshot
    players:      dict       # display_name → GSLPlayer
    active_roles: list       # role names currently active (list[str])
    mode:         str = 'api'   # 'api' | 'browser'
