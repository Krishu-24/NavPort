#!/usr/bin/env bash
# ============================================================
#  NavPort launcher (macOS / Linux)
#  - Verifies Python 3.9+ is installed
#  - Creates a virtual environment (.venv) if one doesn't exist
#  - Installs dependencies only if requirements.txt changed
#  - Starts the Flask server
#  Double-click in Finder, or run: ./run.command
# ============================================================

set -uo pipefail

cd "$(dirname "$0")" || exit 1

BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'; RESET=$'\033[0m'

say()  { printf '%s\n' "$*"; }
ok()   { printf '%s[OK]%s %s\n'    "$GREEN" "$RESET" "$*"; }
step() { printf '%s[..]%s %s\n'    "$DIM"   "$RESET" "$*"; }
die()  {
    printf '%s[ERROR]%s %s\n' "$RED" "$RESET" "$*" >&2
    printf '\nPress Return to close.\n'
    read -r _ 2>/dev/null || true
    exit 1
}

say ""
say "${BOLD}================================================${RESET}"
say "${BOLD}  NavPort - Flight Weather Dashboard${RESET}"
say "${BOLD}================================================${RESET}"
say ""

# ---- 1. Locate a Python interpreter ---------------------------------
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        # macOS ships a python3 stub that only prompts to install Xcode tools.
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    die "Python 3.9 or newer was not found.
        Install it from https://www.python.org/downloads/
        or, with Homebrew:  brew install python"
fi

ok "Found Python: $("$PYTHON" --version 2>&1)"
say ""

# ---- 2. Create the virtual environment if missing --------------------
VENV_DIR=".venv"
VENV_PY="$VENV_DIR/bin/python"

if [ -x "$VENV_PY" ]; then
    ok "Virtual environment already exists - skipping creation."
else
    step "Creating virtual environment in .venv ..."
    "$PYTHON" -m venv "$VENV_DIR" || die "Failed to create the virtual environment.
        Make sure the venv module is available for your Python install."
    ok "Virtual environment created."
fi

[ -x "$VENV_PY" ] || die "Virtual environment python not found at $VENV_PY"
say ""

# ---- 3. Install dependencies only if requirements.txt changed --------
LOCK_FILE="$VENV_DIR/requirements.lock"

if [ -f "$LOCK_FILE" ] && cmp -s requirements.txt "$LOCK_FILE"; then
    ok "Dependencies already installed and up to date - skipping."
else
    step "Installing dependencies from requirements.txt ..."
    "$VENV_PY" -m pip install --upgrade pip --quiet
    "$VENV_PY" -m pip install -r requirements.txt || die "Failed to install dependencies.
        Check your internet connection and try again."
    cp requirements.txt "$LOCK_FILE"
    ok "Dependencies installed."
fi
say ""

# ---- 4. Start the server ---------------------------------------------
say "${BOLD}================================================${RESET}"
say "${BOLD}  Starting NavPort on http://localhost:5000${RESET}"
say "${BOLD}  Press CTRL+C to stop the server.${RESET}"
say "${BOLD}================================================${RESET}"
say ""

"$VENV_PY" run.py
STATUS=$?

say ""
if [ $STATUS -ne 0 ] && [ $STATUS -ne 130 ]; then   # 130 = CTRL+C
    printf '%s[ERROR]%s NavPort exited with code %s. See the output above.\n' "$RED" "$RESET" "$STATUS"
    printf '\nPress Return to close.\n'
    read -r _ 2>/dev/null || true
    exit $STATUS
fi

say "NavPort server stopped."
