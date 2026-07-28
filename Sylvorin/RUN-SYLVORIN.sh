#!/usr/bin/env bash
# Sylvorin — run in browser (dev mode)
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -d node_modules ]]; then npm install; fi
echo "Starting Sylvorin at http://localhost:5173"
npm run dev
