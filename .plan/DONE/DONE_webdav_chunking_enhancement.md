# PLAN: WebDAV Download/Upload Chunking Enhancement

**Date:** 2025-11-20
**Author:** Gemini Code Assist
**Objective:** Implement configurable chunking for WebDAV downloads and uploads to reduce memory usage on resource-constrained devices like Termux on Android.

## 1. Motivation

The current WebDAV client may load entire files into memory during download or upload operations. On devices with limited RAM (e.g., Xiaomi Mi 5 running Termux), this can lead to out-of-memory errors and application crashes, especially with large files.

This enhancement introduces a `WEBDAV_CHUNK_SIZE_KB` setting in `secrets.properties` to control the size of data chunks processed at one time, making the WebDAV operations significantly more resource-friendly. This complements the existing `WEBDAV_SEQUENTIAL_MODE` by reducing memory pressure for each individual file operation.

## 2. Proposed Changes

### 2.1. Configuration (`utils/constants.py`)

1.  **Introduce New Setting:** Add a new configuration variable `WEBDAV_CHUNK_SIZE_KB` to be read from `secrets.properties`.
2.  **Default Value:** Provide a sensible default value (e.g., `1024` KB) that balances performance and memory usage. This ensures the script remains functional without explicit configuration.
3.  **Data Type:** The value will be read as an integer and converted to bytes for internal use (KB * 1024).

### 2.2. WebDAV Client Modifications (`utils/webdav_client.py`)

The core logic will be updated within the `TorboxWebDAVClient` class.

1.  **Chunked Downloads:**
    *   Modify the `download_file` (or equivalent) method.
    *   Instead of downloading the entire file at once, use the `webdav3.client.Client.resource().read()` method in a loop.
    *   In each iteration, read a chunk of size `WEBDAV_CHUNK_SIZE_KB` (in bytes) and write it to the local destination file.
    *   This ensures the entire file is never held in memory.
    *   The existing progress callback logic will need to be integrated into this loop to provide real-time status updates.

2.  **Chunked Uploads:**
    *   Modify the `upload_file` (or equivalent) method.
    *   Instead of sending the local file in one go, open the file in binary read mode.
    *   Use a `webdav3.client.Client.resource().write()` method that accepts a generator or a file-like object that can be read in chunks.
    *   Create a generator function that reads the local file in chunks of `WEBDAV_CHUNK_SIZE_KB` and yields them. This generator will be passed to the WebDAV client.
    *   This prevents loading the entire upload file into memory.
    *   Integrate progress reporting within the generator to track upload progress accurately.

### 2.3. Documentation (`readme.md`)

1.  **Add New Configuration:** Document the `WEBDAV_CHUNK_SIZE_KB` option in the "Configuration Options" section of `readme.md`.
2.  **Explain Benefit:** Briefly explain its purpose and recommend its use for low-resource environments, mentioning that it works well with `WEBDAV_SEQUENTIAL_MODE`.

## 3. Testing Plan

A comprehensive testing strategy is crucial to ensure this change is production-ready and does not introduce regressions.

### 3.1. Unit Tests (`tests/test_webdav_client.py`)

We will create a new test file or add to an existing one to specifically validate the chunking logic. This will involve extensive mocking of the `webdav3` library and file system.

**Test Cases:**

1.  **Test Download Chunking:**
    *   **Setup:** Mock a remote WebDAV file of a known size (e.g., 5MB). Configure a small `WEBDAV_CHUNK_SIZE_KB` (e.g., 64 KB).
    *   **Action:** Call the `download_file` method.
    *   **Verification:**
        *   Assert that the underlying `resource().read()` method was called multiple times.
        *   Calculate the expected number of calls (`ceil(file_size / chunk_size)`) and assert it matches.
        *   Verify that the final local file was created and its content matches the source mock data.

2.  **Test Upload Chunking:**
    *   **Setup:** Create a local mock file of a known size (e.g., 5MB). Configure a small `WEBDAV_CHUNK_SIZE_KB` (e.g., 64 KB).
    *   **Action:** Call the `upload_file` method.
    *   **Verification:**
        *   Mock the `resource().write()` method and assert that it was called with a generator or a file-like object.
        *   Iterate through the passed generator to confirm it yields chunks of the correct size.
        *   Verify that the total data written to the mock server equals the original file size.

3.  **Test Edge Case: File Smaller Than Chunk Size:**
    *   **Setup:** Use a file size smaller than the configured chunk size.
    *   **Action:** Run both download and upload tests.
    *   **Verification:** Assert that the `read()`/`write()` operations are performed only once with the correct total file size.

4.  **Test Edge Case: File Size is an Exact Multiple of Chunk Size:**
    *   **Setup:** Use a file size that is an exact multiple of the chunk size (e.g., 128KB file with 64KB chunks).
    *   **Action:** Run both download and upload tests.
    *   **Verification:** Assert that the correct number of chunks (exactly 2, in this case) are processed.

5.  **Test Default Behavior (No Configuration):**
    *   **Setup:** Do not set `WEBDAV_CHUNK_SIZE_KB` in the test configuration.
    *   **Action:** Run both download and upload tests.
    *   **Verification:** Ensure the operations complete successfully using the default chunk size defined in `constants.py`.

### 3.2. Integration Tests

While unit tests cover the logic, integration tests will validate the feature against a real WebDAV server.

**Test Environment:**
*   A local Docker-based WebDAV server (e.g., using `nginx-webdav`) or a test account on a service like Torbox.

**Test Scenarios:**

1.  **Scenario: Large File Integrity**
    *   **Action:** Download and then re-upload a large file (e.g., 1GB) with a small `WEBDAV_CHUNK_SIZE_KB` (e.g., 512 KB).
    *   **Verification:**
        *   The script should not crash due to memory issues.
        *   Perform a checksum (SHA256) on the original file, the downloaded file, and the re-uploaded file (by downloading it again). All three checksums must match.

2.  **Scenario: Zero-Byte File**
    *   **Action:** Attempt to download and upload a zero-byte file.
    *   **Verification:** The script should handle this gracefully without errors, and the resulting file should also be zero bytes.

3.  **Scenario: Interaction with Other Features**
    *   **Action:** Enable `WEBDAV_SEQUENTIAL_MODE=true` and `WEBDAV_CHUNK_SIZE_KB=128`. Queue up several WebDAV links for processing.
    *   **Verification:**
        *   Confirm that files are still processed one by one (sequentially).
        *   Confirm that each file operation uses chunking.
        *   Check for the integrity of all processed files.

### 3.3. Production Readiness Checklist

-   [ ] All new and existing unit tests pass (`pytest tests/`).
-   [ ] All integration tests pass, verifying file integrity.
-   [ ] Code is reviewed for clarity, efficiency, and adherence to project style.
-   [ ] Error handling is robust (e.g., network interruptions during a chunked transfer). The existing retry logic should handle this, but it needs to be verified.
-   [ ] `readme.md` is updated with the new configuration.
-   [ ] The change does not negatively impact other download methods (Telegram, Torbox CDN). This is guaranteed by isolating the changes to `utils/webdav_client.py`.

## 4. Implementation Steps

1.  **Branch:** Create a new feature branch: `feature/webdav-chunking`.
2.  **Constants:** Add `WEBDAV_CHUNK_SIZE_KB` to `utils/constants.py`.
3.  **Unit Tests (TDD):** Write the failing unit tests first in `tests/test_webdav_client.py` to define the expected behavior.
4.  **Implementation:** Modify `utils/webdav_client.py` to implement the chunked download and upload logic, making the tests pass.
5.  **Integration Tests:** Set up the integration test environment and run the validation scenarios.
6.  **Documentation:** Update `readme.md`.
7.  **Review & Merge:** Create a pull request for review, ensuring all checks and tests pass before merging into the main branch.