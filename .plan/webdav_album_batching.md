# Plan: WebDAV album batching & quiet notifications

## Goals
- Reduce Telegram rate-limit hits during WebDAV uploads by minimizing message edits/sends.
- Batch WebDAV media into Telegram albums (max 10 items) with images first, then videos.
- Send a single completion notice like “All media has been uploaded” when a WebDAV batch finishes.
- Preserve existing retry, sequential mode, and cache/cleanup behaviors with production confidence.

## Tasks
1. Current-state assessment
   - Trace WebDAV download→upload flow (`_execute_webdav_file_task`, `_execute_upload_task`, `_execute_grouped_upload`) to find notification touchpoints and batching gaps.
   - Identify where to hook WebDAV-specific grouping (per directory/source) and how to order images→videos under Telegram’s 10-item album cap.
2. Design & implementation
   - Introduce WebDAV album builder that accumulates completed downloads per source and emits grouped upload tasks (images first, then videos) respecting the 10-item limit.
   - Throttle Telegram notices for WebDAV uploads: avoid progress edits per file; keep optional start note; emit a single final “all media uploaded” message per batch/source.
   - Ensure flood-wait retries keep files and do not spam messages; integrate with existing retry queue.
   - Keep sequential mode semantics (wait for uploads before next download when enabled) intact.
3. Tests
   - Unit tests for WebDAV grouping: verify image/video separation, 10-item batching, ordering (images before videos), and task metadata integrity.
   - Tests for notification throttling: ensure only final completion message is sent per batch and progress edits are suppressed for WebDAV uploads.
   - Regression coverage for retry/flood-wait paths to confirm files are retained and tasks rescheduled without extra edits.
4. Validation
   - Run targeted suites: `pytest tests/test_webdav_upload_processor_fix.py` and new tests covering grouping/notifications.
   - Full suite: `pytest tests` to guard against regressions in other features.
   - Summarize results and readiness for production.
