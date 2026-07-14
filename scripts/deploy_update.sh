#!/usr/bin/env bash
# Pull latest Case PM from git and restart the app so remote browsers get new HTML/JS.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Pulling latest from origin/main..."
git fetch origin main
git checkout main
git pull origin main

BUILD="$(git rev-parse --short HEAD)"
export CASEPM_ASSET_VERSION="$BUILD"
echo "==> Build: $BUILD"

stop_casepm() {
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet casepm 2>/dev/null; then
    echo "==> Restarting casepm service..."
    sudo systemctl restart casepm
    return 0
  fi
  if [ -f /tmp/casepm.pid ]; then
    echo "==> Stopping prior process (pid file)..."
    kill "$(cat /tmp/casepm.pid)" 2>/dev/null || true
    sleep 1
  fi
  if pgrep -f "python.*app.py" >/dev/null 2>&1; then
    echo "==> Stopping running Case PM (python app.py)..."
    pkill -f "python.*app.py" 2>/dev/null || true
    sleep 2
  fi
  return 1
}

if stop_casepm; then
  :
elif ! pgrep -f "python.*app.py" >/dev/null 2>&1; then
  echo "==> Starting app (background)..."
  export CASEPM_ASSET_VERSION="$BUILD"
  nohup python3 app.py > /tmp/casepm.log 2>&1 &
  echo $! > /tmp/casepm.pid
else
  echo "==> WARNING: Case PM may still be running. Stop it manually, then re-run this script."
fi

echo "==> Done. On every remote PC: hard-refresh (Ctrl+Shift+R)."
echo "    Footer must show: Case PM · build $BUILD"
echo "    Pay Apps / Budget pages have a green Save button in the bottom bar."
