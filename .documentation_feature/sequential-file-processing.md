# Sequential File Processing

## Overview
This is the user-facing description of the same sequential pipeline described in `sequential-processing.md`, emphasizing the linear download→compress→upload→cleanup order to reduce RAM usage.

## Key Files & Components
- `utils/constants.py`: `DOWNLOAD_SEMAPHORE_LIMIT`/`UPLOAD_SEMAPHORE_LIMIT` set to 1 by default.
- `utils/queue_manager.py`: enforces the semaphores and orchestrates cleanup after each archive finishes.
- `extract-compressed-files.py`: uses a global semaphore around message/event processing.

## Process Flow
1. Only one archive/message is admitted to processing at a time.
2. Each stage completes fully before the next archive starts, keeping disk and memory footprints small.
3. Upload completion triggers cleanup, then the next queued item begins.

## Edge Cases & Safeguards
- Prevents concurrent extraction folder collisions and mitigates FloodWait by lowering API pressure.
- If configuration raises concurrency, semaphores adjust accordingly but should be used cautiously.
- Works in tandem with WebDAV sequential mode when enabled via env flag.

## Operational Notes
- This file exists separately from `sequential-processing.md` to mirror the duplicated bullet list in `readme.md` for clarity.
