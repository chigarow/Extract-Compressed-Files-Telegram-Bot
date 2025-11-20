# Direct Media Upload

## Overview
Allows users to send images or videos directly (outside of archives). The bot forwards them to the target account as native media, keeping them in Telegram's Media tab rather than as documents.

## Key Files & Components
- `extract-compressed-files.py`: event handlers route incoming media messages into the upload queue, tagging type and source for captions.
- `utils/queue_manager.py`: builds upload tasks with `media_type` and handles grouped album logic for direct uploads.
- `utils/telegram_operations.py`: performs actual uploads with correct media attributes and captions.

## Process Flow
1. Incoming message with photo/video is detected by extension or message type and bypasses extraction.
2. File is downloaded to temp path and queued as an upload task with metadata (source caption, file name, is_grouped flag).
3. `QueueManager` batches items (photos vs videos) up to Telegram album limits, then `TelegramOperations` sends them to `TARGET_USERNAME`.
4. After upload, temp files are cleaned up to conserve space.

## Edge Cases & Safeguards
- Non-media files are filtered out by extension/MIME guard before enqueueing to prevent document-only uploads.
- Upload failures (e.g., FloodWait, network errors) are pushed to retry/fail queues for subsequent attempts.
- Albums respect Telegram's 10-item cap; overflow triggers new batches automatically.

## Operational Notes
- Captions default to the source filename/archive name for traceability.
- Processing remains sequential with download→upload→cleanup to minimize RAM usage on Termux.
