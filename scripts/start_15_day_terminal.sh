#!/bin/zsh
set -euo pipefail

PROJECT_ROOT="${0:A:h}/.."
cd "$PROJECT_ROOT"

export PATH="/Users/shauryakitavat/.pyenv/shims:$PATH"

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
  --capital 2500000
  --lot-size 65
  --max-pos 16
  --min-mscore 1.2
  --tp 26
  --sl 13
  --interval 10
  --duration-hours 6
  --multi-expiry
  --no-eod-squareoff
)

if command -v caffeinate >/dev/null 2>&1; then
  caffeinate -dimsu python -u "${TRADER_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"
else
  python -u "${TRADER_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"
fi
