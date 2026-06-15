#!/usr/bin/env bash
# install.sh  –  One-shot setup + launch for the WSZ6-portal
#
# Run once from the Alpha-Install-Kit folder:
#   bash install.sh
#
# After the first install, use run.sh to start the server again.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DJANGO_DIR="$SCRIPT_DIR/WSP6-portal/Claudes-plan-2/wsz6_portal"
START_SCRIPT="$SCRIPT_DIR/WSP6-portal/Claudes-plan-2/start_server.sh"

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
BOLD=$'\033[1m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
RED=$'\033[0;31m'
CYAN=$'\033[0;36m'
RESET=$'\033[0m'

ok()   { echo -e "  ${GREEN}✓${RESET}  $*"; }
info() { echo -e "  ${CYAN}→${RESET}  $*"; }
warn() { echo -e "  ${YELLOW}!${RESET}  $*"; }
die()  { echo -e "\n  ${RED}ERROR:${RESET} $*\n"; exit 1; }

echo ""
echo -e "${BOLD}=== WSZ6-portal  ·  one-time setup ===${RESET}"
echo ""

# ---------------------------------------------------------------------------
# Step 1 — find Python 3.10+
# ---------------------------------------------------------------------------
echo -e "${BOLD}[1/6] Checking Python...${RESET}"

PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)
        major=${ver%%.*}
        minor=${ver#*.}
        if [ "$major" -eq 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$candidate"
            ok "Found $candidate  (Python $ver)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo ""
    warn "Python 3.10 or later was not found on your PATH."
    echo ""

    # OS-specific install hint
    OS="$(uname -s)"
    if [ "$OS" = "Darwin" ]; then
        echo "  Install it with Homebrew:"
        echo "    brew install python@3.11"
        echo ""
        echo "  No Homebrew?  https://brew.sh"
    else
        # Linux / WSL
        echo "  Install it with:"
        echo "    sudo apt update && sudo apt install python3.11 python3.11-venv"
    fi
    echo ""
    die "Re-run this script after installing Python."
fi

# ---------------------------------------------------------------------------
# Step 2 — create virtual environment
# ---------------------------------------------------------------------------
echo -e "${BOLD}[2/6] Setting up virtual environment...${RESET}"

VENV="$DJANGO_DIR/.venv"
if [ -d "$VENV" ]; then
    ok "Virtual environment already exists – skipping."
else
    "$PYTHON" -m venv "$VENV"
    ok "Created .venv"
fi

# Activate
# shellcheck source=/dev/null
source "$VENV/bin/activate"
python -m pip install --upgrade pip --quiet
ok "pip up-to-date"

# ---------------------------------------------------------------------------
# Step 3 — install Python dependencies
# ---------------------------------------------------------------------------
echo -e "${BOLD}[3/6] Installing dependencies (may take a minute)...${RESET}"

pip install -r "$DJANGO_DIR/requirements.txt" --quiet
ok "All packages installed"

# ---------------------------------------------------------------------------
# Step 4 — initialise database
# ---------------------------------------------------------------------------
echo -e "${BOLD}[4/6] Initialising database...${RESET}"

cd "$DJANGO_DIR"

if [ ! -f ".env" ]; then
    cp .env.dev .env
    info "Copied .env.dev → .env"
fi

python manage.py migrate          --run-syncdb 2>&1 | grep -v "^$\|RuntimeWarning\|Accessing the database\|warnings.warn" || true
python manage.py migrate --database=gdm        2>&1 | grep -v "^$\|RuntimeWarning\|Accessing the database\|warnings.warn" || true
ok "Database ready"

# ---------------------------------------------------------------------------
# Step 5 — create dev user accounts
# ---------------------------------------------------------------------------
echo -e "${BOLD}[5/6] Creating accounts...${RESET}"

python manage.py create_dev_users 2>&1 | grep -v "^$\|RuntimeWarning\|Accessing the database\|warnings.warn" || true
ok "Accounts ready  (password: pass1234)"

# ---------------------------------------------------------------------------
# Step 6 — install example games
# ---------------------------------------------------------------------------
echo -e "${BOLD}[6/6] Installing example games...${RESET}"

python manage.py install_test_game 2>&1 | grep -v "^$\|RuntimeWarning\|Accessing the database\|warnings.warn" || true
ok "Games installed"

# ---------------------------------------------------------------------------
# Done — hand off to start_server.sh
# ---------------------------------------------------------------------------
echo ""
echo -e "${GREEN}${BOLD}Setup complete!${RESET}"
echo ""
echo -e "  To start the server again later, run:"
echo -e "    ${BOLD}bash run.sh${RESET}"
echo ""
echo -e "Starting server now..."
echo ""

exec bash "$START_SCRIPT"
