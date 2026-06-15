"""wsz6_admin/sessions_log/views.py"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from wsz6_play import session_store as ss

from .models import GameSession


@login_required
def session_list(request):
    q = request.GET.get('q', '').strip()
    user = request.user

    if user.is_any_admin():
        sessions = GameSession.objects.select_related('game', 'owner').order_by('-started_at')
    else:
        sessions = GameSession.objects.filter(owner=user).select_related('game').order_by('-started_at')

    if q:
        sessions = sessions.filter(
            Q(game__name__icontains=q) | Q(owner__username__icontains=q)
        )

    # Cross-reference the live in-memory session store so the template can
    # gate Join/Rejoin/Resume buttons on whether the session is actually alive.
    # (The DB may still show 'in_progress' for sessions whose server process
    # has since restarted and whose store entry is therefore gone.)
    live_keys = {s['session_key'] for s in ss.get_all_sessions()}

    session_list = list(sessions[:50])
    for s in session_list:
        s.is_live = str(s.session_key) in live_keys

    return render(request, 'sessions_log/list.html', {'sessions': session_list, 'q': q})


@login_required
@require_POST
def delete_session(request, session_key):
    """Delete an owned session that is not currently in progress."""
    session_obj = get_object_or_404(GameSession, session_key=session_key, owner=request.user)
    if session_obj.status == GameSession.STATUS_IN_PROGRESS:
        # Refuse to delete a live session — players are still connected.
        return redirect('sessions_log:list')
    session_obj.delete()
    # Also evict from the in-memory store if it's still there (e.g. paused lobby).
    ss.delete_session(str(session_key))
    return redirect('sessions_log:list')
