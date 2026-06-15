"""
wsz6_play/internal_api/gsl_state_view.py

Read-only session-state snapshot endpoint for GSL browser-mode assertions.

Only available when settings.DEBUG is True (never exposed in production).

GET /internal-api/gsl/session-state/<session_key>/
Headers: X-Internal-Api-Key: <settings.INTERNAL_API_KEY>

Response JSON:
    {
        "phase":        "playing",
        "step":         3,
        "current_role": 0,
        "active_roles": [0, 1, 2, 3],
        "state_fields": { "winner": null, ... }
    }
"""

import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from wsz6_play import session_store

logger = logging.getLogger(__name__)

# Map session_store status strings → GSL phase names
_STATUS_TO_PHASE = {
    'lobby':       'lobby',
    'in_progress': 'playing',
    'ended':       'ended',
}

_SCALAR_TYPES = (int, float, str, bool, type(None))


def _serialise_state_fields(state) -> dict:
    """Extract scalar fields from the game state object into a plain dict.

    Only includes JSON-safe scalar types and lists whose elements are all
    scalars — avoids emitting large nested dicts or non-serialisable objects.
    """
    try:
        raw = vars(state)
    except TypeError:
        return {}

    result = {}
    for key, val in raw.items():
        if isinstance(val, _SCALAR_TYPES):
            result[key] = val
        elif isinstance(val, (list, tuple)):
            if all(isinstance(v, _SCALAR_TYPES) for v in val):
                result[key] = list(val)
    return result


@require_http_methods(['GET'])
def gsl_session_state(request, session_key: str):
    """Return a lightweight state snapshot for GSL browser-mode assertions."""
    # Debug-only guard — never expose in production
    if not getattr(settings, 'DEBUG', False):
        return JsonResponse({'error': 'Not available in production'}, status=404)

    # Auth check — same pattern as other internal_api endpoints
    if request.headers.get('X-Internal-Api-Key') != settings.INTERNAL_API_KEY:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    sess = session_store.get_session(session_key)
    if sess is None:
        return JsonResponse({'error': 'Session not found'}, status=404)

    status = sess.get('status', 'lobby')
    phase  = _STATUS_TO_PHASE.get(status, status)

    runner = sess.get('game_runner')
    if runner is None:
        # Game not started yet — return lobby-phase snapshot
        return JsonResponse({
            'phase':        phase,
            'step':         0,
            'current_role': None,
            'active_roles': [],
            'state_fields': {},
        })

    state = runner.current_state
    current_role_num = getattr(state, 'current_role_num',
                               getattr(state, 'whose_turn', None))
    active_roles = list(getattr(state, 'active_roles', []))
    step = getattr(runner, 'step', 0)

    return JsonResponse({
        'phase':        phase,
        'step':         step,
        'current_role': current_role_num,
        'active_roles': active_roles,
        'state_fields': _serialise_state_fields(state),
    })
