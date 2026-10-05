#!/bin/zsh
set -euo pipefail

PROJECT_ROOT="${0:A:h}/.."
cd "$PROJECT_ROOT"

SESSION_DATE="$(date +%Y%m%d)"
LOG_DIR="$PROJECT_ROOT/outputs/terminal_sessions"
LOG_FILE="$LOG_DIR/live_terminal_${SESSION_DATE}.log"
mkdir -p "$LOG_DIR"

echo "Starting NIFTY paper-trading session for ${SESSION_DATE}."
echo "Terminal log: ${LOG_FILE}"
echo "Press Ctrl+C to stop safely and export the session report."

type python >/dev/null 2>&1 || {
  echo "Python was not found on PATH. Activate the project environment first."
  exit 1
}

TRADER_ARGS=(
  scripts/live_paper_trader.py
  --new-session \
  --max-pos 8 \
  --min-mscore 2.0 \
  --tp 20 \
  --sl 12 \
  --interval 10 \
  --duration-hours 6
)

if command -v caffeinate >/dev/null 2>&1; then
  caffeinate -dimsu python "${TRADER_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"
else
  python "${TRADER_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"
fi
