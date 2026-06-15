"""
wsz6_play/gsl/assertions.py

Synchronous handler functions for every GSL Assert_* command.

Each handler signature:
    def assert_<keyword>(args: list[str], session: GSLSession) -> None

Return None to pass.  Raise GSLAssertionError to fail.

Assertion handlers are synchronous — they only read session state and
runner.current_state; they never call coroutines.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path

from .context import GSLContext, GSLSession
from .errors import GSLAssertionError, GSLSyntaxError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _coerce_expected(s: str):
    """Coerce an expected-value string from the GSL script to a Python value.

    Tries int → float → None (for the literal 'none') → str.
    """
    if s.lower() == 'none':
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _resolve_key(state, key: str):
    """Walk a dot-notation key into a game state object.

    Supports:
      - Attribute access:  ``winner``, ``suggestion_phase``
      - List indexing:     ``active_roles.0``, ``board.0.0``
      - Length shorthand:  ``active_roles.length``

    Raises GSLAssertionError with a descriptive message on any failure.
    """
    parts = key.split('.')
    obj = state
    for part in parts:
        if part == 'length':
            try:
                obj = len(obj)
            except TypeError as exc:
                raise GSLAssertionError(
                    f'Assert_state: ".length" applied to non-sequence '
                    f'at key "{key}": {type(obj).__name__}'
                ) from exc
        elif isinstance(obj, (list, tuple)):
            try:
                obj = obj[int(part)]
            except (IndexError, ValueError) as exc:
                raise GSLAssertionError(
                    f'Assert_state: index "{part}" out of range for key "{key}"'
                ) from exc
        else:
            try:
                obj = getattr(obj, part)
            except AttributeError as exc:
                raise GSLAssertionError(
                    f'Assert_state: attribute "{part}" not found in '
                    f'{type(obj).__name__} (full key: "{key}")'
                ) from exc
    return obj


# Map GSL phase names ↔ session_store status strings
_PHASE_TO_STATUS = {
    'lobby':   'lobby',
    'playing': 'in_progress',
    'ended':   'ended',
}
_STATUS_TO_PHASE = {v: k for k, v in _PHASE_TO_STATUS.items()}


# ---------------------------------------------------------------------------
# Assertion handlers
# ---------------------------------------------------------------------------

def assert_phase(args: list[str], session: GSLSession) -> None:
    """Assert_phase <lobby|playing|ended>"""
    if len(args) != 1:
        raise GSLSyntaxError('Assert_phase requires exactly one argument')

    expected_phase = args[0].lower()
    if expected_phase not in _PHASE_TO_STATUS:
        raise GSLSyntaxError(
            f'Assert_phase: unknown phase "{expected_phase}". '
            'Valid values: lobby, playing, ended'
        )

    from wsz6_play import session_store
    sess = session_store.get_session(session.session_key)
    if sess is None:
        raise GSLAssertionError(
            'Assert_phase: session not found in session_store '
            '(was Create_Session called?)'
        )

    actual_status  = sess.get('status', '?')
    expected_status = _PHASE_TO_STATUS[expected_phase]

    if actual_status != expected_status:
        actual_phase = _STATUS_TO_PHASE.get(actual_status, actual_status)
        raise GSLAssertionError(
            f'Assert_phase failed: expected "{expected_phase}", '
            f'got "{actual_phase}" (status="{actual_status}")'
        )


def assert_active_role(args: list[str], session: GSLSession) -> None:
    """Assert_active_role <role_name>"""
    if len(args) != 1:
        raise GSLSyntaxError('Assert_active_role requires exactly one argument')
    if not session.started:
        raise GSLAssertionError('Assert_active_role: game has not started')

    expected = args[0]
    runner   = session.game_runner
    state    = runner.current_state

    # GameRunner uses current_role_num; fall back to whose_turn for games
    # that use the latter name (e.g. OCCLUEdo keeps them in sync).
    current_role_num = getattr(state, 'current_role_num',
                               getattr(state, 'whose_turn', 0))

    roles = session.role_manager.roles_spec.roles
    if not (0 <= current_role_num < len(roles)):
        raise GSLAssertionError(
            f'Assert_active_role: current_role_num {current_role_num} '
            f'is out of range (0–{len(roles) - 1})'
        )

    actual = roles[current_role_num].name
    if actual != expected:
        raise GSLAssertionError(
            f'Assert_active_role failed: expected "{expected}", got "{actual}"'
        )


def assert_state(args: list[str], session: GSLSession) -> None:
    """Assert_state <key> <expected_value>"""
    if len(args) != 2:
        raise GSLSyntaxError(
            'Assert_state requires exactly two arguments: <key> <expected_value>'
        )
    if not session.started:
        raise GSLAssertionError('Assert_state: game has not started')

    key, expected_raw = args
    state    = session.game_runner.current_state
    actual   = _resolve_key(state, key)
    expected = _coerce_expected(expected_raw)

    if actual != expected:
        raise GSLAssertionError(
            f'Assert_state failed: {key} = {actual!r} (expected {expected!r})'
        )


def assert_player_count(args: list[str], session: GSLSession) -> None:
    """Assert_player_count <n>"""
    if len(args) != 1:
        raise GSLSyntaxError('Assert_player_count requires exactly one argument')
    if session.role_manager is None:
        raise GSLAssertionError(
            'Assert_player_count: no session created yet '
            '(was Create_Session called?)'
        )

    try:
        expected = int(args[0])
    except ValueError:
        raise GSLSyntaxError(
            f'Assert_player_count: expected an integer, got "{args[0]}"'
        )

    actual = len(session.players)
    if actual != expected:
        raise GSLAssertionError(
            f'Assert_player_count failed: expected {expected}, got {actual}'
        )


def assert_role_count(args: list[str], session: GSLSession) -> None:
    """Assert_role_count <n>

    Checks len(state.active_roles) — a shorthand for
    Assert_state active_roles.length <n>.
    """
    if len(args) != 1:
        raise GSLSyntaxError('Assert_role_count requires exactly one argument')
    if not session.started:
        raise GSLAssertionError('Assert_role_count: game has not started')

    try:
        expected = int(args[0])
    except ValueError:
        raise GSLSyntaxError(
            f'Assert_role_count: expected an integer, got "{args[0]}"'
        )

    state  = session.game_runner.current_state
    actual = len(state.active_roles)

    if actual != expected:
        raise GSLAssertionError(
            f'Assert_role_count failed: expected {expected}, '
            f'got {actual} (active_roles={state.active_roles!r})'
        )


def assert_view_exists(args: list[str], session: GSLSession) -> None:
    """Assert_view_exists <user> <role>

    API-mode check: verifies that <user> holds <role> AND that <role>
    appears in state.active_roles.
    """
    if len(args) != 2:
        raise GSLSyntaxError('Assert_view_exists requires <user> <role>')
    if not session.started:
        raise GSLAssertionError('Assert_view_exists: game has not started')

    display, role_name = args

    player = session.players.get(display)
    if player is None:
        raise GSLAssertionError(
            f'Assert_view_exists: player "{display}" not found '
            f'(known: {list(session.players)})'
        )

    rm    = session.role_manager
    state = session.game_runner.current_state
    roles = rm.roles_spec.roles

    # Resolve role name → index
    role_num = None
    for i, r in enumerate(roles):
        if r.name == role_name:
            role_num = i
            break

    if role_num is None:
        available = ', '.join(f'"{r.name}"' for r in roles)
        raise GSLAssertionError(
            f'Assert_view_exists: role "{role_name}" not found '
            f'in game roles. Available: {available}'
        )

    if not rm.player_has_role(player.token, role_num):
        raise GSLAssertionError(
            f'Assert_view_exists failed: player "{display}" does not hold '
            f'role "{role_name}"'
        )

    if role_num not in state.active_roles:
        raise GSLAssertionError(
            f'Assert_view_exists failed: role "{role_name}" (index {role_num}) '
            f'is not in state.active_roles {state.active_roles!r}'
        )


def assert_custom(args: list[str], session: GSLSession) -> None:
    """Assert_custom <module_or_file> <function> [arg1 [arg2 …]]"""
    if len(args) < 2:
        raise GSLSyntaxError(
            'Assert_custom requires at least <module_or_file> <function>'
        )
    if not session.started:
        raise GSLAssertionError('Assert_custom: game has not started')

    module_or_file = args[0]
    function_name  = args[1]
    extra_raw      = args[2:]

    # Load the module
    if module_or_file.endswith('.py'):
        path = Path(module_or_file)
        if not path.is_absolute():
            path = Path.cwd() / path
        spec = importlib.util.spec_from_file_location('_gsl_check', str(path))
        if spec is None:
            raise GSLAssertionError(
                f'Assert_custom: cannot create module spec from "{module_or_file}"'
            )
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as exc:
            raise GSLAssertionError(
                f'Assert_custom: error loading "{module_or_file}": {exc}'
            ) from exc
    else:
        try:
            mod = importlib.import_module(module_or_file)
        except ImportError as exc:
            raise GSLAssertionError(
                f'Assert_custom: cannot import module "{module_or_file}": {exc}'
            ) from exc

    fn = getattr(mod, function_name, None)
    if fn is None:
        raise GSLAssertionError(
            f'Assert_custom: function "{function_name}" not found '
            f'in "{module_or_file}"'
        )
    if not callable(fn):
        raise GSLAssertionError(
            f'Assert_custom: "{function_name}" in "{module_or_file}" '
            'is not callable'
        )

    # Build read-only context
    runner = session.game_runner
    state  = runner.current_state
    roles  = session.role_manager.roles_spec.roles
    active_role_names = [
        roles[rn].name
        for rn in getattr(state, 'active_roles', [])
        if 0 <= rn < len(roles)
    ]

    from wsz6_play import session_store as ss
    sess_dict = ss.get_session(session.session_key) or {}

    ctx = GSLContext(
        state=state,
        session=sess_dict,
        players=session.players,
        active_roles=active_role_names,
        mode='api',
    )

    # Coerce extra args
    def _coerce(s: str):
        try:
            return int(s)
        except ValueError:
            pass
        try:
            return float(s)
        except ValueError:
            pass
        return s

    extra = [_coerce(a) for a in extra_raw]

    # Invoke
    try:
        result = fn(ctx, *extra)
    except AssertionError as exc:
        msg = str(exc) or f'Assert_custom "{function_name}" raised AssertionError.'
        raise GSLAssertionError(f'Assert_custom: {msg}') from exc
    except Exception as exc:
        raise GSLAssertionError(
            f'Assert_custom: "{function_name}" raised '
            f'{type(exc).__name__}: {exc}'
        ) from exc

    if result is False:
        raise GSLAssertionError(
            f'Assert_custom: "{function_name}" returned False.'
        )
