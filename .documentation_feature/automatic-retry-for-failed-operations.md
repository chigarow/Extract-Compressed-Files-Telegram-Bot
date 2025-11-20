# Automatic Retry for Failed Operations

## Overview
Failed downloads/uploads caused by network issues or FloodWaits are saved and retried on a schedule, reducing manual intervention.

## Key Files & Components
- `utils/cache_manager.py`: `FailedOperationsManager` persists failures to `data/failed_operations.json`.
- `utils/queue_manager.py`: retry queue logic uses exponential backoff and attempts up to `MAX_RETRY_ATTEMPTS`.
- `extract-compressed-files.py`: populates failed operations list and requeues tasks periodically.

## Process Flow
1. When an operation raises a recoverable error, it is added to the failed operations list with metadata.
2. Background scheduler wakes every 30 minutes to push pending failures back into processing queues.
3. Successful retry removes the entry; repeated failures remain for further attempts until limits are reached.

## Edge Cases & Safeguards
- Malformed entries are skipped with warnings to avoid crashing the retry loop.
- Persistent failures beyond max attempts stay in `failed_operations.json` for manual review instead of looping forever.
- Retry scheduling coexists with FloodWait-specific sleeps to avoid compounding delays.

## Operational Notes
- Inspect `data/failed_operations.json` to triage stubborn items (e.g., deleted files, invalid links).
- Adjust retry intervals and limits in `utils/constants.py` if you prefer more aggressive or conservative retries.
