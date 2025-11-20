# Battery Monitoring

## Overview
Exposes a `/battery-status` command for Termux users to check device battery metrics without leaving Telegram.

## Key Files & Components
- `utils/command_handlers.py`: `handle_battery_status_command()` executes `termux-battery-status` and formats the reply.
- `extract-compressed-files.py`: routes `/battery-status` messages to the handler when received from the authorized user.

## Process Flow
1. User sends `/battery-status`.
2. Handler checks for `termux-battery-status` binary; if present, runs it and parses JSON output (percentage, plugged status, temp, health).
3. Reply is sent with formatted metrics; errors are reported to the user if parsing/execution fails.

## Edge Cases & Safeguards
- If `termux-battery-status` is missing (non-Termux or not installed), the bot replies with a clear error instead of crashing.
- Command is protected by sender validation; unauthorized users get no response.
- Timeout on subprocess (10s) prevents hangs if the Termux API stalls.

## Operational Notes
- Install `termux-api` package on Android to enable the command.
- For non-Termux environments, expect the feature to remain unavailable by design.
