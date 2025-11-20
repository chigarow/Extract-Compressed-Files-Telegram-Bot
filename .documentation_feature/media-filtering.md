# Media Filtering

## Overview
Ensures only supported media types are processed and forwarded, dropping unsupported files early to save bandwidth and avoid Telegram errors.

## Key Files & Components
- `utils/constants.py`: defines `PHOTO_EXTENSIONS`, `VIDEO_EXTENSIONS`, and combined `MEDIA_EXTENSIONS` used for validation.
- `extract-compressed-files.py`: filters extracted file lists against `MEDIA_EXTENSIONS` before queueing uploads.
- `utils/queue_manager.py`: uses media type tags to batch images vs videos separately for albums.

## Process Flow
1. After extraction or direct download, files are enumerated and filtered by extension.
2. Accepted media are normalized into upload tasks; non-media items are skipped with log entries for traceability.
3. Upload tasks carry `media_type` to determine album grouping and further processing (video conversion, image compression).

## Edge Cases & Safeguards
- GIFs are intentionally excluded from photos to avoid Telegram document behavior.
- Duplicate extensions in unusual case (e.g., `.JPG`) are handled case-insensitively.
- Unknown extensions are ignored rather than causing failures; user can resend supported formats if needed.

## Operational Notes
- Extend accepted formats by editing `PHOTO_EXTENSIONS`/`VIDEO_EXTENSIONS` in `utils/constants.py` and restarting.
