# Media Tab Support

## Overview
Uploads photos and videos through Telethon media APIs so they appear under the chat's Media tab instead of as generic documents.

## Key Files & Components
- `utils/telegram_operations.py`: wraps Telethon send methods to choose correct input types (photo/video) and attach attributes.
- `utils/queue_manager.py`: separates `media_type` for tasks to ensure the right uploader path is used.
- `extract-compressed-files.py`: orchestrates task creation with the proper flags (`is_grouped`, `media_type`).

## Process Flow
1. Filtered media files are tagged as `images` or `videos` before entering the upload queue.
2. Queue manager batches and dispatches them using photo/video uploads (not documents), preserving captions.
3. Telethon sends the items, which Telegram classifies as media and surfaces in the Media tab for easier browsing.

## Edge Cases & Safeguards
- Non-media extensions bypass this path and are ignored to avoid sending documents unintentionally.
- If Telegram rejects a media type (corrupt file), it is logged and moved to failed retries without blocking other uploads.

## Operational Notes
- Album and compression features piggyback on this flow; ensure `MEDIA_EXTENSIONS` remains accurate to keep uploads classified correctly.
