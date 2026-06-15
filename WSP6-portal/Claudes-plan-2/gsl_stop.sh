#!/usr/bin/env bash
# gsl_stop.sh
#
# Stop a running GSL live session launched by gsl_live.sh.
#
# Finds the process via the PID file written by gsl_live.sh, or falls back
# to searching by process name if the PID file is missing.
#
# Usage:
#   bash gsl_stop.sh

PID_FILE="/tmp/gsl_live.pid"
LOG_FILE="/tmp/gsl_live.log"

GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
RED=$'\033[0;31m'
DIM=$'\033[2m'
RESET=$'\033[0m'

# ---------------------------------------------------------------------------
# Find the process
# ---------------------------------------------------------------------------
PID=""

if [ -f "$PID_FILE" ]; then
    CANDIDATE=$(cat "$PID_FILE")
    if kill -0 "$CANDIDATE" 2>/dev/null; then
        PID="$CANDIDATE"
    else
        # Stale PID file
        rm -f "$PID_FILE"
    fi
fi

# Fall back to pgrep if no valid PID file
if [ -z "$PID" ]; then
    PID=$(pgrep -f "run_gsl.*--stay-open" 2>/dev/null | head -1)
fi

if [ -z "$PID" ]; then
    echo -e "${YELLOW}No live GSL session found.${RESET}"
    exit 0
fi

# ---------------------------------------------------------------------------
# Stop it
# ---------------------------------------------------------------------------
echo -e "Stopping live GSL session (PID $PID)…"
kill "$PID" 2>/dev/null

# Wait up to 5 s for the process to exit cleanly (it runs cleanup in finally)
for _ in $(seq 1 20); do
    kill -0 "$PID" 2>/dev/null || break
    sleep 0.25
done

if kill -0 "$PID" 2>/dev/null; then
    echo -e "${YELLOW}Process did not exit cleanly; sending SIGKILL…${RESET}"
    kill -9 "$PID" 2>/dev/null
fi

rm -f "$PID_FILE"
echo -e "${GREEN}Done.${RESET}"

if [ -f "$LOG_FILE" ]; then
    echo -e "${DIM}Session log: $LOG_FILE${RESET}"
fi
