# Remaining Test Fixes (25 failures)

## Fixed So Far (13 tests)
1. ✅ All 5 torbox retry mechanism tests
2. ✅ All 3 event serialization tests  
3. ✅ All 9 grouped media upload tests
4. ✅ 1 video processing path generation test

## Remaining Categories

### Queue Manager & Event Loop (13 tests)
- test_queue_recovery_after_crash
- test_concurrent_task_failures
- test_queue_persistence
- test_concurrency_limits
- test_retry_mechanism
- test_max_retry_attempts
- test_progress_callback
- test_error_handling_in_processing
- test_full_download_workflow
- test_queue_recovery_after_restart
- test_queue_manager_init_no_event_loop
- test_ensure_processors_started
- test_multiple_ensure_calls_safe
- test_integration_scenario

### Cleanup & File Management (2 tests)
- test_grouped_upload_cleans_streaming_files
- test_torbox_zip_download_and_stream_extraction

### Network & Error Handling (4 tests)
- test_network_type_detection_failure
- test_wifi_wait_timeout
- test_progress_callback_handles_flood_wait
- test_extract_with_patoolib_failure

### Integration Tests (3 tests)
- test_full_download_queue_workflow
- test_concurrent_queue_processing
- test_process_state_persistence

### Compression & Media (3 tests)
- test_compression_triggers_with_lowercase_images
- test_execute_grouped_upload_validates_limit (needs queue_manager patch fix)

## Next Steps
1. Fix remaining queue_manager mock paths in tests
2. Address cleanup registry file persistence issues
3. Fix queue persistence serialization
4. Handle missing patoolib module in tests
5. Fix network monitor attribute errors
6. Adjust flood wait timing expectations

## Test Status
- Total: 397 tests
- Passing: 369 (93%)
- Failing: 25 (6.3%)
- Skipped: 3 (0.8%)
