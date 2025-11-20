# Grouped Media Uploads

## Overview
Uploads images and videos as grouped Telegram albums to cut API calls (batched 10-at-a-time) and keep archive context in captions.

## Key Files & Components
- `utils/queue_manager.py`: `StreamingBatchBuilder` and album batching logic respect `TELEGRAM_ALBUM_MAX_FILES` (10) and separate image/video buffers.
- `extract-compressed-files.py`: marks tasks with `is_grouped` and passes archive names for captions.
- `utils/telegram_operations.py`: executes grouped uploads with correct media attributes.

## Process Flow
1. After extraction, media entries are queued with source archive name and media type.
2. `QueueManager` buffers items until reaching 10 per type or until flush is called, then creates a grouped upload task.
3. Upload task sends album captioned like `<archive> - Images Batch N`, minimizing FloodWait exposure.
4. Once batches finish, cleanup registries are notified to remove extracted folders and source archives.

## Edge Cases & Safeguards
- Separates image and video queues to avoid mixed albums that Telegram disallows.
- Flush ensures trailing items (<10) still send at end of extraction or shutdown.
- Upload errors (FloodWait, network) are retried via retry queue; cleanup waits until all batches succeed.

## Operational Notes
- Batch naming is customizable in `StreamingBatchBuilder._dispatch()` if different captions are desired.
- Grouped mode is default; set `is_grouped=False` when adding tasks to force single uploads (not recommended).
