# Progress Tracking

## Overview
Provides real-time status updates during download, extraction, and upload so users can monitor progress via Telegram messages or logs.

## Key Files & Components
- `utils/telegram_operations.py`: `create_download_progress_callback()` builds Telethon-friendly callbacks to update messages incrementally.
- `extract-compressed-files.py`: attaches progress callbacks to downloads and logs stage transitions.
- `utils/utils.py`: formatting helpers like `human_size` and `format_eta` for readable progress text.

## Process Flow
1. When a download starts, a progress callback edits a message when percentage crosses `MIN_PCT_STEP` or after `MIN_EDIT_INTERVAL` seconds.
2. Extraction and upload steps log milestones (start, completion, cleanup) with sizes and durations.
3. Status commands (`/status`, `/queue`) report queue lengths and current tasks for snapshot visibility.

## Edge Cases & Safeguards
- Progress edits are rate-limited (`MIN_EDIT_INTERVAL`) to prevent API spam and reduce FloodWait risk.
- If progress message editing fails (e.g., permissions, deleted message), logging continues so the user still sees updates in logs.
- Callback handles total size unknown cases by skipping ETA to avoid misleading info.

## Operational Notes
- Tune `MIN_PCT_STEP`/`MIN_EDIT_INTERVAL` in `utils/constants.py` to balance update frequency vs. rate-limit risk.
