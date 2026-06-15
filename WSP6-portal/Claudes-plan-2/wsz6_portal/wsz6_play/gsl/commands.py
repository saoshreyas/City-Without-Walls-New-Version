"""
wsz6_play/gsl/commands.py

Async handler functions for every GSL setup and gameplay command.

Each handler signature:
    async def handle_<keyword>(args: list[str], session: GSLSession) -> None

Handlers mutate ``session`` freely.  They raise GSL*Error subclasses on
failure — never swallow exceptions silently.

The no-op broadcast coroutine lives here because it is only needed by the
GameRunner instantiation in handle_start_game.
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import get_user_model

from wsz6_play.engine.game_runner import GameError, GameRunner
from wsz6_play.engine.pff_loader import PFFLoadError, load_formulation
from wsz6_play.engine.role_manager import RoleManager
from wsz6_play import session_store

from .context import GSLPlayer, GSLSession
from .errors import (
    GSLCommandError,
    GSLOrderError,
    GSLSecurityError,
    GSLSyntaxError,
)
from .mock_accounts import create_mock_user

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# No-op broadcast (api mode — no WebSocket needed)
# ---------------------------------------------------------------------------

async def _noop_broadcast(payload: dict) -> None:
    """GameRunner requires a broadcast coroutine; in api mode we discard it."""
    pass


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _extract_kwargs(args: list[str]) -> tuple[list[str], dict[str, str]]:
    """Separate positional args from ``key:value`` keyword args.

    shlex already unquotes ``display:"Alice"`` → ``display:Alice``, so we
    just split on the first colon.
    """
    positional: list[str] = []
    kwargs: dict[str, str] = {}
    for arg in args:
        if ':' in arg:
            key, _, val = arg.partition(':')
            kwargs[key.lower()] = val
        else:
            positional.append(arg)
    return positional, kwargs


def _coerce_arg(s: str):
    """Convert an operator argument string to int, float, or str."""
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _resolve_role_num(role_manager: RoleManager, role_name: str) -> int:
    """Return the integer role index for ``role_name``.

    Raises GSLCommandError if the name is not found in the roles_spec.
    """
    roles = role_manager.roles_spec.roles
    for i, role in enumerate(roles):
        if role.name == role_name:
            return i
    available = ', '.join(f'"{r.name}"' for r in roles)
    raise GSLCommandError(
        f'Role "{role_name}" not found. Available roles: {available}'
    )


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Async ORM / loader helpers (run sync calls in threads)
# ---------------------------------------------------------------------------

async def _get_user_async(username: str):
    User = get_user_model()
    return await asyncio.to_thread(
        lambda: User.objects.get(username=username)
    )


async def _get_game_async(slug: str):
    from wsz6_admin.games_catalog.models import Game
    return await asyncio.to_thread(
        lambda: Game.objects.get(slug=slug)
    )


async def _create_mock_async(display_name: str):
    """Returns (user, raw_password) tuple; wraps create_mock_user in a thread."""
    return await asyncio.to_thread(create_mock_user, display_name)


async def _load_formulation_async(game_slug: str, games_repo_root: str):
    return await asyncio.to_thread(load_formulation, game_slug, games_repo_root)


# ---------------------------------------------------------------------------
# Session setup command handlers
# ---------------------------------------------------------------------------

async def handle_login(args: list[str], session: GSLSession) -> None:
    """Login <user> [<password>] [display:"<name>"]

    Must be the first command in every script.
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
        # Create a temporary mock account (api mode only needs the user object)
        user, _ = await _create_mock_async(display)
        is_mock = True
    else:
        # Warn about plaintext credential in script
        logger.warning(
            '[GSL] Plaintext password supplied to Login. '
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
        is_mock = False

    # Store player — token is '' until Create_Session creates the RoleManager
    if session.role_manager is not None:
        token = session.role_manager.add_player(display, user.pk)
    else:
        token = ''   # back-filled by handle_create_session

    session.players[display] = GSLPlayer(
        display_name=display,
        token=token,
        user_id=user.pk,
        is_mock=is_mock,
    )
    logger.info('[GSL] Login OK: username=%r display=%r mock=%s', username, display, is_mock)


async def handle_select_game(args: list[str], session: GSLSession) -> None:
    """Select_Game <game_slug>"""
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
    logger.info('[GSL] Selected game: %s (slug=%r)', game.name, slug)


async def handle_create_session(args: list[str], session: GSLSession) -> None:
    """Create_Session [name:"<label>"]"""
    if not session.game_slug:
        raise GSLOrderError('Create_Session must follow Select_Game')

    _, kwargs = _extract_kwargs(args)
    label = kwargs.get('name', f'GSL session – {session.game_slug}')

    session.session_key = uuid.uuid4().hex

    # Load the game formulation
    games_repo = settings.GAMES_REPO_ROOT
    try:
        formulation = await _load_formulation_async(session.game_slug, games_repo)
    except PFFLoadError as exc:
        raise GSLCommandError(f'Create_Session: failed to load formulation: {exc}') from exc

    session.formulation  = formulation
    session.role_manager = RoleManager(formulation.roles_spec)

    # Back-fill tokens for players registered before Create_Session (e.g. Login)
    for gsl_player in session.players.values():
        if gsl_player.token == '':
            token = session.role_manager.add_player(
                gsl_player.display_name, gsl_player.user_id
            )
            gsl_player.token = token

    # Register a minimal entry in session_store (for Assert_phase and cleanup)
    session_store.create_session(session.session_key, {
        'session_key':          session.session_key,
        'game_slug':            session.game_slug,
        'game_name':            label,
        'owner_id':             None,
        'pff_path':             '',
        'status':               'lobby',
        'role_manager':         session.role_manager,
        'game_runner':          None,
        'gdm_writer':           None,
        'playthrough_id':       None,
        'latest_checkpoint_id': None,
        'bots':                 [],
        'session_dir':          '',
        'started_at':           _now_iso(),
    })
    logger.info('[GSL] Session created: key=%s label=%r', session.session_key, label)


async def handle_add_player(args: list[str], session: GSLSession) -> None:
    """Add_Player <user> [<password>] [display:"<name>"]"""
    if not args:
        raise GSLSyntaxError('Add_Player requires at least a username argument')
    if session.role_manager is None:
        raise GSLOrderError('Add_Player must follow Create_Session')

    positional, kwargs = _extract_kwargs(args)
    if not positional:
        raise GSLSyntaxError('Add_Player requires a username argument')

    username = positional[0]
    password = positional[1] if len(positional) > 1 else None
    display  = kwargs.get('display', '') or username

    if username == 'mock' or password is None:
        user, _ = await _create_mock_async(display)
        is_mock = True
    else:
        logger.warning(
            '[GSL] Plaintext password supplied to Add_Player. '
            'Use Add_Player %s $ENV_VAR to suppress this warning.',
            username,
        )
        try:
            user = await _get_user_async(username)
        except Exception:
            raise GSLCommandError(f'Add_Player: user "{username}" not found.')
        if not user.check_password(password):
            raise GSLCommandError(
                f'Add_Player: incorrect password for "{username}".'
            )
        is_mock = False

    token = session.role_manager.add_player(display, user.pk)
    session.players[display] = GSLPlayer(
        display_name=display,
        token=token,
        user_id=user.pk,
        is_mock=is_mock,
    )
    logger.info('[GSL] Added player %r (mock=%s token=%s)', display, is_mock, token[:8])


async def handle_assign_role(args: list[str], session: GSLSession) -> None:
    """Assign_role <user> <role_name>"""
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
    if not player.token:
        raise GSLCommandError(
            f'Assign_role: player "{display}" has no token yet '
            '(was Create_Session called?)'
        )

    role_num = _resolve_role_num(session.role_manager, role_name)
    result   = session.role_manager.add_to_role(player.token, role_num)
    if result:
        raise GSLCommandError(f'Assign_role failed: {result}')

    logger.info('[GSL] Assigned "%s" to role "%s" (role_num=%d)', display, role_name, role_num)


async def handle_set_rng_seed(args: list[str], session: GSLSession) -> None:
    """Set_rng_seed <integer>

    Only valid in DEBUG mode or when GSL_ALLOW_SEED=True.
    Must appear before Start_game.
    """
    if len(args) != 1:
        raise GSLSyntaxError('Set_rng_seed requires exactly one integer argument')

    # Production guard
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
        '[GSL] WARNING: Set_rng_seed %d is active — '
        'remove this line before production deployment.',
        session.rng_seed,
    )


async def handle_start_game(args: list[str], session: GSLSession) -> None:
    """Start_game"""
    if session.role_manager is None:
        raise GSLOrderError('Start_game must follow Create_Session')
    if session.started:
        raise GSLOrderError('Start_game has already been called in this session')

    err = session.role_manager.validate_for_start()
    if err:
        raise GSLCommandError(f'Start_game: cannot start — {err}')

    # Apply RNG seed if one was staged by Set_rng_seed
    if session.rng_seed is not None:
        random.seed(session.rng_seed)
        logger.info('[GSL] RNG seeded with %d (initialize_problem will follow)', session.rng_seed)
        session.rng_seed = None   # clear so a second session is not accidentally seeded

    runner = GameRunner(
        formulation=session.formulation,
        role_manager=session.role_manager,
        broadcast_func=_noop_broadcast,
        game_slug=session.game_slug,
    )
    await runner.start()

    session.game_runner = runner
    session.started     = True

    session_store.update_session(session.session_key, {
        'status':      'in_progress',
        'game_runner': runner,
    })
    logger.info('[GSL] Game started: slug=%s step=%d', session.game_slug, runner.step)


# ---------------------------------------------------------------------------
# Gameplay command handlers
# ---------------------------------------------------------------------------

async def handle_op(args: list[str], session: GSLSession) -> None:
    """Op <user> <operator_name> [arg1 [arg2 …]]"""
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

    runner = session.game_runner
    state  = runner.current_state

    # Resolve operator name → index
    ops   = runner.get_ops_info(state)
    match = next((o for o in ops if o['name'] == op_name), None)
    if match is None:
        available = [o['name'] for o in ops]
        raise GSLCommandError(
            f'Op: no operator named "{op_name}". '
            f'Available: {available}'
        )

    op_index        = match['index']
    converted_args  = [_coerce_arg(a) for a in op_args_raw] if op_args_raw else None

    try:
        await runner.apply_operator(op_index, converted_args)
    except GameError as exc:
        raise GSLCommandError(f'Op "{op_name}" failed: {exc}') from exc

    # Update session status if the game just ended
    if runner.finished:
        session_store.update_session(session.session_key, {'status': 'ended'})
        logger.info('[GSL] Game ended at step %d', runner.step)

    logger.info('[GSL] Op "%s" by "%s" → step %d', op_name, display, runner.step)


async def handle_view_as(args: list[str], session: GSLSession) -> None:
    """View_as <user> <role>"""
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

    session.active_view[player.token] = role_num
    logger.info('[GSL] %s is now viewing as "%s" (role_num=%d)', display, role_name, role_num)
