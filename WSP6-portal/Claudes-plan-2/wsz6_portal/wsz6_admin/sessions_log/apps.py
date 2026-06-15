import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class SessionsLogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'wsz6_admin.sessions_log'
    label = 'sessions_log'
    verbose_name = 'Sessions Log'

    def ready(self):
        # The in-memory session store (wsz6_play.session_store) is wiped on
        # every server restart.  Any DB sessions still marked open/in_progress/
        # paused are therefore stale — no live process is running them and they
        # cannot be rejoined.  Mark them interrupted so the UI doesn't offer a
        # broken "Rejoin" button.
        self._mark_stale_sessions_interrupted()

    @staticmethod
    def _mark_stale_sessions_interrupted():
        try:
            from .models import GameSession
            stale = [
                GameSession.STATUS_OPEN,
                GameSession.STATUS_IN_PROGRESS,
                GameSession.STATUS_PAUSED,
            ]
            count = GameSession.objects.filter(status__in=stale).update(
                status=GameSession.STATUS_INTERRUPTED
            )
            if count:
                logger.info(
                    "Startup: marked %d stale session(s) as interrupted "
                    "(server restarted, in-memory store was wiped).",
                    count,
                )
        except Exception:
            # Tables don't exist yet (e.g. before first migration).  Safe to
            # ignore — the cleanup will run on the next normal startup.
            pass
