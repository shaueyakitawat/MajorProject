#!/bin/zsh
# scripts/attach_terminal.sh
# Streams the active live paper trading Bloomberg-style ASCII dashboard to your interactive terminal.

PROJECT_ROOT="${0:A:h}/.."
cd "$PROJECT_ROOT"

SESSION_DATE="$(date +%Y%m%d)"
LOG_FILE="$PROJECT_ROOT/outputs/terminal_sessions/live_terminal_${SESSION_DATE}.log"

if [[ ! -f "$LOG_FILE" ]]; then
    echo "⚠️ No live log found for today (${SESSION_DATE}) at: $LOG_FILE"
    echo "Check if the engine is running with: ps aux | grep live_paper_trader"
    exit 1
fi

echo "Connecting to live terminal session for ${SESSION_DATE}..."
tail -n 65 -f "$LOG_FILE"
