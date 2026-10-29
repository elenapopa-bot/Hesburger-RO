#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
chmod +x .cursor/start.sh .cursor/install.sh 2>/dev/null || true
python3 -m py_compile scripts/hesburger_ro_update.py
