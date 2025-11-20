# Compression Timeout Control

## Overview
Allows tuning of the maximum time ffmpeg video compression is allowed to run, preventing runaway transcode jobs on low-power devices.

## Key Files & Components
- `utils/constants.py`: `COMPRESSION_TIMEOUT_SECONDS` pulled from config (default 300s if invalid/missing).
- `utils/command_handlers.py`: `/compression-timeout <seconds>` command updates config and global timeout.
- `utils/media_processing.py`: `compress_video_for_telegram()` uses the configured timeout when running ffmpeg.

## Process Flow
1. Startup loads timeout from `secrets.properties` into constants.
2. When compression is invoked, the timeout value is passed to the ffmpeg subprocess via executor wrapper.
3. If ffmpeg exceeds the timeout, it is terminated and the operation logs an error; upload may fall back to the original file.
4. Users can adjust timeout at runtime; handler saves to config so future runs persist the value.

## Edge Cases & Safeguards
- Invalid or non-positive timeout values default to 300s to avoid unbounded runs.
- Timeout errors are caught and reported; failed conversions trigger retry/failure handling without crashing the bot.

## Operational Notes
- Increase timeout for very large/complex videos if hardware permits; decrease on Termux to avoid device overheating.
