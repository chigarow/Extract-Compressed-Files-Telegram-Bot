# Automatic Image Compression

## Overview
Automatically compresses photos that exceed Telegram's 10MB photo limit by decreasing JPEG quality iteratively until the size fits, ensuring uploads never fail due to oversized images.

## Key Files & Components
- `utils/media_processing.py`: compression logic (Pillow-based) invoked when image size exceeds `TELEGRAM_PHOTO_SIZE_LIMIT`.
- `extract-compressed-files.py`: detects oversize images during prep and routes them through the compression helper before upload.
- `requirements.txt`: includes Pillow dependency required for this feature.

## Process Flow
1. Image file size is checked against 10MB threshold during upload preparation.
2. If too large, compression routine opens the image and reduces quality stepwise, writing to a temp path.
3. Compressed image replaces the original in the upload task; original is retained until upload succeeds for safety.
4. Upload proceeds as a normal photo, now within Telegram size limits.

## Edge Cases & Safeguards
- If Pillow is missing, the routine logs a warning and attempts upload; Telegram may reject oversize files.
- Compression loop stops once size is under limit or quality floor is reached; if still too large, the image remains and may fail, triggering retry/failure logging.
- Works for formats Pillow supports; unsupported formats fall back to original upload path.

## Operational Notes
- Ensure enough temp space for compressed copies; cleanup removes temp files after upload.
- Adjust quality steps in `utils/media_processing.py` if you need different compression aggressiveness.
