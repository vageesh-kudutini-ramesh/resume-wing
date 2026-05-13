#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  ResumeWing — Run Daily Digest Email (macOS / Linux)
#
#  Wrapper invoked by cron, launchd, or systemd timers. Activates the project
#  venv and runs digest_email.py, propagating the exit code so the scheduler
#  reports success / failure correctly.
#
#  Quick install:
#    chmod +x run_digest.sh
#
#  macOS — register via launchd (preferred; wakes from sleep):
#    See "Daily digest email" section of the project README.
#
#  Linux — register via systemd timer (preferred; Persistent=true catches
#          missed runs):
#    See "Daily digest email" section of the project README.
#
#  Either OS — fallback via crontab:
#    crontab -e
#    0 8 * * *  /full/path/to/job-app-automation/run_digest.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# Resolve the directory this script lives in, regardless of where it's invoked.
ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

VENV_PY="${ROOT}/venv/bin/python"

if [[ ! -x "${VENV_PY}" ]]; then
    echo "ERROR: Python venv not found at ${VENV_PY}." >&2
    echo "Run:   cd job-app-automation && python3 -m venv venv && venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

cd "${ROOT}"
exec "${VENV_PY}" digest_email.py
