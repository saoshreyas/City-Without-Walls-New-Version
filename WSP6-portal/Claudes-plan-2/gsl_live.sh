#!/usr/bin/env bash
# gsl_live.sh
#
# Launch a GSL browser session and leave the Chromium windows open for
# interactive testing.  Runs the management command in the background,
# waits for setup to complete, then returns you to the prompt.
#
# Usage:
#   bash gsl_live.sh                             # default: Setup_OCCLUEdo_Live.gsl
#   bash gsl_live.sh MyGame_Live.gsl             # any .gsl file (relative to repo root)
#   bash gsl_live.sh --port 8080                 # if server is on a non-default port
#   bash gsl_live.sh --headless                  # no visible browser window
#   bash gsl_live.sh --help                      # show this message
#
# Stop the session:
#   bash gsl_stop.sh
#
# The session stays open until you run gsl_stop.sh or the process is killed.

set -e

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DJANGO_DIR="$REPO_ROOT/wsz6_portal"
VENV="$DJANGO_DIR/.venv"
MANAGE="$DJANGO_DIR/manage.py"
PID_FILE="/tmp/gsl_live.pid"
LOG_FILE="/tmp/gsl_live.log"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
PORT=8000
HEADED=true
GSL_SCRIPT="$REPO_ROOT/Setup_OCCLUEdo_Live.gsl"

# ---------------------------------------------------------------------------
# Parse flags
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)
            PORT="$2"; shift 2 ;;
        --headless)
            HEADED=false; shift ;;
        --help|-h)
            cat <<'USAGE'
Usage: bash gsl_live.sh [SCRIPT] [FLAGS]

Launches a GSL browser session and leaves the windows open for interactive
testing.  The process runs in the background; use gsl_stop.sh to close it.

Arguments:
  SCRIPT        Path to .gsl file, relative to repo root (default: Setup_OCCLUEdo_Live.gsl)

Flags:
  --port PORT   Port the server is running on (default: 8000)
  --headless    Run Chromium headlessly (no visible window)
  --help, -h    Show this message

Examples:
  bash gsl_live.sh
  bash gsl_live.sh MyGame_Live.gsl
  bash gsl_live.sh --port 8080
USAGE
            exit 0 ;;
        -*)
            echo "Unknown flag: $1  (use --help for usage)"
            exit 1 ;;
        *)
            # Treat as script path — resolve to absolute
            if [[ "$1" = /* ]]; then
                GSL_SCRIPT="$1"
            else
                GSL_SCRIPT="$REPO_ROOT/$1"
            fi
            shift ;;
    esac
done

BASE_URL="http://127.0.0.1:$PORT"

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
BOLD=$'\033[1m'
DIM=$'\033[2m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
CYAN=$'\033[0;36m'
RED=$'\033[0;31m'
WHITE=$'\033[1;37m'
RESET=$'\033[0m'

# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------
if [ ! -f "$MANAGE" ]; then
    echo -e "${RED}ERROR: manage.py not found at $MANAGE${RESET}"
    echo "Run this script from the Claudes-plan-2/ repo root."
    exit 1
fi

if [ ! -d "$VENV" ]; then
    echo -e "${RED}ERROR: Virtual environment not found at $VENV${RESET}"
    echo "Run wsz6_portal/setup_dev.sh first."
    exit 1
fi

if [ ! -f "$GSL_SCRIPT" ]; then
    echo -e "${RED}ERROR: GSL script not found: $GSL_SCRIPT${RESET}"
    exit 1
fi

# Check the server is reachable before spending time on browser setup.
if ! curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/accounts/login/" 2>/dev/null | grep -q "200"; then
    echo -e "${RED}ERROR: Server not reachable at $BASE_URL${RESET}"
    echo "Start the server first:  bash start_server.sh"
    exit 1
fi

# Warn if a session is already running.
if [ -f "$PID_FILE" ]; then
    EXISTING_PID=$(cat "$PID_FILE")
    if kill -0 "$EXISTING_PID" 2>/dev/null; then
        echo -e "${YELLOW}WARNING: A live GSL session is already running (PID $EXISTING_PID).${RESET}"
        echo "Run  bash gsl_stop.sh  to close it first, or proceed to start another."
        read -rp "Start anyway? [y/N] " confirm
        [[ "$confirm" =~ ^[Yy]$ ]] || exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

# ---------------------------------------------------------------------------
# Build and launch the management command
# ---------------------------------------------------------------------------
HEADED_FLAG=""
[ "$HEADED" = true ] && HEADED_FLAG="--headed"

export DJANGO_SETTINGS_MODULE=wsz6_portal.settings.development
export ADMIN_PASS="${ADMIN_PASS:-pass1234}"

cd "$DJANGO_DIR"

# Clear the log from any previous run.
: > "$LOG_FILE"

PYTHONUNBUFFERED=1 "$VENV/bin/python" manage.py run_gsl "$GSL_SCRIPT" \
    --mode browser $HEADED_FLAG --stay-open \
    --base-url "$BASE_URL" \
    > "$LOG_FILE" 2>&1 &

GSL_PID=$!
echo "$GSL_PID" > "$PID_FILE"

# ---------------------------------------------------------------------------
# Wait for setup to complete (or fail)
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${WHITE}GSL live session — ${GSL_SCRIPT##*/}${RESET}"
echo -e "${DIM}Log: $LOG_FILE${RESET}"
echo ""

SPINNER='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
i=0
printf "  "

while kill -0 "$GSL_PID" 2>/dev/null; do
    if grep -q "Browser windows are open" "$LOG_FILE" 2>/dev/null; then
        printf "\r  ${GREEN}✓ Browser windows are open.${RESET}                    \n"
        break
    fi
    if grep -qE "\[GSL FATAL\]|GSLSyntaxError|GSLCommandError|Traceback" "$LOG_FILE" 2>/dev/null; then
        printf "\r  ${RED}✗ Setup failed.${RESET}                                 \n\n"
        echo -e "${DIM}--- Last 20 lines of $LOG_FILE ---${RESET}"
        tail -20 "$LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
    # Also exit if the process died before showing success
    if ! kill -0 "$GSL_PID" 2>/dev/null; then
        printf "\r  ${RED}✗ Process exited unexpectedly.${RESET}                   \n\n"
        tail -20 "$LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
    printf "\r  %s Setting up…" "${SPINNER:$((i % ${#SPINNER})):1}"
    i=$((i + 1))
    sleep 0.25
done

# ---------------------------------------------------------------------------
# Ready panel
# ---------------------------------------------------------------------------
SCRIPT_NAME="${GSL_SCRIPT##*/}"
PAD_SCRIPT=$(printf '%*s' $((44 - ${#SCRIPT_NAME})) '')
PAD_URL=$(printf '%*s' $((44 - ${#BASE_URL})) '')
PAD_PID=$(printf '%*s' $((44 - ${#GSL_PID})) '')

echo ""
cat <<PANEL
${BOLD}${WHITE}
╔══════════════════════════════════════════════════════════════════╗
║               GSL LIVE SESSION — READY                          ║
╠══════════════════════════════════════════════════════════════════╣
║  Script:  ${SCRIPT_NAME}${PAD_SCRIPT}║
║  Server:  ${BASE_URL}${PAD_URL}║
║  PID:     ${GSL_PID}${PAD_PID}║
╠══════════════════════════════════════════════════════════════════╣
║  Chromium windows are open and ready for interaction.           ║
║                                                                  ║
║  When you are done:   ${CYAN}bash gsl_stop.sh${WHITE}                       ║
╚══════════════════════════════════════════════════════════════════╝
${RESET}
PANEL
