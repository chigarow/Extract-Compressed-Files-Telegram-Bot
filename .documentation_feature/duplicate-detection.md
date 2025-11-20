# Duplicate Detection

## Overview
Prevents reprocessing the same archive by caching hashes of processed files, saving time and bandwidth on repeated sends or retries.

## Key Files & Components
- `utils/cache_manager.py`: manages persistent cache stored at `data/processed_archives.json` via `CacheManager`.
- `extract-compressed-files.py`: computes SHA256 of incoming archives (`compute_sha256`) and queries the cache before processing.
- `utils/constants.py`: declares `PROCESSED_CACHE_PATH` backing the cache file.

## Process Flow
1. When a new archive is received, the script computes SHA256 and looks it up in the cache.
2. If found and marked as extracted, the archive is skipped and the user is notified to avoid duplicate uploads.
3. After successful extraction and upload, cache entry is updated with filename, size, timestamp, and status.

## Edge Cases & Safeguards
- Corrupted cache format triggers a warning and rebuild; processing continues with a fresh cache to avoid crashes.
- Hashing uses streaming chunks to handle large archives without excessive RAM usage.
- Cache is keyed by hash, so renamed files with same content are still deduplicated.

## Operational Notes
- Clearing `data/processed_archives.json` will allow reprocessing of all archives; use sparingly to avoid unintended duplicates downstream.
