# Automatic File Cleanup

## Overview
Provides commands to remove old files and orphaned directories to reclaim disk space safely after processing.

## Key Files & Components
- `utils/command_handlers.py`: `/cleanup`, `/cleanup-confirm`, and `/cleanup-orphans` handlers implement cleanup workflows and confirmations.
- `CLEANUP_GUIDE.md`: user-facing instructions and safety notes.
- `utils/constants.py`: defines protected directories like `RECOVERY_DIR` and `QUARANTINE_DIR` that are excluded from destructive actions.

## Process Flow
1. User triggers `/cleanup` to get a summary of deletable items and confirmation prompt.
2. `/cleanup-confirm` performs deletion of eligible files/directories while skipping protected lists.
3. `/cleanup-orphans` targets stray extraction folders or temp files not tracked by registries.
4. Results are reported back to the user; errors are logged for manual follow-up.

## Edge Cases & Safeguards
- Confirmation step prevents accidental deletion; cleanup aborts without explicit `/cleanup-confirm`.
- Protected lists prevent removal of active session, recovery, and quarantine assets.
- Exceptions during deletion are caught and surfaced without crashing the bot.

## Operational Notes
- Run cleanup periodically on Termux to prevent storage exhaustion.
- Combine with monitoring outputs (`monitor_system.py`) to decide when to clean.
