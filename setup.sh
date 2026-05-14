#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  ResumeWing — One-time Setup (macOS / Linux)
#
#  Run this once after cloning the repo. It:
#    1. Verifies Python 3.10+ and Node 18+ are installed
#    2. Creates a clean Python venv and installs every backend dep
#    3. Installs every frontend dep with npm
#    4. Verifies the install actually worked (uvicorn + node_modules present)
#    5. Marks start.sh / stop.sh / run_digest.sh as executable
#
#  Then run ./start.sh to launch the app.
#
#  Usage:
#      bash setup.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/job-app-automation"
FRONTEND="$ROOT/frontend"

# Colours
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

OS="$(uname -s)"

clear
echo ""
echo -e "${BOLD}  ============================================================${RESET}"
echo -e "${BOLD}    ResumeWing — One-time Setup${RESET}"
echo -e "${BOLD}  ============================================================${RESET}"
echo ""

step() { echo -e "  ${CYAN}[$1]${RESET} $2"; }
ok()   { echo -e "        ${GREEN}OK${RESET} — $1"; echo ""; }
fail() { echo -e "\n  ${RED}ERROR:${RESET} $1\n"; exit 1; }


# ── [1/5] Python ──────────────────────────────────────────────────────────────
step "1/5" "Checking Python..."

if ! command -v python3 &>/dev/null; then
    echo ""
    echo -e "  ${RED}'python3' not found.${RESET}"
    echo ""
    if [[ "$OS" == "Darwin" ]]; then
        echo "  Install Python 3.10+ via Homebrew:"
        echo -e "      ${CYAN}brew install python@3.11${RESET}"
        echo "  Or download from: https://www.python.org/downloads/macos/"
    else
        echo "  Install Python on Debian / Ubuntu:"
        echo -e "      ${CYAN}sudo apt update && sudo apt install -y python3 python3-venv python3-pip python3-dev build-essential${RESET}"
        echo ""
        echo "  Other distros: install python3, python3-venv, and a C build toolchain."
    fi
    echo ""
    exit 1
fi

PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="$(python3 -c 'import sys; print(sys.version_info.major)')"
PY_MINOR="$(python3 -c 'import sys; print(sys.version_info.minor)')"

if [[ "$PY_MAJOR" -lt 3 ]] || { [[ "$PY_MAJOR" -eq 3 ]] && [[ "$PY_MINOR" -lt 10 ]]; }; then
    fail "Python 3.10+ required (found $PY_VERSION). Upgrade and re-run setup.sh."
fi

# On Linux, the venv module isn't always bundled — python3-venv is a separate apt package.
if [[ "$OS" == "Linux" ]] && ! python3 -c "import venv" &>/dev/null; then
    echo ""
    echo -e "  ${RED}python3-venv module missing.${RESET}"
    echo ""
    echo "  Fix:"
    echo -e "      ${CYAN}sudo apt install -y python3-venv python3-pip python3-dev build-essential${RESET}"
    echo ""
    exit 1
fi

ok "Python $PY_VERSION"


# ── [2/5] Node ────────────────────────────────────────────────────────────────
step "2/5" "Checking Node.js..."

if ! command -v node &>/dev/null; then
    echo ""
    echo -e "  ${RED}'node' not found.${RESET}"
    echo ""
    echo "  Install Node.js 18+ from: https://nodejs.org/"
    if [[ "$OS" == "Darwin" ]]; then
        echo -e "  Or via Homebrew:  ${CYAN}brew install node${RESET}"
    fi
    echo ""
    exit 1
fi

NODE_VERSION="$(node -v | sed 's/v//')"
NODE_MAJOR="$(echo "$NODE_VERSION" | cut -d. -f1)"

if [[ "$NODE_MAJOR" -lt 18 ]]; then
    fail "Node.js 18+ required (found v$NODE_VERSION). Upgrade and re-run setup.sh."
fi

ok "Node v$NODE_VERSION"


# ── [3/5] Create venv ─────────────────────────────────────────────────────────
step "3/5" "Creating Python virtual environment..."

cd "$BACKEND"

if [[ -d venv ]]; then
    echo "        Removing existing venv..."
    rm -rf venv
fi

python3 -m venv venv
ok "venv created at $BACKEND/venv"


# ── [4/5] Backend dependencies ────────────────────────────────────────────────
step "4/5" "Installing backend dependencies (2-3 minutes)..."
echo ""

# Use the venv's pip directly so we never rely on `source activate` working.
"$BACKEND/venv/bin/python" -m pip install --upgrade pip --quiet
"$BACKEND/venv/bin/pip" install -r requirements.txt

if [[ ! -f "$BACKEND/venv/bin/uvicorn" ]]; then
    echo ""
    echo -e "  ${RED}uvicorn did not install. Check the pip output above for errors.${RESET}"
    echo ""
    echo "  Common fixes:"
    if [[ "$OS" == "Darwin" ]]; then
        echo "    macOS: install Xcode command-line tools, then re-run setup.sh:"
        echo -e "      ${CYAN}xcode-select --install${RESET}"
    else
        echo "    Linux: install build tools, then re-run setup.sh:"
        echo -e "      ${CYAN}sudo apt install -y build-essential python3-dev${RESET}"
    fi
    echo ""
    exit 1
fi

ok "uvicorn + all backend deps installed"


# ── [5/5] Frontend dependencies ───────────────────────────────────────────────
step "5/5" "Installing frontend dependencies (1-2 minutes)..."
echo ""

cd "$FRONTEND"
npm install

if [[ ! -d node_modules ]]; then
    fail "npm install ran but node_modules is missing. Check the output above."
fi

ok "node_modules installed"


# ── Make scripts executable ───────────────────────────────────────────────────
cd "$ROOT"
chmod +x start.sh stop.sh 2>/dev/null || true
chmod +x job-app-automation/run_digest.sh 2>/dev/null || true


# ── Success ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}  ============================================================${RESET}"
echo -e "${BOLD}    Setup complete!${RESET}"
echo -e "${BOLD}  ============================================================${RESET}"
echo ""
echo -e "    To start ResumeWing, run:"
echo -e "        ${CYAN}./start.sh${RESET}"
echo ""
echo -e "    Then open  ${CYAN}http://localhost:3000${RESET}  in your browser."
echo ""
echo "    Optional — load the browser extension once:"
echo "        1. Open  chrome://extensions  (or edge://extensions)"
echo "        2. Toggle 'Developer mode' on"
echo "        3. Click 'Load unpacked' → select the  extension/  folder"
echo ""
echo -e "${BOLD}  ============================================================${RESET}"
echo ""
