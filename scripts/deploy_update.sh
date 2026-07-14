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

if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet casepm 2>/dev/null; then
  echo "==> Restarting casepm service..."
  sudo systemctl restart casepm
elif [ -f /tmp/casepm.pid ]; then
  echo "==> Stopping prior process..."
  kill "$(cat /tmp/casepm.pid)" 2>/dev/null || true
  sleep 1
fi

if ! pgrep -f "python.*app.py" >/dev/null 2>&1; then
  echo "==> Starting app (background)..."
  nohup python3 app.py > /tmp/casepm.log 2>&1 &
  echo $! > /tmp/casepm.pid
fi

echo "==> Done. Remote users: hard-refresh the browser (Ctrl+Shift+R)."
echo "    Footer should show: Case PM · build $BUILD"
