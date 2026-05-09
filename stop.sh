#!/usr/bin/env bash
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  ResumeWing â€” Stop All Services (macOS / Linux)
#
#  Strategy (two-layer for reliability):
#    1. Read saved PIDs from .resumewing.pids and kill those processes
#    2. Fall back to pkill on process name (catches macOS Terminal-launched procs)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT/.resumewing.pids"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; RESET='\033[0m'

echo ""
echo -e "${BOLD}  ============================================================${RESET}"
echo -e "${BOLD}    ResumeWing  |  Stopping all services...${RESET}"
echo -e "${BOLD}  ============================================================${RESET}"
echo ""

killed_any=false

# â”€â”€ Layer 1: Kill by saved PID â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if [[ -f "$PID_FILE" ]]; then
    echo "  Stopping by saved PIDs..."
    while IFS=" " read -r service pid; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null && echo -e "        ${GREEN}Stopped${RESET} $service (PID $pid)" || true
            killed_any=true
        fi
    done < "$PID_FILE"
    rm -f "$PID_FILE"
    echo ""
fi

# â”€â”€ Layer 2: pkill by process name (catches Terminal.app-launched procs) â”€â”€â”€â”€â”€â”€
echo "  Stopping uvicorn (FastAPI backend)..."
if pkill -f "uvicorn main:app" 2>/dev/null; then
    echo -e "        ${GREEN}Stopped${RESET}"
    killed_any=true
else
    echo "        Not running or already stopped."
fi
echo ""

echo "  Stopping Next.js frontend (node / next)..."
if pkill -f "next dev" 2>/dev/null || pkill -f "next-server" 2>/dev/null; then
    echo -e "        ${GREEN}Stopped${RESET}"
    killed_any=true
else
    echo "        Not running or already stopped."
fi
echo ""

# â”€â”€ Summary â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo -e "${BOLD}  ============================================================${RESET}"
if $killed_any; then
    echo -e "${BOLD}    All ResumeWing services stopped.${RESET}"
else
    echo -e "    ${YELLOW}No running ResumeWing services were found.${RESET}"
fi
echo -e "${BOLD}  ============================================================${RESET}"
echo ""
