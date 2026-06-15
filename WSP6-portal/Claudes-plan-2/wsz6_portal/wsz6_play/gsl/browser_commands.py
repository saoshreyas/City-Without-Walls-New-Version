"""
wsz6_play/gsl/browser_commands.py

Async handler functions for every GSL command in browser mode.

Each handler signature:
    async def handle_<keyword>_browser(args: list[str],
                                       session: BrowserSession) -> None

Browser mode drives a real Chromium browser (via Playwright) against a
running Daphne server.  The game state lives in the server's process;
the management-command process is a Playwright controller only.

Key architecture note (from GSL-API-to-Browser-Mode-Handoff.md §2):
    - Session creation MUST go through POST /internal-api/launch/ so the
      session is registered in the *server's* session_store, not a local
      copy.
    - State reads for assertions go through /internal-api/gsl/session-state/.
    - Mock user creation writes to the shared database — safe in both modes.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING

import httpx
from django.conf import settings

from .browser_session import BrowserPlayerCtx, BrowserSession
from .commands import _extract_kwargs, _coerce_arg, _resolve_role_num
from .context import GSLPlayer
from .errors import (
    GSLCommandError,
    GSLOrderError,
    GSLSecurityError,
    GSLSyntaxError,
)
from .mock_accounts import create_mock_user
from .sync_helpers import (
    get_current_step,
    wait_for_all_pages_at_game,
    wait_for_role_chip,
    wait_for_step_change,
)

if TYPE_CHECKING:
    pass   # Playwright types only needed for type checkers

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _create_mock_async_browser(display_name: str) -> tuple:
    """Create a mock user in a thread; returns (user, raw_password)."""
    return await asyncio.to_thread(create_mock_user, display_name)


async def _get_user_async(username: str):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return await asyncio.to_thread(
        lambda: User.objects.get(username=username)
    )


async def _get_game_async(slug: str):
    from wsz6_admin.games_catalog.models import Game
    return await asyncio.to_thread(
        lambda: Game.objects.get(slug=slug)
    )


def _owner_ctx(session: BrowserSession) -> BrowserPlayerCtx:
    """Return the BrowserPlayerCtx for the first registered player (= owner)."""
    first_display = next(iter(session.browser_players))
    return session.browser_players[first_display]


async def _switch_view_if_needed(page, role_num: int,
                                  session: BrowserSession) -> None:
    """Click the role selector button if the page is not already on role_num.

    Used before Op and Assert_view_exists to ensure the correct role's
    operators / vis are displayed.
    """
    # Read the currently active role from the page's role-selector buttons.
    # The active button has the 'active' or 'btn-primary' class.
    # We fall back to clicking the right role label if any selector exists.
    selector_div = page.locator('#role-selector-btns')
    if not await selector_div.is_visible():
        return   # single-role player — no selector shown

    role_manager = session.role_manager
    if role_manager is None:
        return
    roles = role_manager.roles_spec.roles
    if not (0 <= role_num < len(roles)):
        return
    role_name = roles[role_num].name

    # Click the button with the matching role name.
    # Skip if already active (active button is disabled in game.html).
    btn = selector_div.locator('button', has_text=role_name)
    if await btn.count() > 0 and await btn.first.is_enabled():
        await btn.first.click()
        # Brief wait for the view to switch.
        await page.wait_for_timeout(400)


# ---------------------------------------------------------------------------
# Session setup command handlers
# ---------------------------------------------------------------------------

async def handle_login_browser(args: list[str], session: BrowserSession) -> None:
    """Login <user> [<password>] [display:"<name>"]

    Opens a new browser context, navigates to /accounts/login/, fills and
    submits the login form, then waits for the redirect to complete.
    """
    if not args:
        raise GSLSyntaxError('Login requires at least a username argument')

    positional, kwargs = _extract_kwargs(args)
    if not positional:
        raise GSLSyntaxError('Login requires a username argument')

    username = positional[0]
    password = positional[1] if len(positional) > 1 else None
    display  = kwargs.get('display', '') or username

    if username == 'mock' or password is None:
        user, raw_password = await _create_mock_async_browser(display)
        actual_username    = user.username
        is_mock            = True
    else:
        logger.warning(
            '[GSL browser] Plaintext password supplied to Login. '
            'Use Login %s $ENV_VAR display:"%s" to suppress this warning.',
            username, display,
        )
        try:
            user = await _get_user_async(username)
        except Exception:
            raise GSLCommandError(f'Login: user "{username}" not found.')
        if not user.check_password(password):
            raise GSLCommandError(
                f'Login: incorrect password for user "{username}".'
            )
        actual_username = username
        raw_password    = password
        is_mock         = False

    # Open a fresh browser context (isolated cookies / session) per player.
    ctx  = await session.browser.new_context()
    page = await ctx.new_page()

    login_url = f'{session.base_url}/accounts/login/'
    await page.goto(login_url)
    await page.fill('#id_username', actual_username)
    await page.fill('#id_password', raw_password)
    await page.click('button[type="submit"]')
    # Wait for the post-login redirect to settle.
    await page.wait_for_load_state('networkidle')

    session.browser_players[display] = BrowserPlayerCtx(
        display_name=display,
        username=actual_username,
        raw_password=raw_password,
        browser_ctx=ctx,
        page=page,
    )

    # Register in session.players so assertions can reference by display_name.
    token = ''   # back-filled by handle_create_session_browser
    if session.role_manager is not None:
        token = session.role_manager.add_player(display, user.pk)

    session.players[display] = GSLPlayer(
        display_name=display,
        token=token,
        user_id=user.pk,
        is_mock=is_mock,
    )
    logger.info(
        '[GSL browser] Login OK: username=%r display=%r mock=%s',
        actual_username, display, is_mock,
    )


async def handle_select_game_browser(args: list[str],
                                     session: BrowserSession) -> None:
    """Select_Game <game_slug> — store slug; no browser navigation needed."""
    if len(args) != 1:
        raise GSLSyntaxError('Select_Game requires exactly one argument: <game_slug>')

    slug = args[0]
    try:
        game = await _get_game_async(slug)
    except Exception:
        raise GSLCommandError(
            f'Select_Game: game "{slug}" not found in the database. '
            'Has it been installed with install_test_game?'
        )

    session.game_slug = slug
    logger.info('[GSL browser] Selected game: %s (slug=%r)', game.name, slug)


async def handle_create_session_browser(args: list[str],
                                        session: BrowserSession) -> None:
    """Create_Session [name:"<label>"]

    Calls POST /internal-api/launch/ so the session is registered in the
    *server's* session_store (not the management command's local copy).
    Then navigates the owner's browser tab to the lobby URL.
    """
    if not session.game_slug:
        raise GSLOrderError('Create_Session must follow Select_Game')
    if not session.browser_players:
        raise GSLOrderError('Create_Session requires at least one Login first')

    _, kwargs = _extract_kwargs(args)
    label = kwargs.get('name', f'GSL browser session – {session.game_slug}')

    owner_display = next(iter(session.browser_players))
    owner_bctx    = session.browser_players[owner_display]
    owner_player  = session.players.get(owner_display)
    owner_id      = owner_player.user_id if owner_player else None

    # Ask the running server to register the session in its session_store.
    url = f'{session.base_url}/internal/v1/launch/'
    async with httpx.AsyncClient() as client:
        r = await client.post(
            url,
            json={
                'game_slug': session.game_slug,
                'owner_id':  owner_id,
                'game_name': label,
            },
            headers={'X-Internal-Api-Key': settings.INTERNAL_API_KEY},
            timeout=10,
        )
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise GSLCommandError(
            f'Create_Session: launch request failed '
            f'(status {r.status_code}): {r.text}'
        ) from exc

    data = r.json()
    session.session_key = data['session_key']
    lobby_url = f'{session.base_url}{data["lobby_url"]}'

    # Navigate the owner's page to the lobby and wait for WS connection.
    await owner_bctx.page.goto(lobby_url)
    await owner_bctx.page.wait_for_selector(
        '#playing-as-badge, #name-overlay',
        timeout=session.default_timeout,
    )

    # If the name overlay appeared, fill it.
    overlay = owner_bctx.page.locator('#name-overlay')
    if await overlay.is_visible():
        await owner_bctx.page.fill('#overlay-name-input', owner_display)
        await owner_bctx.page.press('#overlay-name-input', 'Enter')
        await owner_bctx.page.wait_for_selector(
            '#playing-as-badge', timeout=session.default_timeout
        )

    # Load the game formulation so role resolution works for later commands.
    from django.conf import settings as django_settings
    from wsz6_play.engine.pff_loader import PFFLoadError, load_formulation
    from wsz6_play.engine.role_manager import RoleManager
    from .errors import GSLCommandError as _GSLCommandError

    games_repo = django_settings.GAMES_REPO_ROOT
    try:
        formulation = await asyncio.to_thread(
            load_formulation, session.game_slug, games_repo
        )
    except PFFLoadError as exc:
        raise _GSLCommandError(
            f'Create_Session: failed to load formulation: {exc}'
        ) from exc

    session.formulation  = formulation
    session.role_manager = RoleManager(formulation.roles_spec)

    # Back-fill tokens for players registered before Create_Session.
    for gsl_player in session.players.values():
        if gsl_player.token == '':
            token = session.role_manager.add_player(
                gsl_player.display_name, gsl_player.user_id
            )
            gsl_player.token = token

    logger.info(
        '[GSL browser] Session created: key=%s label=%r lobby=%s',
        session.session_key, label, lobby_url,
    )


async def handle_add_player_browser(args: list[str],
                                    session: BrowserSession) -> None:
    """Add_Player <user> [<password>] [display:"<name>"]

    Opens a new browser context, logs in (if credentials given),
    navigates to the join URL, and fills the name overlay if shown.
    """
    if not args:
        raise GSLSyntaxError('Add_Player requires at least a username argument')
    if not session.session_key:
        raise GSLOrderError('Add_Player must follow Create_Session')

    positional, kwargs = _extract_kwargs(args)
    if not positional:
        raise GSLSyntaxError('Add_Player requires a username argument')

    username = positional[0]
    password = positional[1] if len(positional) > 1 else None
    display  = kwargs.get('display', '') or username

    if username == 'mock' or password is None:
        user, raw_password = await _create_mock_async_browser(display)
        actual_username    = user.username
        is_mock            = True
    else:
        logger.warning(
            '[GSL browser] Plaintext password supplied to Add_Player.',
        )
        try:
            user = await _get_user_async(username)
        except Exception:
            raise GSLCommandError(f'Add_Player: user "{username}" not found.')
        if not user.check_password(password):
            raise GSLCommandError(
                f'Add_Player: incorrect password for "{username}".'
            )
        actual_username = username
        raw_password    = password
        is_mock         = False

    # Open a fresh browser context for this additional player.
    ctx  = await session.browser.new_context()
    page = await ctx.new_page()

    # Log in via the login form.
    login_url = f'{session.base_url}/accounts/login/'
    await page.goto(login_url)
    await page.fill('#id_username', actual_username)
    await page.fill('#id_password', raw_password)
    await page.click('button[type="submit"]')
    await page.wait_for_load_state('networkidle')

    # Navigate to the lobby join URL.
    join_url = f'{session.base_url}/play/join/{session.session_key}/'
    await page.goto(join_url)
    # Wait for either the name overlay (need_identity) or the badge (already set).
    await page.wait_for_selector(
        '#name-overlay, #playing-as-badge',
        timeout=session.default_timeout,
    )
    overlay = page.locator('#name-overlay')
    if await overlay.is_visible():
        await page.fill('#overlay-name-input', display)
        await page.press('#overlay-name-input', 'Enter')
        await page.wait_for_selector('#playing-as-badge',
                                     timeout=session.default_timeout)

    session.browser_players[display] = BrowserPlayerCtx(
        display_name=display,
        username=actual_username,
        raw_password=raw_password,
        browser_ctx=ctx,
        page=page,
    )

    # Register in session.players.
    token = session.role_manager.add_player(display, user.pk)
    session.players[display] = GSLPlayer(
        display_name=display,
        token=token,
        user_id=user.pk,
        is_mock=is_mock,
    )
    logger.info(
        '[GSL browser] Added player %r (mock=%s)', display, is_mock
    )


async def handle_assign_role_browser(args: list[str],
                                     session: BrowserSession) -> None:
    """Assign_role <user> <role_name>

    Clicks the join button in the correct data-role-num row on the player's
    lobby page.  Waits for the player chip to appear in that row to confirm.
    """
    if len(args) < 2:
        raise GSLSyntaxError('Assign_role requires <user> <role_name>')
    if session.role_manager is None:
        raise GSLOrderError('Assign_role must follow Create_Session')

    display   = args[0]
    role_name = args[1]

    player = session.players.get(display)
    if player is None:
        known = ', '.join(f'"{n}"' for n in session.players)
        raise GSLCommandError(
            f'Assign_role: player "{display}" not found. Known players: {known}'
        )

    bctx     = session.browser_players.get(display)
    if bctx is None:
        raise GSLCommandError(
            f'Assign_role: no browser context for player "{display}".'
        )

    role_num = _resolve_role_num(session.role_manager, role_name)

    # Also update the api-side role_manager so assertions stay in sync.
    result = session.role_manager.add_to_role(player.token, role_num)
    if result:
        raise GSLCommandError(f'Assign_role (api-side) failed: {result}')

    join_btn = bctx.page.locator(
        f'[data-role-num="{role_num}"] [data-action="join-role"]'
    )
    await join_btn.click()
    await wait_for_role_chip(bctx.page, display, role_num,
                             session.default_timeout)
    logger.info(
        '[GSL browser] Assigned "%s" to role "%s" (role_num=%d)',
        display, role_name, role_num,
    )


async def handle_set_rng_seed_browser(args: list[str],
                                       session: BrowserSession) -> None:
    """Set_rng_seed <integer> — same production guard as api mode."""
    if len(args) != 1:
        raise GSLSyntaxError('Set_rng_seed requires exactly one integer argument')

    debug = getattr(settings, 'DEBUG', False)
    allow = getattr(settings, 'GSL_ALLOW_SEED', False)
    if not debug and not allow:
        raise GSLSecurityError(
            'Set_rng_seed is not permitted in production. '
            'Set DEBUG=True or GSL_ALLOW_SEED=True in settings (testing only).'
        )
    if session.started:
        raise GSLOrderError('Set_rng_seed must appear before Start_game')

    try:
        session.rng_seed = int(args[0])
    except ValueError:
        raise GSLSyntaxError(
            f'Set_rng_seed: argument must be an integer, got "{args[0]}"'
        )
    logger.warning(
        '[GSL browser] WARNING: Set_rng_seed %d is active — '
        'remove before production deployment.',
        session.rng_seed,
    )


async def handle_start_game_browser(args: list[str],
                                    session: BrowserSession) -> None:
    """Start_game

    Clicks #start-btn on the owner's lobby page; waits for all player pages
    to navigate to /play/game/; captures each player's role_token from URL.
    """
    if not session.session_key:
        raise GSLOrderError('Start_game must follow Create_Session')
    if session.started:
        raise GSLOrderError('Start_game has already been called in this session')

    if session.rng_seed is not None:
        random.seed(session.rng_seed)
        logger.info(
            '[GSL browser] RNG seeded with %d before Start_game click.',
            session.rng_seed,
        )
        session.rng_seed = None

    owner_bctx = _owner_ctx(session)
    await owner_bctx.page.click('#start-btn')
    await wait_for_all_pages_at_game(session.browser_players,
                                     session.default_timeout)

    # Capture role_token from the URL each player landed on:
    # pattern: /play/game/<session_key>/<role_token>/
    for bctx in session.browser_players.values():
        url = bctx.page.url
        bctx.role_token    = url.rstrip('/').split('/')[-1]
        bctx.game_page_url = url

    session.started = True
    logger.info('[GSL browser] Start_game done — all players at game page.')


async def handle_op_browser(args: list[str], session: BrowserSession) -> None:
    """Op <user> <operator_name> [arg1 [arg2 …]]

    Clicks the operator button on the player's game page.
    Supports parameterised operators via #param-form.
    Waits for data-gsl-step to increment after the click.
    """
    if len(args) < 2:
        raise GSLSyntaxError('Op requires at least <user> <operator_name>')
    if not session.started:
        raise GSLOrderError('Op requires a started game (call Start_game first)')

    display     = args[0]
    op_name     = args[1]
    op_args_raw = args[2:]

    player = session.players.get(display)
    if player is None:
        known = ', '.join(f'"{n}"' for n in session.players)
        raise GSLCommandError(
            f'Op: player "{display}" not found. Known players: {known}'
        )

    bctx = session.browser_players.get(display)
    if bctx is None:
        raise GSLCommandError(
            f'Op: no browser context for player "{display}".'
        )
    page = bctx.page

    # Switch to the correct role view if this player holds multiple roles.
    # Determine which role is currently active from the server state.
    await _auto_switch_role_for_op(page, display, op_name, session)

    old_step = await get_current_step(page)

    # Click the operator button (identified by data-op-name).
    btn = page.locator(
        f'#ops-list li button[data-op-name="{op_name}"]'
    )
    await btn.click()

    # Handle parameterised operators: wait for param-form, fill, submit.
    if op_args_raw:
        param_form = page.locator('#param-form')
        await param_form.wait_for(
            state='visible', timeout=session.default_timeout
        )
        for i, raw_val in enumerate(op_args_raw):
            field = page.locator(f'#param-{i}')
            await field.fill(str(raw_val))
        await page.locator('#param-form button.btn-primary').click()

    # Wait for the game step to advance.
    await wait_for_step_change(page, old_step, session.default_timeout)
    logger.info(
        '[GSL browser] Op "%s" by "%s" complete (was step %d).',
        op_name, display, old_step,
    )


async def _auto_switch_role_for_op(page, display: str, op_name: str,
                                    session: BrowserSession) -> None:
    """Switch the view if the player holds multiple roles.

    If the #role-selector-btns is visible, click the correct role button
    before applying the operator.  We identify the target role by checking
    which role's operators are currently applicable for this player's turn.
    """
    selector_div = page.locator('#role-selector-btns')
    if not await selector_div.is_visible():
        return   # single-role player

    # Try each role the player holds and switch to the one that has
    # the target operator in its #ops-list.
    player = session.players.get(display)
    if player is None or session.role_manager is None:
        return

    role_manager = session.role_manager
    roles = role_manager.roles_spec.roles

    for role_num in range(len(roles)):
        if not role_manager.player_has_role(player.token, role_num):
            continue
        role_name = roles[role_num].name
        btn_in_selector = selector_div.locator('button', has_text=role_name)
        if await btn_in_selector.count() == 0:
            continue
        # If the button is disabled it is the currently-active view — check
        # whether the op is already applicable without switching.
        if not await btn_in_selector.first.is_enabled():
            op_btn = page.locator(
                f'#ops-list li button[data-op-name="{op_name}"].applicable'
            )
            if await op_btn.count() > 0:
                return   # already on the right role view
            continue
        # Switch to this role view and check.
        await btn_in_selector.first.click()
        await page.wait_for_timeout(300)
        op_btn = page.locator(
            f'#ops-list li button[data-op-name="{op_name}"].applicable'
        )
        if await op_btn.count() > 0:
            return   # found the right role view


async def handle_view_as_browser(args: list[str],
                                  session: BrowserSession) -> None:
    """View_as <user> <role>

    Clicks the role selector button whose text matches the role name on the
    player's game page.
    """
    if len(args) < 2:
        raise GSLSyntaxError('View_as requires <user> <role>')
    if not session.started:
        raise GSLOrderError('View_as requires a started game')

    display   = args[0]
    role_name = args[1]

    player = session.players.get(display)
    if player is None:
        raise GSLCommandError(f'View_as: player "{display}" not found.')

    role_num = _resolve_role_num(session.role_manager, role_name)

    if not session.role_manager.player_has_role(player.token, role_num):
        raise GSLCommandError(
            f'View_as: player "{display}" does not hold role "{role_name}".'
        )

    bctx = session.browser_players.get(display)
    if bctx is None:
        raise GSLCommandError(
            f'View_as: no browser context for player "{display}".'
        )

    page = bctx.page
    selector_div = page.locator('#role-selector-btns')
    btn = selector_div.locator('button', has_text=role_name)
    # Only click if not already the active role (active button is disabled).
    if await btn.count() > 0 and await btn.first.is_enabled():
        await btn.first.click()
        await page.wait_for_timeout(300)

    # Update the api-side tracking too.
    session.active_view[player.token] = role_num
    logger.info(
        '[GSL browser] %s is now viewing as "%s" (role_num=%d)',
        display, role_name, role_num,
    )
