
# Plan: Automated Conversion and Re-upload of Failed Files

## 1. Goal

To create a fully automated, end-of-process workflow that handles video files that fail to upload due to `MediaInvalidError`. The system will collect these problematic files, attempt to convert them into a Telegram-compatible format after all other uploads are finished, and then try to upload them again.

## 2. Current Process Analysis

- Media uploads are managed by a queue processor, likely located in `utils/queue_manager.py`.
- This processor attempts to upload files in batches (albums). When a batch fails with a `MediaInvalidError` (as seen in the logs), it correctly falls back to uploading each file in that batch individually.
- Currently, if a file fails again during the individual upload attempt, the error is logged, but the temporary file is discarded. There is no mechanism to salvage it.

## 3. Proposed New Workflow

1.  **Collection of Failed Files:** The individual upload logic will be modified. When a file fails with an error indicating it's invalid or corrupted, instead of just being logged and forgotten, its local path and necessary metadata (destination chat, original filename, caption) will be appended to a new "failed uploads" list.

2.  **Main Process Completion:** The script will continue its normal operation, processing all archives and media files in the queue until all primary tasks are complete.

3.  **Recovery Phase Trigger:** Once the main queues are empty, the script will check if the "failed uploads" list contains any items. If it is, it will enter a new "Recovery Phase."

4.  **Conversion and Re-upload Loop:** The script will iterate through each item in the "failed uploads" list one by one.
    a.  **Conversion:** It will call a new video conversion function that uses `ffmpeg` to re-encode the problematic file into a standard MP4 format (H.264 video, AAC audio), which is highly compatible with Telegram.
    b.  **Re-upload:** After a successful conversion, it will attempt to upload the newly converted file.
    c.  **Success:** If the upload succeeds, the temporary converted file and the original problematic file are deleted.
    d.  **Final Failure:** If the upload fails *again* even after conversion, the script will stop trying. It will move the *original problematic file* to a permanent `data/quarantine/` directory for manual inspection and log a final error message. This prevents infinite loops.

5.  **Final Report:** At the end of the recovery phase, a summary message will be logged, stating how many files were successfully recovered and how many were moved to quarantine.

## 4. Component-wise Changes

### `utils/queue_manager.py` (Assumed Location of Core Logic)

-   The function responsible for processing upload tasks and handling the individual fallback loop needs to be located and modified.
-   It must be updated to accept a `failed_uploads_list` parameter (passed down from the main script).
-   When an individual file upload fails with a `MediaInvalidError`, it should append a dictionary containing `{ "file_path": ..., "chat_id": ..., "caption": ... }` to this list instead of just logging the error.

### `extract-compressed-files.py`

-   A new list will be managed in the main script's context, initialized as `self.failed_media_files = []`.
-   This list will be passed down through the function calls to the queue processor.
-   A new method, `_handle_failed_uploads(self)`, will be created. This method contains the logic for the "Recovery Phase."
-   The main execution loop will be modified to call `await self._handle_failed_uploads()` after the primary processing is complete.
-   This method will log the start of the phase, loop through the failed files, call the conversion and upload functions, and handle final failures by moving files to `data/quarantine/`.

### `utils/media_processing.py`

-   A new function, `convert_video_for_recovery(input_path: str) -> str`, will be added.
-   This function will take a file path, generate a new output path for the converted file, and use `subprocess` to run an `ffmpeg` command.
-   **Proposed `ffmpeg` command:**
    ```sh
    ffmpeg -i "INPUT_PATH" -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k -movflags +faststart "OUTPUT_PATH"
    ```
-   The function will return the path to the converted file on success and `None` on failure.

## 5. Data Structure for Failed Files

The `failed_media_files` list will contain dictionaries with this structure:

```python
[
    {
        "file_path": "/path/to/tmp/problematic_video.mp4",
        "chat_id": "target_username_or_id",
        "caption": "The original caption for the file",
        "original_filename": "archive_name.zip - Batch 1"
    },
    # ... more items
]
```

## 6. Implementation Steps

1.  **Modify `extract-compressed-files.py`:**
    -   Initialize `self.failed_media_files = []`.
    -   Add the `_handle_failed_uploads` method stub.
    -   Update the main loop to call it at the end.

2.  **Locate & Modify Queue Processor:**
    -   Find the individual upload fallback loop (likely in `utils/queue_manager.py`).
    -   Modify it to pass the `failed_media_files` list and populate it on failure.

3.  **Implement Conversion Function:**
    -   Add the `convert_video_for_recovery` function to `utils/media_processing.py`.

4.  **Complete `_handle_failed_uploads`:**
    -   Flesh out the method to orchestrate the recovery process: iterate, call conversion, call upload, and handle quarantine logic.

5.  **Dependencies & Setup:**
    -   Ensure the `data/quarantine/` directory is created if it doesn't exist.
    -   The script already checks for `ffmpeg`, which is sufficient.

6.  **Testing:**
    -   Create a test case using a known problematic video file to verify that it is correctly identified, converted, re-uploaded, and cleaned up.
