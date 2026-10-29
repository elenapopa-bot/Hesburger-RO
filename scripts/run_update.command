#!/bin/bash
# Double-click this file in Finder (Mac) to refresh the Hesburger RO report.
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Hesburger RO report update ==="
echo ""
echo "1) Chrome must be open and logged in to Looker (bolt.cloud.looker.com)."
echo "2) Press Enter here when Looker works in Chrome."
read -r _

ENV_FILE="$HOME/.hesburger_ro_env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo ""
  echo "ERROR: Missing $ENV_FILE (GITHUB_TOKEN)."
  echo "Press Enter to close."
  read -r _
  exit 1
fi
# POSIX `.` works when `source` is missing (sh/dash); script also reads env file itself.
# shellcheck disable=SC1090
. "$ENV_FILE"

if [[ -f "$HOME/scripts/hesburger_ro_update.py" ]]; then
  PY="$HOME/scripts/hesburger_ro_update.py"
elif [[ -f "$(dirname "$0")/hesburger_ro_update.py" ]]; then
  PY="$(dirname "$0")/hesburger_ro_update.py"
else
  echo ""
  echo "ERROR: hesburger_ro_update.py not found in ~/scripts/ or this folder."
  echo "Download from: https://github.com/elenapopa-bot/Hesburger-RO/tree/main/scripts"
  echo "Press Enter to close."
  read -r _
  exit 1
fi

echo ""
echo "Running: python3 $PY"
echo ""
python3 "$PY" || {
  echo ""
  echo "FAILED — see ~/scripts/hesburger_ro.log"
  echo "Press Enter to close."
  read -r _
  exit 1
}

echo ""
echo "Done. Report: https://elenapopa-bot.github.io/Hesburger-RO/"
echo "Press Enter to close."
read -r _
