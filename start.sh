#!/usr/bin/env bash
# =============================================================================
#  Sigmoji Discord Bot — macOS / Linux startup script
#  Usage:
#    ./start.sh            (reads PORT from .env, default 8080)
#    PORT=9090 ./start.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  =========================================="
echo "    🎮  Sigmoji Discord Bot"
echo "  =========================================="
echo ""

# ── Read PORT from .env (env var takes precedence) ────────────────────────────
if [[ -z "${PORT:-}" ]] && [[ -f ".env" ]]; then
    PORT_LINE=$(grep -E '^\s*PORT\s*=' .env 2>/dev/null | head -1 || true)
    if [[ -n "$PORT_LINE" ]]; then
        PORT_VAL="${PORT_LINE#*=}"
        PORT_VAL="${PORT_VAL//[[:space:]]/}"
        PORT_VAL="${PORT_VAL//\"/}"
        [[ "$PORT_VAL" =~ ^[0-9]+$ ]] && PORT="$PORT_VAL"
    fi
fi
PORT="${PORT:-8080}"
echo "  [sigmoji] Port   : $PORT"

# ── Detect Python ─────────────────────────────────────────────────────────────
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null && "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    echo "  [sigmoji] ERROR: Python 3.10+ not found in PATH."
    echo "  Install from https://python.org or via your package manager."
    exit 1
fi
echo "  [sigmoji] Python : $($PYTHON_CMD --version)"
echo ""

# ── Check / free the port ─────────────────────────────────────────────────────
echo "  [sigmoji] Checking port $PORT..."
if command -v lsof &>/dev/null; then
    FOUND_PID=$(lsof -ti "tcp:$PORT" 2>/dev/null || true)
elif command -v fuser &>/dev/null; then
    FOUND_PID=$(fuser "${PORT}/tcp" 2>/dev/null || true)
else
    FOUND_PID=""
fi

if [[ -n "$FOUND_PID" ]]; then
    echo "  [sigmoji] WARNING: Port $PORT in use by PID $FOUND_PID — killing..."
    kill -9 $FOUND_PID 2>/dev/null || true
    sleep 1
    echo "  [sigmoji] OK: Port $PORT freed."
else
    echo "  [sigmoji] OK: Port $PORT is free."
fi
echo ""

# ── Virtual environment ───────────────────────────────────────────────────────
if [[ ! -f "venv/bin/activate" ]]; then
    echo "  [sigmoji] Creating virtual environment..."
    "$PYTHON_CMD" -m venv venv
    echo "  [sigmoji] OK: venv created."
fi

echo "  [sigmoji] Activating venv..."
# shellcheck source=/dev/null
source venv/bin/activate
echo "  [sigmoji] venv   : $(python --version)"

# ── Install / sync requirements ───────────────────────────────────────────────
echo ""
echo "  [sigmoji] Checking requirements..."
pip install -r requirements.txt -q --disable-pip-version-check
echo "  [sigmoji] OK: Dependencies up to date."

# ── Token check (non-fatal warning) ──────────────────────────────────────────
echo ""
TOKEN_VAL=""
if [[ -f ".env" ]]; then
    TOKEN_LINE=$(grep -E '^\s*DISCORD_TOKEN\s*=' .env 2>/dev/null | head -1 || true)
    if [[ -n "$TOKEN_LINE" ]]; then
        TOKEN_VAL="${TOKEN_LINE#*=}"
        TOKEN_VAL="${TOKEN_VAL//[[:space:]]/}"
        TOKEN_VAL="${TOKEN_VAL//\"/}"
    fi
fi

if [[ -z "$TOKEN_VAL" ]]; then
    echo "  [sigmoji] WARNING: DISCORD_TOKEN is not set in .env"
    echo "  [sigmoji]          Bot will start in local-only mode."
    echo "  [sigmoji]          Open http://localhost:$PORT/ for setup instructions."
elif [[ "$TOKEN_VAL" == "your_bot_token_here" ]]; then
    echo "  [sigmoji] WARNING: DISCORD_TOKEN still has the placeholder value."
    echo "  [sigmoji]          Bot will start in local-only mode."
    echo "  [sigmoji]          Open http://localhost:$PORT/ for setup instructions."
else
    echo "  [sigmoji] OK: Discord token found."
fi

# ── Launch ────────────────────────────────────────────────────────────────────
echo ""
echo "  [sigmoji] Starting bot  -->  http://localhost:$PORT/"
echo "  [sigmoji] Press Ctrl+C to stop."
echo ""

python bot.py
