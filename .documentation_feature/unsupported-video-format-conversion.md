# Unsupported Video Format Conversion

## Overview
Automatically converts non-Telegram-friendly video formats to MP4 to guarantee playback and album compatibility, even when transcoding would otherwise be disabled.

## Key Files & Components
- `utils/media_processing.py`: `needs_video_processing()` decides when to transcode; `compress_video_for_telegram()` runs ffmpeg with Telegram-safe flags.
- `extract-compressed-files.py`: pipeline checks video compatibility and invokes conversion jobs before upload.
- `utils/constants.py`: `TRANSCODE_ENABLED` and `VIDEO_TRANSCODE_THRESHOLD_MB` influence when conversion occurs.

## Process Flow
1. After extraction or direct download, videos are evaluated via `needs_video_processing()` (container/codec, `.ts` exceptions, user toggle).
2. If processing is needed, `compress_video_for_telegram()` is run (async via executor) to produce `_compressed.mp4` output.
3. Resulting file path replaces the original in the upload task; duration/thumbnail are updated during upload.
4. If ffmpeg is unavailable, conversion is skipped with a warning and upload proceeds (may fail on Telegram if unsupported).

## Edge Cases & Safeguards
- `.ts` files are exempt because Telegram can stream them; avoids unnecessary recompression.
- Transcode is skipped when `TRANSCODE_ENABLED` is false, unless compatibility checks fail; logging notes the decision.
- ffmpeg errors/timeouts propagate to logs; upload falls back to original file, which may be further handled by retry logic.

## Operational Notes
- Install `ffmpeg`/`ffprobe` for reliable conversion and metadata extraction; required on most servers/Termux.
- Compression timeout is configurable; see compression-timeout-control feature.
