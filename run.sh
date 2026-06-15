#!/usr/bin/env bash
# run.sh  –  Start the WSZ6-portal server (after install.sh has been run once)
#
# Usage:
#   bash run.sh
#
# To install for the first time, use install.sh instead.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START_SCRIPT="$SCRIPT_DIR/WSP6-portal/Claudes-plan-2/start_server.sh"
VENV="$SCRIPT_DIR/WSP6-portal/Claudes-plan-2/wsz6_portal/.venv"

if [ ! -d "$VENV" ]; then
    echo ""
    echo "  Setup has not been run yet.  Run this first:"
    echo "    bash install.sh"
    echo ""
    exit 1
fi

exec bash "$START_SCRIPT"
