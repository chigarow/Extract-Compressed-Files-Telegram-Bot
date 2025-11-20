# Streaming Extraction & Upload Plan

- [x] **Step 1:** Profile current extraction/upload pipeline to identify touchpoints that assume full extraction, including queue processing, grouped uploads, cleanup registry, and retry handling.
- [x] **Step 2:** Design streaming extraction buffers (per-entry extraction helper, temp-file lifecycle, grouped batch builders, free-space checks, pause/resume signals) tailored for low-RAM/limited-storage devices like Xiaomi Mi 5.
- [x] **Step 3:** Implement the streaming extractor and uploader, ensuring immediate cleanup of per-file temps, crash-resume manifests, and compatibility with existing queue semantics.
- [x] **Step 4:** Build comprehensive unit tests covering streaming extraction, free-space guardrails, retries, and cleanup guarantees while validating legacy behavior remains intact.
- [x] **Step 5:** Run targeted pytest suites (streaming + queue/upload) to confirm stability before considering broader integration tests.

## Step 2 Design Summary

1. **StreamingExtractor helper**
   - Opens the archive via `zipfile`/`tarfile` and yields media entries sequentially.
   - For each entry, extracts to a `tempfile.NamedTemporaryFile(delete=False, dir=TORBOX_DIR)` to avoid RAM spikes; automatically deletes after upload confirmation.
   - Persists a lightweight manifest (`data/streaming_manifests/<archive>.json`) recording processed members so restarts resume without re-uploading.

2. **Free-space guardrails**
   - New utility `ensure_free_space(min_bytes)` using `shutil.disk_usage` on the extraction volume.
   - Before extracting each entry, if free space < threshold (configurable, default 3 GB for Xiaomi Mi 5), pause the queue: send Telegram notice, recheck every 30 s, resume when healthy.

3. **BatchBuilder**
   - Maintains in-memory batches per media type (photos/videos) capped at 10 files.
   - As soon as a batch fills or the archive ends, dispatch a grouped upload task referencing just-created temp files.
   - Tracks outstanding batches so retries know which temp files still exist, and triggers cleanup callbacks after upload completion.

4. **Immediate cleanup hooks**
   - After a batch upload succeeds (or a direct upload finishes), iterate over the temp files and unlink them; also prune manifest entries.
   - If upload fails and exceeds retry limit, delete the affected temp files and mark manifest entries as failed so the archive can continue without blocking.

5. **Queue/cleanup integration**
   - `ExtractionCleanupRegistry` now tracks active streaming manifests instead of entire folders.
   - `_process_extraction_and_upload` becomes an async loop pumping from `StreamingExtractor`, feeding `BatchBuilder`, and never materializing a full extraction directory.
   - Retry tasks persist enough context (archive path, next entry index, manifest path) to resume streaming mid-archive.

## Step 3 Implementation Summary

1. Created `utils/streaming_extractor.py` with `StreamingExtractor`, temp-file manifests, and low-free-space throttling tailored to Torbox ZIPs.
2. Extended QueueManager with `StreamingBatchBuilder`, sequential batch dispatch, and `_wait_for_upload_idle()` to keep outstanding files capped at one batch.
3. Grouped uploads now support `cleanup_file_paths` and streaming manifest flags, deleting temp files immediately after successful uploads and marking manifest progress for crash recovery.

## Step 4 Test Summary

- Extended `tests/test_streaming_extraction.py` with manifest persistence checks, grouped-upload cleanup coverage, low-storage pause/resume verification, and `StreamingBatchBuilder` batching assertions.
- Retained extraction failure notification tests to ensure the Torbox error messaging still passes under the streaming workflow, running `./venv/bin/pytest tests/test_streaming_extraction.py tests/test_extraction_failure_notifications.py` as the fast validation suite.

## Step 5 Test Summary

- Targeted regression suite: `./venv/bin/pytest tests/test_streaming_extraction.py tests/test_grouped_media_upload.py tests/test_extraction_failure_notifications.py` — confirms streaming flow, grouped batching, and failure notifications coexist without regressions.

## Future Considerations

1. Expand streaming beyond Torbox ZIPs (e.g., general archives or 7z/RAR via 7zip) and add integration tests for the pause/resume free-space flow.
2. Surface streaming manifest progress within the existing ProcessManager/cleanup reporting so operators can view per-archive streaming status via bot commands or summaries.