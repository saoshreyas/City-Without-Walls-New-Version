"""
wsz6_play/gsl/mock_accounts.py

Lifecycle management for temporary gsl_mock_* Django user accounts.

All mock accounts share the username prefix 'gsl_mock_' so they can be
identified and purged even if a prior run crashed before cleanup.

Usage pattern:
    # During script execution:
    user = create_mock_user('Bob')   # blocks until ORM call completes

    # In the executor's finally block:
    purge_mock_users()               # deletes all accounts created this run

    # At management command startup:
    purge_stale_mock_users()         # deletes orphans from prior crashes
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict

logger = logging.getLogger(__name__)

# Module-level registry: username → User object (populated during a run)
_registry: Dict[str, object] = {}

MOCK_PREFIX = 'gsl_mock_'


def create_mock_user(display_name: str = '') -> tuple:
    """Create a temporary account, register it, and return (user, raw_password).

    The username is ``gsl_mock_<uuid4hex>`` to guarantee uniqueness.
    The raw password is returned so browser-mode handlers can log in via form.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    username = f'{MOCK_PREFIX}{uuid.uuid4().hex}'
    raw_password = uuid.uuid4().hex
    user = User.objects.create_user(
        username=username,
        password=raw_password,
    )
    _registry[username] = user
    logger.debug('[GSL] Created mock user %s (display: %r)', username, display_name)
    return user, raw_password


def purge_mock_users() -> None:
    """Delete all mock accounts created during this run (synchronous).

    Safe to call from synchronous code (e.g. the management command).
    Call ``await apurge_mock_users()`` from async contexts instead.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    for username in list(_registry):
        try:
            User.objects.filter(username=username).delete()
        except Exception as exc:
            logger.warning('[GSL] Failed to delete mock user %s: %s', username, exc)
        _registry.pop(username, None)
    logger.debug('[GSL] Session mock users purged.')


async def apurge_mock_users() -> None:
    """Async wrapper around purge_mock_users() for use inside coroutines."""
    import asyncio
    await asyncio.to_thread(purge_mock_users)


def purge_stale_mock_users() -> None:
    """Delete any gsl_mock_* accounts left over from a previous crashed run.

    Called once at management-command startup before the script runs.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    deleted, _ = User.objects.filter(username__startswith=MOCK_PREFIX).delete()
    if deleted:
        logger.info('[GSL] Purged %d stale mock account(s) from prior run.', deleted)
