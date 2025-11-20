# Queue Monitoring

## Overview
Provides commands to inspect current download/upload queue state and in-progress tasks for operational visibility.

## Key Files & Components
- `utils/command_handlers.py`: `/status` and `/queue` command handlers assemble queue snapshots and uptime info.
- `utils/queue_manager.py`: exposes queue instances via `get_queue_manager()`/`get_processing_queue()` used in reports.
- `extract-compressed-files.py`: routes command messages to the appropriate handler functions.

## Process Flow
1. User sends `/status` or `/queue` from the authorized account.
2. Handler pulls queue lengths, current processing item, and uptime, formatting them into reply text.
3. Reply is sent to the user for quick diagnostics without accessing logs.

## Edge Cases & Safeguards
- Commands are protected by sender validation; unauthorized callers get silently ignored/logged.
- If queues are empty, replies clearly indicate idle state to avoid confusion.
- For long outputs, handlers keep messages concise to stay within Telegram limits.

## Operational Notes
- Additional command `/help` lists all available runtime controls; see command_handlers for current list.
