# Organized File Structure

## Overview
Torbox and WebDAV downloads are isolated into dedicated directories to keep `data/` tidy and prevent collisions with other processing artifacts.

## Key Files & Components
- `utils/constants.py`: defines `TORBOX_DIR` (`data/torbox`) and `WEBDAV_DIR` (`data/webdav`) and ensures they exist on startup.
- `utils/torbox_downloader.py`: writes Torbox downloads into `TORBOX_DIR`.
- `utils/webdav_client.py`: stores WebDAV files under `WEBDAV_DIR` when enabled.

## Process Flow
1. At import time, constants module creates the directory structure if missing.
2. Downloaders place files into their dedicated subdirectories, leaving main `data/` for generic archives and metadata.
3. Cleanup/monitoring scripts reference these paths to manage storage without mixing file types.

## Edge Cases & Safeguards
- Directory creation is idempotent and occurs every startup, so missing folders are auto-healed.
- Separation avoids name collisions between Torbox/WebDAV and regular Telegram downloads.

## Operational Notes
- If relocating `data/`, ensure all subdirectories move together to keep paths consistent with constants.
