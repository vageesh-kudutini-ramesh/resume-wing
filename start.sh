#!/usr/bin/env bash
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  ResumeWing â€” Start All Services (macOS / Linux)
#
#  What this script does:
#    1. Validates the Python virtual environment and Node modules
#    2. Starts the FastAPI backend  on http://localhost:8000
#    3. Waits 15 s for AI models (sentence-transformers / KeyBERT) to warm up
#    4. Starts the Next.js frontend on http://localhost:3000
#    5. Opens both services in new terminal windows when possible,
#       or runs them in the background with log files as fallback
#
#  To stop everything:  ./stop.sh
#
#  Usage:
#    chmod +x start.sh stop.sh   # (first time only â€” make scripts executable)
#    ./start.sh
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

set -euo pipefail

# â”€â”€ Resolve project root (the folder this script lives in) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/job-app-automation"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/venv"
LOGS="$ROOT/.logs"
PID_FILE="$ROOT/.resumewing.pids"

# Colours
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

clear
echo ""
echo -e "${BOLD}  ============================================================${RESET}"
echo -e "${BOLD}    ResumeWing  |  Starting all services...${RESET}"
echo -e "${BOLD}  ============================================================${RESET}"
echo ""


# â”€â”€ Helper: print a labelled step â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
step() { echo -e "  ${CYAN}[$1]${RESET} $2"; }
ok()   { echo -e "        ${GREEN}OK${RESET} â€” $1"; echo ""; }
fail() { echo -e "\n  ${RED}ERROR:${RESET} $1\n"; exit 1; }


# â”€â”€ Detect OS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
OS="$(uname -s)"   # Darwin = macOS, Linux = Linux


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# PRE-FLIGHT CHECKS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

step "1/4" "Checking Python virtual environment..."
if [[ ! -f "$VENV/bin/uvicorn" ]]; then
    echo ""
    echo -e "  ${RED}Virtual environment not found or incomplete.${RESET}"
    echo ""
    echo "  First-time setup - run this once from the repo root:"
    echo -e "      ${CYAN}bash setup.sh${RESET}"
    echo ""
    echo "  setup.sh checks your Python/Node versions, creates the venv,"
    echo "  installs every backend and frontend dependency, and verifies"
    echo "  the install worked."
    echo ""
    exit 1
fi
ok "venv found at $VENV"


step "2/4" "Checking Node modules..."
if [[ ! -d "$FRONTEND/node_modules" ]]; then
    echo ""
    echo -e "  ${RED}Frontend dependencies not installed.${RESET}"
    echo ""
    echo "  First-time setup - run this once from the repo root:"
    echo -e "      ${CYAN}bash setup.sh${RESET}"
    echo ""
    exit 1
fi
ok "node_modules found"


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TERMINAL LAUNCHER
# Opens a command in a new terminal window on macOS or Linux.
# Falls back to background process + log file if no terminal is found.
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

WINDOW_MODE=""   # "macos" | "gnome" | "konsole" | "xterm" | "kitty" | "background"

detect_terminal() {
    if [[ "$OS" == "Darwin" ]]; then
        WINDOW_MODE="macos"
    elif command -v gnome-terminal &>/dev/null; then
        WINDOW_MODE="gnome"
    elif command -v konsole &>/dev/null; then
        WINDOW_MODE="konsole"
    elif command -v kitty &>/dev/null; then
        WINDOW_MODE="kitty"
    elif command -v xterm &>/dev/null; then
        WINDOW_MODE="xterm"
    else
        WINDOW_MODE="background"
    fi
}

# open_terminal <window-title> <log-file> <bash-command-string>
# Spawns the command in a new window (or background process).
# Returns the PID of the spawned process via $SPAWNED_PID.
open_terminal() {
    local title="$1"
    local logfile="$2"
    local cmd="$3"

    mkdir -p "$LOGS"

    case "$WINDOW_MODE" in

        macos)
            # AppleScript: open a new Terminal.app window running the command.
            # Falls back to iTerm2 if Terminal is not set as default.
            osascript > /dev/null 2>&1 <<APPLESCRIPT
tell application "Terminal"
    activate
    do script "$cmd"
    set custom title of front window to "$title"
end tell
APPLESCRIPT
            # We can't easily get the PID from an AppleScript-launched process;
            # stop.sh uses pkill on the process name instead.
            SPAWNED_PID=""
            ;;

        gnome)
            gnome-terminal --title="$title" -- bash -c "$cmd; exec bash" &
            SPAWNED_PID=$!
            ;;

        konsole)
            konsole --title "$title" -e bash -c "$cmd; exec bash" &
            SPAWNED_PID=$!
            ;;

        kitty)
            kitty --title "$title" bash -c "$cmd; exec bash" &
            SPAWNED_PID=$!
            ;;

        xterm)
            xterm -title "$title" -e bash -c "$cmd; exec bash" &
            SPAWNED_PID=$!
            ;;

        background)
            # No GUI terminal available (headless / SSH / WSL without display).
            # Run in background and redirect output to a log file.
            bash -c "$cmd" > "$logfile" 2>&1 &
            SPAWNED_PID=$!
            ;;
    esac
}

detect_terminal
echo -e "  ${YELLOW}Terminal mode: ${WINDOW_MODE}${RESET}"
echo ""


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# CLEAR OLD PID FILE
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
> "$PID_FILE"


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# START BACKEND
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
step "3/4" "Starting FastAPI backend (http://localhost:8000)..."

BACKEND_CMD="cd '$BACKEND' && source '$VENV/bin/activate' && \
printf '\n  ResumeWing Backend â€” FastAPI\n  http://localhost:8000\n  (First start: AI models load in 10-20 s)\n\n' && \
uvicorn main:app --host 127.0.0.1 --port 8000 --reload"

open_terminal "ResumeWing â€” Backend (8000)" "$LOGS/backend.log" "$BACKEND_CMD"
[[ -n "$SPAWNED_PID" ]] && echo "backend $SPAWNED_PID" >> "$PID_FILE"

echo "        Backend window opened."
echo ""


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# WAIT FOR AI MODELS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
echo -e "  ${YELLOW}Waiting 15 s for AI models to initialise...${RESET}"
echo "        (sentence-transformers + KeyBERT load on first request)"
echo ""
for i in $(seq 15 -1 1); do
    printf "\r          %2d s remaining..." "$i"
    sleep 1
done
printf "\r          Done.                  \n\n"


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# START FRONTEND
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
step "4/4" "Starting Next.js frontend (http://localhost:3000)..."

FRONTEND_CMD="cd '$FRONTEND' && \
printf '\n  ResumeWing Frontend â€” Next.js\n  http://localhost:3000\n\n' && \
npm run dev"

open_terminal "ResumeWing â€” Frontend (3000)" "$LOGS/frontend.log" "$FRONTEND_CMD"
[[ -n "$SPAWNED_PID" ]] && echo "frontend $SPAWNED_PID" >> "$PID_FILE"

echo "        Frontend window opened."
echo ""


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# BACKGROUND MODE â€” stream log files so the user sees output
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
if [[ "$WINDOW_MODE" == "background" ]]; then
    echo -e "  ${YELLOW}NOTE: No GUI terminal detected.${RESET}"
    echo "  Both services are running in the background."
    echo "  Logs are being written to:"
    echo "      $LOGS/backend.log"
    echo "      $LOGS/frontend.log"
    echo ""
    echo "  Tail both logs in this window? (Ctrl+C to detach â€” services keep running)"
    read -r -p "  Press Enter to tail logs, or Ctrl+C to exit: "
    echo ""
    tail -f "$LOGS/backend.log" "$LOGS/frontend.log"
fi


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# READY SUMMARY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
echo ""
echo -e "${BOLD}  ============================================================${RESET}"
echo -e "${BOLD}    ResumeWing is up!${RESET}"
echo -e "${BOLD}  ============================================================${RESET}"
echo ""
echo -e "    Dashboard   :  ${CYAN}http://localhost:3000${RESET}"
echo -e "    Backend API :  ${CYAN}http://localhost:8000${RESET}"
echo -e "    API docs    :  ${CYAN}http://localhost:8000/docs${RESET}"
echo ""
echo "    Chrome Extension (one-time setup):"
echo "      1. Open  chrome://extensions"
echo "      2. Enable 'Developer mode'  (top-right toggle)"
echo "      3. Click 'Load unpacked'"
echo "      4. Select the  extension/  folder inside this project"
echo ""
echo "    To stop all services:  ./stop.sh"
echo ""
echo -e "${BOLD}  ============================================================${RESET}"
echo ""
