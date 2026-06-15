"""
wsz6_play/gsl/executor.py

Async execution engine for parsed GSL command lists.

Public entry point:
    exit_code = await execute_script(commands, mode='api', log_level='info',
                                     browser_session=None)

Returns 0 on success, 1 on any failure.

The executor:
  1. Pre-processes the flat Command list into a tree of RepeatBlock nodes.
  2. Iterates the tree, dispatching each command to its handler.
  3. Applies the current on_error policy (stop / continue / log) on failure.
  4. Purges mock accounts in a finally block regardless of outcome.

Modes:
  api     — handlers in commands.py / assertions.py; drives the game engine
            directly in-process.
  browser — handlers in browser_commands.py / browser_assertions.py; drives
            a real Playwright browser against a running Daphne server.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import List, Union

from .assertions import (
    assert_active_role,
    assert_custom,
    assert_phase,
    assert_player_count,
    assert_role_count,
    assert_state,
    assert_view_exists,
)
from .browser_assertions import (
    assert_active_role_browser,
    assert_custom_browser,
    assert_phase_browser,
    assert_player_count_browser,
    assert_role_count_browser,
    assert_state_browser,
    assert_view_exists_browser,
)
from .browser_commands import (
    handle_add_player_browser,
    handle_assign_role_browser,
    handle_create_session_browser,
    handle_login_browser,
    handle_op_browser,
    handle_select_game_browser,
    handle_set_rng_seed_browser,
    handle_start_game_browser,
    handle_view_as_browser,
)
from .commands import (
    handle_add_player,
    handle_assign_role,
    handle_create_session,
    handle_login,
    handle_op,
    handle_select_game,
    handle_set_rng_seed,
    handle_start_game,
    handle_view_as,
)
from .context import GSLSession
from .errors import GSLAssertionError, GSLError, GSLSyntaxError
from .mock_accounts import apurge_mock_users, purge_mock_users
from .parser import Command

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dispatch tables: GSL keyword (lowercase) → handler callable
# ---------------------------------------------------------------------------

API_DISPATCH = {
    # Session setup
    'login':          handle_login,
    'select_game':    handle_select_game,
    'create_session': handle_create_session,
    'add_player':     handle_add_player,
    'assign_role':    handle_assign_role,
    'set_rng_seed':   handle_set_rng_seed,
    'start_game':     handle_start_game,
    # Gameplay
    'op':             handle_op,
    'view_as':        handle_view_as,
    # Assertions
    'assert_phase':        assert_phase,
    'assert_active_role':  assert_active_role,
    'assert_state':        assert_state,
    'assert_player_count': assert_player_count,
    'assert_role_count':   assert_role_count,
    'assert_view_exists':  assert_view_exists,
    'assert_custom':       assert_custom,
    # Flow control — handled inline / by block expansion
    'on_error':    None,
    'repeat':      None,   # consumed by _expand_repeats
    'end_repeat':  None,   # consumed by _expand_repeats
    # Include is expanded at parse time; never reaches the executor
}

BROWSER_DISPATCH = {
    # Session setup
    'login':          handle_login_browser,
    'select_game':    handle_select_game_browser,
    'create_session': handle_create_session_browser,
    'add_player':     handle_add_player_browser,
    'assign_role':    handle_assign_role_browser,
    'set_rng_seed':   handle_set_rng_seed_browser,
    'start_game':     handle_start_game_browser,
    # Gameplay
    'op':             handle_op_browser,
    'view_as':        handle_view_as_browser,
    # Assertions — all async in browser mode
    'assert_phase':        assert_phase_browser,
    'assert_active_role':  assert_active_role_browser,
    'assert_state':        assert_state_browser,
    'assert_player_count': assert_player_count_browser,
    'assert_role_count':   assert_role_count_browser,
    'assert_view_exists':  assert_view_exists_browser,
    'assert_custom':       assert_custom_browser,
    # Flow control — handled inline / by block expansion
    'on_error':    None,
    'repeat':      None,
    'end_repeat':  None,
}

# Keep the old name as an alias for backwards compatibility.
DISPATCH = API_DISPATCH


# ---------------------------------------------------------------------------
# Block expansion (Repeat / End_repeat)
# ---------------------------------------------------------------------------

@dataclass
class RepeatBlock:
    """A Repeat N … End_repeat block."""
    count:    int
    commands: list   # list of Command | RepeatBlock (supports nesting)


def _expand_repeats(
    commands: List[Command],
) -> List[Union[Command, RepeatBlock]]:
    """Convert a flat list with repeat/end_repeat markers into RepeatBlock nodes.

    Supports nested Repeat blocks up to arbitrary depth.

    Raises:
        GSLSyntaxError: on mismatched Repeat/End_repeat or bad count.
    """
    stack:  list[list] = [[]]   # stack of command-lists being built
    counts: list[int]  = []     # corresponding repeat counts

    for cmd in commands:
        if cmd.keyword == 'repeat':
            if not cmd.args:
                raise GSLSyntaxError(
                    f'Line {cmd.line_no}: Repeat requires an integer argument'
                )
            try:
                n = int(cmd.args[0])
            except ValueError:
                raise GSLSyntaxError(
                    f'Line {cmd.line_no}: Repeat count must be an integer, '
                    f'got "{cmd.args[0]}"'
                )
            counts.append(n)
            stack.append([])

        elif cmd.keyword == 'end_repeat':
            if len(stack) < 2:
                raise GSLSyntaxError(
                    f'Line {cmd.line_no}: End_repeat without a matching Repeat'
                )
            block_cmds = stack.pop()
            n          = counts.pop()
            stack[-1].append(RepeatBlock(count=n, commands=block_cmds))

        else:
            stack[-1].append(cmd)

    if len(stack) > 1:
        raise GSLSyntaxError(
            f'Unclosed Repeat block — missing End_repeat '
            f'(depth {len(stack) - 1})'
        )

    return stack[0]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def execute_script(
    commands: List[Command],
    mode: str = 'api',
    log_level: str = 'info',
    browser_session=None,
    defer_mock_cleanup: bool = False,
) -> int:
    """Execute a parsed GSL script and return an exit code.

    Args:
        commands:            Parsed Command list from parse_file().
        mode:                'api' or 'browser'.
        log_level:           Logging verbosity (unused here; configured by caller).
        browser_session:     A pre-constructed BrowserSession instance (browser
                             mode only).  If None in browser mode, a default
                             BrowserSession is created.
        defer_mock_cleanup:  If True, skip purging mock accounts in the finally
                             block.  The caller is responsible for calling
                             purge_mock_users() later (used by --stay-open so
                             mock accounts remain valid while the browser is open).

    Returns:
        0 — all commands and assertions passed
        1 — one or more failures (see log for details)
    """
    if mode == 'browser':
        from .browser_session import BrowserSession
        session  = browser_session if browser_session is not None else BrowserSession()
        dispatch = BROWSER_DISPATCH
    else:
        session  = GSLSession()
        dispatch = API_DISPATCH

    try:
        expanded = _expand_repeats(commands)
        await _run_block(expanded, session, dispatch)

        if session.error_count > 0:
            logger.error(
                '[GSL] Script finished with %d error(s).',
                session.error_count,
            )
            return 1

        logger.info('[GSL] Script completed successfully — all assertions passed.')
        return 0

    except GSLError as exc:
        logger.error('[GSL FATAL] %s: %s', type(exc).__name__, exc)
        return 1
    except Exception as exc:
        logger.exception('[GSL FATAL] Unexpected exception: %s', exc)
        return 1
    finally:
        # Clean up mock users unless the caller asked us to defer (--stay-open).
        if not defer_mock_cleanup:
            await apurge_mock_users()
        # In api mode, remove the local session_store entry.
        # In browser mode, the server manages its own session_store —
        # do NOT call session_store.delete_session from this process.
        if mode == 'api' and session.session_key:
            from wsz6_play import session_store
            session_store.delete_session(session.session_key)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _run_block(
    items: List[Union[Command, RepeatBlock]],
    session: GSLSession,
    dispatch: dict,
) -> None:
    """Recursively execute a list of Commands and RepeatBlocks."""
    for item in items:
        if isinstance(item, RepeatBlock):
            for _ in range(item.count):
                await _run_block(item.commands, session, dispatch)
        else:
            await _dispatch_cmd(item, session, dispatch)


async def _dispatch_cmd(cmd: Command, session: GSLSession,
                        dispatch: dict) -> None:
    """Dispatch one command, honouring the current on_error policy."""
    try:
        await _execute_one(cmd, session, dispatch)
    except GSLError as exc:
        _apply_error_policy(cmd, exc, session)


def _apply_error_policy(
    cmd: Command,
    exc: GSLError,
    session: GSLSession,
) -> None:
    """Apply session.on_error to a caught GSLError."""
    msg = f'[GSL line {cmd.line_no}] {type(exc).__name__}: {exc}'
    policy = session.on_error

    if policy == 'stop':
        raise exc   # propagates up to execute_script → exit 1

    elif policy == 'continue':
        logger.error(msg)
        session.error_count += 1

    elif policy == 'log':
        logger.warning(msg + '  (on_error log — not counted toward exit code)')

    else:
        raise exc   # defensive fallback


async def _execute_one(cmd: Command, session: GSLSession,
                       dispatch: dict) -> None:
    """Execute a single command."""
    logger.info(
        '[GSL line %d] %s%s',
        cmd.line_no,
        cmd.keyword,
        (' ' + ' '.join(cmd.args)) if cmd.args else '',
    )

    # --- Inline flow-control: On_error ---
    if cmd.keyword == 'on_error':
        if not cmd.args or cmd.args[0].lower() not in ('stop', 'continue', 'log'):
            raise GSLSyntaxError(
                f'Line {cmd.line_no}: On_error requires stop, continue, or log'
            )
        session.on_error = cmd.args[0].lower()
        return

    # --- All other keywords ---
    handler = dispatch.get(cmd.keyword)
    if handler is None:
        if cmd.keyword in ('repeat', 'end_repeat'):
            # Should have been consumed by _expand_repeats; this is a bug
            raise GSLSyntaxError(
                f'Line {cmd.line_no}: Unexpected "{cmd.keyword}" — '
                'this is an executor bug, please report it'
            )
        raise GSLSyntaxError(
            f'Line {cmd.line_no}: Unknown command "{cmd.keyword}"'
        )

    # Dispatch — support both async (commands) and sync (api assertions) handlers
    if inspect.iscoroutinefunction(handler):
        await handler(cmd.args, session)
    else:
        handler(cmd.args, session)
