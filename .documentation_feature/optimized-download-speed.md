# Optimized Download Speed

## Overview
Uses larger chunk sizes for Telegram Premium accounts and tunable chunk settings to reduce overhead and maximize throughput.

## Key Files & Components
- `utils/constants.py`: `DOWNLOAD_CHUNK_SIZE_KB` and `PARALLEL_DOWNLOADS` are pulled from config; premium-aware sizing is applied in download helpers.
- `extract-compressed-files.py`: selects chunk sizes and download method per file, leveraging FastTelethon when available.
- `config.py`: loads user-provided overrides from `secrets.properties`.

## Process Flow
1. At startup, config values are read and stored in constants.
2. When downloading, the script picks chunk size based on `DOWNLOAD_CHUNK_SIZE_KB` (larger for premium) and connection count.
3. Download proceeds through Telethon or FastTelethon with progress callbacks for visibility.

## Edge Cases & Safeguards
- Chunk sizes tuned for premium accounts can be reduced via config if a network is unstable; changes take effect on restart.
- Parallel download count is bounded by `PARALLEL_DOWNLOADS` to prevent excessive connection usage.
- Falls back to Telethon defaults if custom chunk values cause errors.

## Operational Notes
- Adjust values in `secrets.properties` under `DOWNLOAD_CHUNK_SIZE_KB`/`PARALLEL_DOWNLOADS` and restart to apply.
