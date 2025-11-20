# Plan: Streaming Progress Reporting

This plan outlines the steps to implement a feature that reports the progress of in-flight streaming extractions.

### Phase 1: Enhance Manifest Data
- [x] **Modify `StreamingExtractor`:** Update the extractor to count the total number of media files in an archive upon initialization.
- [x] **Update `StreamingManifest`:** Store the `total_files` count in the JSON manifest file alongside the list of `processed` files.

### Phase 2: Implement Status Command Logic
- [x] **Locate Status Handler:** Identify the command handler responsible for status reports (likely in `utils/command_handlers.py`).
- [x] **Add Progress Logic:** Implement a new function to scan for active streaming manifests in `data/streaming_manifests/`.
- [x] **Format Progress Output:** For each active manifest, calculate the progress percentage (`len(processed) / total_files`) and format it into a user-friendly string.
- [x] **Integrate into Status Report:** Append the formatted progress strings to the main status message.

### Phase 3: Validation
- [x] **Create New Test:** Develop a new test case that simulates an in-progress streaming extraction.
- [x] **Verify Test:** Assert that the status command output correctly includes the formatted progress of the simulated extraction.
