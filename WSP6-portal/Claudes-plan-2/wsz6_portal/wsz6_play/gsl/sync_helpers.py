"""
wsz6_play/gsl/sync_helpers.py

Playwright wait helpers for GSL browser-mode execution.

WebSocket-driven UIs do not update synchronously.  Every browser action
that triggers a server-side state change must be followed by an explicit
wait.  All helpers are ``async``; timeout values are always explicit —
never implemented as bare ``asyncio.sleep``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

    from .browser_session import BrowserSession


async def wait_for_step_change(page, old_step: int, timeout: int) -> int:
    """Wait until data-gsl-step on the page differs from old_step.

    Returns the new step value.

    The attribute is set on ``#state-display`` by game.html's
    ``onStateUpdate`` handler on every WebSocket state_update message.
    """
    from playwright.async_api import expect
    locator = page.locator('#state-display[data-gsl-step]')
    await expect(locator).not_to_have_attribute(
        'data-gsl-step', str(old_step), timeout=timeout
    )
    new_step_str = await locator.get_attribute('data-gsl-step')
    return int(new_step_str)


async def wait_for_phase(page, phase: str, timeout: int) -> None:
    """Wait until [data-gsl-phase] == phase.

    The attribute is set on ``.game-wrap`` in game.html; it starts as
    "playing" and is updated to "ended" on goal_reached WS messages.
    """
    from playwright.async_api import expect
    await expect(page.locator('[data-gsl-phase]')).to_have_attribute(
        'data-gsl-phase', phase, timeout=timeout
    )


async def wait_for_all_pages_at_game(browser_players: dict, timeout: int) -> None:
    """After Start_game, wait for every player's page to reach /play/game/."""
    for ctx in browser_players.values():
        await ctx.page.wait_for_url('**/play/game/**', timeout=timeout)


async def wait_for_role_chip(page, display_name: str,
                              role_num: int, timeout: int) -> None:
    """Wait for a player chip to appear in the specified role row.

    Relies on the ``data-role-num`` attribute added to ``.role-row`` in
    the join.html template and the player's display name appearing in the
    chip text.
    """
    from playwright.async_api import expect
    row = page.locator(
        f'[data-role-num="{role_num}"] .player-chip',
        has_text=display_name,
    )
    await expect(row).to_be_visible(timeout=timeout)


async def get_current_step(page) -> int:
    """Read the current data-gsl-step value from the game page.

    Returns 0 if the attribute has not yet been set (pre-first-move).
    """
    val = await page.locator('#state-display').get_attribute('data-gsl-step')
    if val is None:
        return 0
    try:
        return int(val)
    except ValueError:
        return 0
