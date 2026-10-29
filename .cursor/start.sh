#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PORT=8080
if command -v ss >/dev/null 2>&1; then
  if ss -ltn | grep -q ":${PORT} "; then
    exit 0
  fi
elif command -v netstat >/dev/null 2>&1; then
  if netstat -ltn 2>/dev/null | grep -q ":${PORT} "; then
    exit 0
  fi
fi
exec python3 -m http.server "$PORT" --bind 127.0.0.1
