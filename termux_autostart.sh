#!/data/data/com.termux/files/usr/bin/bash
# Simple Termux autostart wrapper for the extractor bot.
# Use with Termux:Boot or cron to relaunch the bot after crashes/reboots.

set -e

PROJECT_DIR="/data/data/com.termux/files/home/Extract-Compressed-Files-Telegram-Bot"
VENV_DIR="$PROJECT_DIR/venv"
SCRIPT_PATH="$PROJECT_DIR/extract-compressed-files.py"
LOG_DIR="$PROJECT_DIR/data/logs"
LOG_FILE="$LOG_DIR/termux-autostart.log"

mkdir -p "$LOG_DIR"

# Keep the device awake during startup; ignore failures if termux-api missing
termux-wake-lock >/dev/null 2>&1 || true

# Exit early if already running
if pgrep -f "extract-compressed-files.py" >/dev/null 2>&1; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') already running" >> "$LOG_FILE"
  exit 0
fi

cd "$PROJECT_DIR" || exit 1

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') virtualenv missing at $VENV_DIR" >> "$LOG_FILE"
  exit 1
fi

source "$VENV_DIR/bin/activate"

echo "$(date '+%Y-%m-%d %H:%M:%S') restarting extractor bot" >> "$LOG_FILE"
nohup python "$SCRIPT_PATH" >> "$LOG_FILE" 2>&1 &
