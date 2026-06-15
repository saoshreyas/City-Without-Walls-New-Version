"""
wsz6_play/gsl/browser_assertions.py

Async handler functions for every GSL Assert_* command in browser mode.

Each handler signature:
    async def assert_<keyword>_browser(args: list[str],
                                       session: BrowserSession) -> None

Most assertions delegate to the /internal-api/gsl/session-state/ endpoint
for reliable values rather than DOM scraping.  DOM-based checks are only
used where they directly test visible rendering (Assert_view_exists).

Auth header for state endpoint uses X-Internal-Api-Key (same pattern as
other internal_api endpoints — NOT X-GSL-Internal as the draft plan stated).
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path

import httpx
from django.conf import settings

from .browser_session import BrowserSession
from .commands import _resolve_role_num
from .context import GSLContext
from .errors import GSLAssertionError, GSLSyntaxError

logger = logging.getLogger(__name__)

# Map GSL phase names ↔ session_store status strings (mirrors assertions.py)
_PHASE_TO_STATUS = {
    'lobby':   'lobby',
    'playing': 'in_progress',
    'ended':   'ended',
}

_SCALAR_TYPES = (int, float, str, bool, type(None))


# ---------------------------------------------------------------------------
# State-endpoint helper
# ---------------------------------------------------------------------------

async def _fetch_gsl_state(session: BrowserSession) -> dict:
    """Fetch the session state snapshot from the running server.

    Uses X-Internal-Api-Key auth (same as other internal_api endpoints).
    Raises GSLAssertionError on HTTP error or if session not found.
    """
    url = (
        f'{session.base_url}/internal/v1/gsl/session-state/'
        f'{session.session_key}/'
    )
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                url,
                headers={'X-Internal-Api-Key': settings.INTERNAL_API_KEY},
                timeout=10,
            )
        except httpx.ConnectError as exc:
            raise GSLAssertionError(
                f'GSL state endpoint unreachable at {url}: {exc}'
            ) from exc

    if r.status_code == 404:
        raise GSLAssertionError(
            f'GSL state endpoint returned 404. '
            'Is DEBUG=True and is the server running?'
        )
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise GSLAssertionError(
            f'GSL state endpoint error {r.status_code}: {r.text}'
        ) from exc

    return r.json()


# ---------------------------------------------------------------------------
# Shared value-comparison helper (mirrors api-mode _coerce_expected)
# ---------------------------------------------------------------------------

def _coerce_expected(s: str):
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


def _resolve_key_from_dict(state_fields: dict, key: str):
    """Walk a dot-notation key into a flat state_fields dict.

    Supports dot-notation (e.g. 'winner', 'active_roles.0',
    'active_roles.length').  Raises GSLAssertionError on missing key.
    """
    parts = key.split('.')
    obj = state_fields
    for part in parts:
        if part == 'length':
            try:
                obj = len(obj)
            except TypeError as exc:
                raise GSLAssertionError(
                    f'Assert_state (browser): ".length" applied to '
                    f'non-sequence at key "{key}"'
                ) from exc
        elif isinstance(obj, (list, tuple)):
            try:
                obj = obj[int(part)]
            except (IndexError, ValueError) as exc:
                raise GSLAssertionError(
                    f'Assert_state (browser): index "{part}" out of range '
                    f'for key "{key}"'
                ) from exc
        elif isinstance(obj, dict):
            if part not in obj:
                raise GSLAssertionError(
                    f'Assert_state (browser): key "{part}" not found '
                    f'in state_fields (full key: "{key}")'
                )
            obj = obj[part]
        else:
            raise GSLAssertionError(
                f'Assert_state (browser): cannot descend into '
                f'{type(obj).__name__} at part "{part}" (full key: "{key}")'
            )
    return obj


# ---------------------------------------------------------------------------
# Assertion handlers
# ---------------------------------------------------------------------------

async def assert_phase_browser(args: list[str],
                                session: BrowserSession) -> None:
    """Assert_phase <lobby|playing|ended>"""
    if len(args) != 1:
        raise GSLSyntaxError('Assert_phase requires exactly one argument')

    expected_phase = args[0].lower()
    if expected_phase not in _PHASE_TO_STATUS:
        raise GSLSyntaxError(
            f'Assert_phase: unknown phase "{expected_phase}". '
            'Valid values: lobby, playing, ended'
        )

    data = await _fetch_gsl_state(session)
    actual_phase = data.get('phase', '?')

    if actual_phase != expected_phase:
        raise GSLAssertionError(
            f'Assert_phase failed: expected "{expected_phase}", '
            f'got "{actual_phase}"'
        )


async def assert_active_role_browser(args: list[str],
                                      session: BrowserSession) -> None:
    """Assert_active_role <role_name>"""
    if len(args) != 1:
        raise GSLSyntaxError('Assert_active_role requires exactly one argument')

    expected = args[0]
    data     = await _fetch_gsl_state(session)

    current_role_num = data.get('current_role')
    if current_role_num is None:
        raise GSLAssertionError(
            'Assert_active_role (browser): game has not started '
            '(current_role is null in state snapshot)'
        )

    if session.role_manager is None:
        raise GSLAssertionError(
            'Assert_active_role (browser): role_manager not initialised. '
            'Was Create_Session called?'
        )

    roles = session.role_manager.roles_spec.roles
    if not (0 <= current_role_num < len(roles)):
        raise GSLAssertionError(
            f'Assert_active_role (browser): current_role_num '
            f'{current_role_num} out of range (0–{len(roles) - 1})'
        )

    actual = roles[current_role_num].name
    if actual != expected:
        raise GSLAssertionError(
            f'Assert_active_role failed: expected "{expected}", got "{actual}"'
        )


async def assert_state_browser(args: list[str],
                                session: BrowserSession) -> None:
    """Assert_state <key> <expected_value>"""
    if len(args) != 2:
        raise GSLSyntaxError(
            'Assert_state requires exactly two arguments: <key> <expected_value>'
        )

    key, expected_raw = args
    data              = await _fetch_gsl_state(session)
    state_fields      = data.get('state_fields', {})

    actual   = _resolve_key_from_dict(state_fields, key)
    expected = _coerce_expected(expected_raw)

    if actual != expected:
        raise GSLAssertionError(
            f'Assert_state (browser) failed: {key} = {actual!r} '
            f'(expected {expected!r})'
        )


async def assert_player_count_browser(args: list[str],
                                       session: BrowserSession) -> None:
    """Assert_player_count <n>"""
    if len(args) != 1:
        raise GSLSyntaxError('Assert_player_count requires exactly one argument')

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


async def assert_role_count_browser(args: list[str],
                                     session: BrowserSession) -> None:
    """Assert_role_count <n>"""
    if len(args) != 1:
        raise GSLSyntaxError('Assert_role_count requires exactly one argument')

    try:
        expected = int(args[0])
    except ValueError:
        raise GSLSyntaxError(
            f'Assert_role_count: expected an integer, got "{args[0]}"'
        )

    data         = await _fetch_gsl_state(session)
    active_roles = data.get('active_roles', [])
    actual       = len(active_roles)

    if actual != expected:
        raise GSLAssertionError(
            f'Assert_role_count failed: expected {expected}, '
            f'got {actual} (active_roles={active_roles!r})'
        )


async def assert_view_exists_browser(args: list[str],
                                      session: BrowserSession) -> None:
    """Assert_view_exists <user> <role>

    Browser-mode check: verifies that the player holds the role AND that
    the game page (viewed as that role) renders without an error.
    """
    if len(args) != 2:
        raise GSLSyntaxError('Assert_view_exists requires <user> <role>')

    display, role_name = args

    player = session.players.get(display)
    if player is None:
        raise GSLAssertionError(
            f'Assert_view_exists: player "{display}" not found '
            f'(known: {list(session.players)})'
        )

    if session.role_manager is None:
        raise GSLAssertionError(
            'Assert_view_exists (browser): role_manager not initialised.'
        )

    role_num = _resolve_role_num(session.role_manager, role_name)

    if not session.role_manager.player_has_role(player.token, role_num):
        raise GSLAssertionError(
            f'Assert_view_exists failed: player "{display}" does not hold '
            f'role "{role_name}"'
        )

    # Also verify via server state that the role is active.
    data         = await _fetch_gsl_state(session)
    active_roles = data.get('active_roles', [])
    if role_num not in active_roles:
        raise GSLAssertionError(
            f'Assert_view_exists failed: role "{role_name}" (index {role_num}) '
            f'is not in server active_roles {active_roles!r}'
        )

    bctx = session.browser_players.get(display)
    if bctx is None:
        # If no browser context, fall back to server-only check (already passed).
        return

    from playwright.async_api import expect

    page = bctx.page

    # Switch to the target role view if the player holds multiple roles.
    # Only click if the button is enabled — the currently-active role's
    # button is disabled (btn-primary) and does not need to be clicked.
    selector_div = page.locator('#role-selector-btns')
    if await selector_div.is_visible():
        roles    = session.role_manager.roles_spec.roles
        btn_text = roles[role_num].name
        btn = selector_div.locator('button', has_text=btn_text)
        if await btn.count() > 0 and await btn.first.is_enabled():
            await btn.first.click()
            await page.wait_for_timeout(400)

    # Check that vis-display or state-display is visible and not showing an error.
    vis = page.locator('#vis-display, #state-display')
    await expect(vis.first).to_be_visible(timeout=session.default_timeout)
    # A rendered view should not contain the word "Error" as a standalone header.
    content = await vis.first.text_content() or ''
    if 'Error' in content and len(content) < 200:
        raise GSLAssertionError(
            f'Assert_view_exists failed: vis/state display appears to '
            f'contain an error for player "{display}" role "{role_name}": '
            f'{content[:200]!r}'
        )


async def assert_custom_browser(args: list[str],
                                 session: BrowserSession) -> None:
    """Assert_custom <module_or_file> <function> [arg1 [arg2 …]]

    Loads a user-supplied check function and calls it with a GSLContext
    whose mode='browser'.  The state is fetched from the server endpoint.
    """
    if len(args) < 2:
        raise GSLSyntaxError(
            'Assert_custom requires at least <module_or_file> <function>'
        )

    module_or_file = args[0]
    function_name  = args[1]
    extra_raw      = args[2:]

    # Load the module (same logic as api-mode assert_custom).
    if module_or_file.endswith('.py'):
        path = Path(module_or_file)
        if not path.is_absolute():
            path = Path.cwd() / path
        spec = importlib.util.spec_from_file_location('_gsl_check', str(path))
        if spec is None:
            raise GSLAssertionError(
                f'Assert_custom: cannot create module spec from '
                f'"{module_or_file}"'
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

    # Build a GSLContext using the server state snapshot.
    data = await _fetch_gsl_state(session)
    active_roles = []
    if session.role_manager is not None:
        roles = session.role_manager.roles_spec.roles
        active_roles = [
            roles[rn].name
            for rn in data.get('active_roles', [])
            if 0 <= rn < len(roles)
        ]

    # state is a simple namespace constructed from state_fields.
    from types import SimpleNamespace
    state_ns = SimpleNamespace(**data.get('state_fields', {}))

    ctx = GSLContext(
        state=state_ns,
        session={'session_key': session.session_key,
                 'status': _PHASE_TO_STATUS.get(data.get('phase', ''), '')},
        players=session.players,
        active_roles=active_roles,
        mode='browser',
    )

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
