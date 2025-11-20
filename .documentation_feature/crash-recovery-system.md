# Crash Recovery System

## Overview
Continuously snapshots in-progress work to disk so the bot can resume after crashes or restarts without losing state.

## Key Files & Components
- `utils/cache_manager.py`: `ProcessManager` persists processing snapshot to `data/current_process.json` every minute.
- `extract-compressed-files.py`: initializes managers and updates current processing state as tasks progress.
- `data/current_process.json`: on-disk record of active archive, stage, and counters.

## Process Flow
1. When a task starts, metadata is recorded in `ProcessManager` (archive name, paths, progress markers).
2. Background timer writes the snapshot to disk at regular intervals.
3. On restart, managers load `current_process.json` to restore queue context and continue where left off when possible.

## Edge Cases & Safeguards
- Serialization normalizes Telethon/datetime objects to JSON-safe forms to avoid crashes on reload.
- If snapshot file is corrupted, warnings are logged and a fresh state is initialized to keep the bot running.
- Snapshot frequency balances safety with I/O overhead; default is lightweight for Termux storage.

## Operational Notes
- Keep `data/` persistent across device restarts (e.g., avoid tmpfs) to benefit from recovery.
- Pair with automatic retry feature for robust handling of transient network errors after a crash.
