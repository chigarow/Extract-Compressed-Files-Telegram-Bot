# Plan: Fix WebDAV stalled download/resume issues

## Goals
- Prevent WebDAV downloads from hanging indefinitely when the server stops sending data mid-stream.
- Ensure Range/partial downloads resume safely without corrupting files.
- Restore end-to-end reliability (download → upload) with production confidence.

## Tasks
1. Instrumentation & Diagnostics
   - Add detailed logging around WebDAV GET responses (status code, headers, resume offsets, chunk size used).
   - Log when Range is ignored or when resuming from partial files.
   - Add periodic “still downloading” heartbeat with byte counts to detect stalls in logs.
2. Inactivity Watchdog for Streaming
   - Implement per-download inactivity timer in `TorboxWebDAVClient.download_file`: if no chunk arrives within a threshold (e.g., 30–60s), cancel the response/client, recreate the HTTP client, and retry with Range from the last written byte.
   - Make the watchdog threshold configurable (env/config) with sensible defaults for Termux/desktop.
   - Ensure retries respect existing max retry/backoff behavior in `queue_manager`.
3. Robust Resume & Partial Handling
   - When server ignores Range (HTTP 200 while expecting 206), reset state: delete/overwrite corrupt partials and restart from byte 0 to avoid appending bad data.
   - Harden `.part` file handling: clean zero-byte partials, verify sizes before resume, guard against duplicate append.
4. Integration with Queue Manager
   - Ensure sequential WebDAV mode still downloads/upload in order; ensure the watchdog retry interacts cleanly with `_handle_webdav_download_failure` and does not orphan tasks.
   - Update progress callbacks to surface restarts/retries to user replies (status message edits).
5. Tests (add/extend)
   - Unit tests for `download_file` covering: normal chunked download, resume with 206, server ignores Range (200) → reset, inactivity watchdog triggering retry, and correct chunk size usage from config.
   - Integration tests for queue manager WebDAV tasks: ensure retried downloads enqueue uploads once complete; verify sequential mode waits appropriately; ensure partial files are cleaned up on retry.
6. Validation & Production Readiness
   - Run targeted unit tests: `pytest tests/test_webdav_chunking.py` and new tests for inactivity/resume behavior.
   - Run WebDAV integration suite: `pytest tests/test_webdav_integration.py` and `pytest tests/test_webdav_upload_processor_fix.py`.
   - Full regression sweep: `pytest tests` to confirm no regressions in existing features (including Telegram session timeout test).
   - If available, reproduce against problematic WebDAV link to confirm watchdog resolves stalls (manual/optional).

## Deliverables
- Updated WebDAV client with watchdog/retry and safer resume behavior.
- Enhanced queue integration and user-facing status updates during retries.
- New/updated tests covering edge cases and stall scenarios.
- Pytest runs recorded (targeted + full suite) to prove readiness.
