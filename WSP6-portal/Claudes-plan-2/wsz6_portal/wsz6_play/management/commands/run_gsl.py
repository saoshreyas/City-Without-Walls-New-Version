"""
wsz6_play/management/commands/run_gsl.py

Django management command: execute a GSL (Game Setup Language) script.

Usage:
    python manage.py run_gsl <file.gsl> [--mode api|browser] [--log debug|info|error]
                             [--headed] [--gsl-timeout <ms>] [--base-url <url>]

Exit codes:
    0 — all commands and assertions passed
    1 — any command or assertion failed

Examples:
    python manage.py run_gsl ../Test_OCCLUEdo.gsl
    python manage.py run_gsl ../Test_OCCLUEdo.gsl --log debug
    python manage.py run_gsl fixtures/smoke.gsl --mode browser --headed
    python manage.py run_gsl fixtures/smoke.gsl --mode browser --gsl-timeout 60000
"""

import asyncio
import logging
import sys

from django.core.management.base import BaseCommand, CommandError

from wsz6_play.gsl.executor import execute_script
from wsz6_play.gsl.mock_accounts import purge_stale_mock_users
from wsz6_play.gsl.parser import parse_file
from wsz6_play.gsl.errors import GSLSyntaxError


class Command(BaseCommand):
    help = (
        'Execute a GSL (Game Setup Language) script against the portal. '
        'Exit 0 = all assertions passed; exit 1 = failures.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'gsl_file',
            type=str,
            help='Path to the .gsl script file.',
        )
        parser.add_argument(
            '--mode',
            choices=['api', 'browser'],
            default='api',
            help=(
                'Execution mode. '
                '"api" (default) drives the game engine directly via Python. '
                '"browser" drives a real Chromium browser via Playwright '
                'against a running Daphne server.'
            ),
        )
        parser.add_argument(
            '--log',
            choices=['debug', 'info', 'error'],
            default='info',
            help='Log verbosity (default: info).',
        )
        parser.add_argument(
            '--headed',
            action='store_true',
            default=False,
            help=(
                'Browser mode: show the Chromium window instead of running '
                'headless. Invaluable for debugging failing scripts.'
            ),
        )
        parser.add_argument(
            '--gsl-timeout',
            type=int,
            default=30_000,
            metavar='MS',
            help=(
                'Browser mode: Playwright wait timeout in milliseconds '
                '(default: 30000).'
            ),
        )
        parser.add_argument(
            '--base-url',
            type=str,
            default='http://127.0.0.1:8000',
            metavar='URL',
            help=(
                'Browser mode: base URL of the running server '
                '(default: http://127.0.0.1:8000).'
            ),
        )
        parser.add_argument(
            '--stay-open',
            action='store_true',
            default=False,
            help=(
                'Browser mode: after the script completes, keep all browser '
                'windows open and wait for Enter before closing. '
                'Combine with --headed for interactive developer sessions. '
                'Mock accounts are kept alive until Enter is pressed.'
            ),
        )

    def handle(self, *args, **options):
        # Configure logging for this run
        level = getattr(logging, options['log'].upper(), logging.INFO)
        logging.basicConfig(
            level=level,
            format='%(asctime)s %(levelname)-8s %(message)s',
            datefmt='%H:%M:%S',
            force=True,   # override any previously configured root logger
        )

        # Purge stale mock accounts from prior crashed runs
        purge_stale_mock_users()

        # Parse the script file
        gsl_file = options['gsl_file']
        self.stdout.write(f'[GSL] Parsing {gsl_file} …')
        try:
            commands = parse_file(gsl_file)
        except GSLSyntaxError as exc:
            self.stderr.write(self.style.ERROR(f'[GSL] Parse error: {exc}'))
            sys.exit(1)

        self.stdout.write(f'[GSL] Parsed {len(commands)} command(s).')

        mode     = options['mode']
        base_url = options['base_url']

        if mode == 'api':
            exit_code = asyncio.run(
                execute_script(commands, mode='api', log_level=options['log'])
            )
        else:
            exit_code = asyncio.run(
                self._run_browser(
                    commands=commands,
                    log_level=options['log'],
                    base_url=base_url,
                    headed=options['headed'],
                    gsl_timeout=options['gsl_timeout'],
                    stay_open=options['stay_open'],
                )
            )

        sys.exit(exit_code)

    async def _run_browser(
        self,
        commands,
        log_level: str,
        base_url: str,
        headed: bool,
        gsl_timeout: int,
        stay_open: bool = False,
    ) -> int:
        """Run the script in browser mode with full Playwright lifecycle.

        If stay_open is True and the script succeeds (exit code 0), the browser
        windows are kept open until the user presses Enter.  Mock account
        cleanup is deferred until that point so logins remain valid.
        """
        import httpx

        # 1. Server health check — browser mode requires a running server.
        try:
            httpx.get(f'{base_url}/accounts/login/', timeout=5)
        except httpx.ConnectError:
            raise CommandError(
                'Browser mode requires a running server. '
                f'Could not reach {base_url}. '
                'Start the server first (bash start_server.sh), then re-run.'
            )

        # 2. Build the BrowserSession.
        from wsz6_play.gsl.browser_session import BrowserSession
        session = BrowserSession(
            base_url=base_url,
            default_timeout=gsl_timeout,
        )

        # 3. Playwright lifecycle.
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=not headed)
            session.playwright_instance = pw
            session.browser             = browser
            try:
                exit_code = await execute_script(
                    commands,
                    mode='browser',
                    log_level=log_level,
                    browser_session=session,
                    defer_mock_cleanup=stay_open,
                )

                # If requested, hold the browser open until the developer is
                # done interacting with the live session.
                if stay_open and exit_code == 0:
                    self.stdout.write(
                        '\n[GSL] Setup complete.  Browser windows are open.\n'
                        '[GSL] Interact with the game, then press Enter here '
                        'to close the browser and exit.\n'
                    )
                    # Wait until SIGTERM or SIGINT (Ctrl+C) is received.
                    # This works whether stdin is a TTY or a pipe, making it
                    # safe to run from any environment (terminal, tool, CI).
                    import os
                    import signal as _signal

                    loop = asyncio.get_running_loop()
                    stop = asyncio.Event()
                    loop.add_signal_handler(_signal.SIGTERM, stop.set)
                    loop.add_signal_handler(_signal.SIGINT,  stop.set)
                    self.stdout.write(
                        f'[GSL] PID {os.getpid()} — '
                        f'run  kill {os.getpid()}  to close the browser.\n'
                    )
                    try:
                        await stop.wait()
                    finally:
                        loop.remove_signal_handler(_signal.SIGTERM)
                        loop.remove_signal_handler(_signal.SIGINT)

            finally:
                # Close all open browser contexts gracefully.
                for bctx in session.browser_players.values():
                    try:
                        await bctx.browser_ctx.close()
                    except Exception:
                        pass
                await browser.close()

                # If mock cleanup was deferred, do it now (after the browser
                # is closed so the accounts are valid for the full session).
                if stay_open:
                    from wsz6_play.gsl.mock_accounts import apurge_mock_users
                    await apurge_mock_users()

        return exit_code
