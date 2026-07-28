#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "================================================"
echo "  Case PM Desktop App"
echo "  (native window — no browser tab required)"
echo "================================================"
echo

PY=""
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "ERROR: Python 3 is not installed or not in PATH."
  exit 1
fi

if [[ ! -x venv/bin/python ]]; then
  echo "Creating virtual environment..."
  "$PY" -m venv venv
fi

PY=venv/bin/python
"$PY" -m pip install --upgrade pip --quiet
echo "Installing Case PM + desktop window packages..."
"$PY" -m pip install -r requirements-desktop.txt --quiet

export CASEPM_HOST=127.0.0.1
export CASEPM_PORT=5000
export CASEPM_REMOTE=0
export CASEPM_DEBUG=0
export CASEPM_DESKTOP=1

echo
echo "Launching Case PM in a desktop window..."
echo "Close the window to exit. Data stays in instance/case_pm.db on this computer."
echo

exec "$PY" desktop_launcher.py
