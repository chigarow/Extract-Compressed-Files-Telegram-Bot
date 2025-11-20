# Proper Video Attributes

## Overview
Ensures uploaded videos display correct duration, thumbnails, and metadata in Telegram to avoid black thumbnails or 00:00 durations.

## Key Files & Components
- `utils/media_processing.py`: uses `ffprobe` to validate metadata and `compress_video_for_telegram()` to normalize streams and timestamps.
- `utils/telegram_operations.py`: `get_video_attributes_and_thumbnail()` extracts duration and thumbnail during upload preparation.
- `extract-compressed-files.py`: integrates attribute extraction results into upload tasks.

## Process Flow
1. Video file is analyzed with `ffprobe` to gather streams and duration; missing/invalid results trigger conversion.
2. Compression step applies flags (`-movflags +faststart`, timestamp fixes, even dimensions) to correct playback issues.
3. Upload task includes generated thumbnail and duration metadata so Telethon sends it as a proper video, not a generic document.
4. Telegram displays accurate duration and preview in the Media tab after upload.

## Edge Cases & Safeguards
- If `ffprobe` is unavailable, the system assumes attributes may be incomplete and may still convert based on settings.
- For videos already Telegram-compatible, metadata is still preserved by copying and normalized to avoid hidden edge issues.
- Thumbnail extraction errors are logged; upload continues without thumbnail, letting Telegram auto-generate if possible.

## Operational Notes
- Recompression uses `libx264`/`aac` defaults; adjust in `utils/media_processing.py` if stricter quality targets are needed.
