# Sequential Processing

## Overview
Default processing model runs one file at a time (download → extract/compress → upload → cleanup) to minimize RAM/CPU usage on Termux and avoid race conditions.

## Key Files & Components
- `utils/constants.py`: sets `DOWNLOAD_SEMAPHORE_LIMIT` and `UPLOAD_SEMAPHORE_LIMIT` to 1.
- `utils/queue_manager.py`: enforces these semaphores around download/upload tasks and coordinates cleanup registries.
- `extract-compressed-files.py`: uses a global `semaphore` to gate message processing and queue submissions.

## Process Flow
1. Incoming tasks enter download queue; semaphore ensures only one download runs at a time.
2. After extraction and prep, uploads are enqueued and also processed singly.
3. When upload completes, cleanup triggers and the next queued item starts.
4. State is persisted periodically so sequential position can be recovered after crashes.

## Edge Cases & Safeguards
- Prevents overlapping extraction folders that could exceed storage on small devices.
- If config overrides concurrency, queues still guard against flooding Telethon by respecting semaphores.
- Sequential mode cooperates with WebDAV sequentialization when enabled.

## Operational Notes
- Change `DOWNLOAD_SEMAPHORE_LIMIT`/`UPLOAD_SEMAPHORE_LIMIT` in `utils/constants.py` for higher throughput; monitor rate limits and memory before increasing.
