# Torbox CDN Downloads

## Overview
Detects Torbox CDN links in text messages and downloads the referenced archive/media with resume support, batching them into the normal extraction/upload pipeline.

## Key Files & Components
- `utils/torbox_downloader.py`: detection (`is_torbox_link`, `extract_torbox_links`), metadata helpers, `download_from_torbox()` with resume/backoff, and filename inference.
- `extract-compressed-files.py`: message handlers extract links and enqueue downloads; uses `download_torbox_with_progress` wrapper from `utils/__init__.py`.
- `data/torbox/`: dedicated storage directory for Torbox downloads defined in `utils/constants.py`.

## Process Flow
1. Incoming text messages are scanned for Torbox CDN patterns; each unique link is parsed for filename and queued.
2. Downloader issues ranged HTTP requests, resuming from `.part` files when present and reporting progress via callbacks.
3. Completed downloads are renamed from `.part`, normalized into `data/torbox/`, then treated as regular archives/media for extraction and upload.
4. Errors trigger exponential backoff retries up to the configured `max_retries`, with logging to aid diagnostics.

## Edge Cases & Safeguards
- Handles missing extensions by inferring from URL path segments; falls back to timestamped filenames to avoid collisions.
- Network interruptions keep partial `.part` files for resume rather than restarting the whole transfer.
- Invalid/expired Torbox tokens or HTTP errors are logged; download is retried with increasing delay.
- Dedicated directory separation prevents Torbox artifacts from cluttering the main `data/` path.

## Operational Notes
- Optional Torbox API key in `secrets.properties` improves metadata retrieval but is not mandatory for CDN links.
- When combined with WebDAV incremental downloads, ensure disk space is sufficient; see WebDAV docs if enabled.
