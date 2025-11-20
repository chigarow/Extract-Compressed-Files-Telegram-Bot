# FastTelethon Parallel Downloads

## Overview
Speeds up large Telegram downloads by using FastTelethon's parallel MTProto connections when available, yielding 10-20x faster transfers.

## Key Files & Components
- `utils/fast_download.py`: implements `fast_download_to_file()` using FastTelethon helpers.
- `extract-compressed-files.py`: tries to import FastTelethon and sets `FAST_DOWNLOAD_AVAILABLE`; uses `fast_download_to_file` when enabled.
- `utils/constants.py`: holds `FAST_DOWNLOAD_ENABLED` and `FAST_DOWNLOAD_CONNECTIONS` config values.

## Process Flow
1. On startup, script checks whether FastTelethon is importable; logs availability.
2. For eligible downloads, if both availability and `FAST_DOWNLOAD_ENABLED` are true, the fast path is chosen.
3. Download splits into multiple connections, writing to disk with progress callbacks just like the standard path.
4. If FastTelethon import fails or is disabled, the code falls back to Telethon's standard download.

## Edge Cases & Safeguards
- Requires `cryptg` for optimal performance; missing dependency logs a warning and disables fast mode gracefully.
- Premium users also benefit from larger chunk sizes (see optimized download speed feature) even without FastTelethon.
- Fast path respects sequential semaphores to avoid overloading the device/network.

## Operational Notes
- Install FastTelethon and `cryptg` in the virtualenv to enable; see requirements or pip instructions.
- Adjust `FAST_DOWNLOAD_CONNECTIONS` in `secrets.properties`/config to tune concurrency vs. CPU usage.
