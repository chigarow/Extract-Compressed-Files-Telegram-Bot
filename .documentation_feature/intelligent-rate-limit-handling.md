# Intelligent Rate Limit Handling

## Overview
Handles Telegram `FloodWaitError` and related rate limits automatically by pausing, preserving files, and retrying until success without data loss.

## Key Files & Components
- `extract-compressed-files.py`: wraps send/download operations in try/except for `FloodWaitError`, logging and scheduling retries.
- `utils/queue_manager.py`: retry queue with exponential backoff timers; manages in-flight task locking to avoid duplicate work.
- `utils/constants.py`: `MAX_RETRY_ATTEMPTS` and `RETRY_BASE_INTERVAL` configure retry behavior.

## Process Flow
1. On FloodWait during download or upload, handler logs wait time and schedules a retry task after the specified delay.
2. Files are kept on disk (`cleanup` deferred) so retries have intact inputs.
3. Retry queue re-enqueues the operation with incremental backoff until it completes or exhausts attempts.
4. Success triggers normal cleanup and queue advancement; persistent failures end up in failed operations for manual review.

## Edge Cases & Safeguards
- Album batching reduces API calls by ~97-99%, reducing FloodWait frequency preemptively.
- Concurrent queue limits (set to 1 by default) further lower rate pressure for Termux/low-resource setups.
- Flood waits are respected exactly as returned by Telegram; no busy-looping.

## Operational Notes
- Review `data/failed_operations.json` for items that exhausted retries; they can be retried manually or cleaned up.
- Adjust semaphore limits in `utils/constants.py` if you intentionally want more concurrency and can tolerate higher wait risk.
