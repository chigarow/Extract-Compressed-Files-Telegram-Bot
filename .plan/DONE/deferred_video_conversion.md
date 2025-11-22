# Plan: Deferred Video Conversion for Incompatible Formats

This plan outlines the implementation of a system to handle unsupported video formats that cause `SendMultiMediaRequest` errors during grouped uploads.

The goal is to defer the handling of these problematic files, convert them to a compatible format (MP4), and then upload them individually. This will happen only after all other, non-problematic media in the queue has been successfully uploaded.

## 1. Modify Grouped Upload Error Handling

**File:** `utils/queue_manager.py`
**Function:** `_execute_grouped_upload`

The current implementation's error handling for `telethon.errors.rpcerrorlist.MediaInvalidError` is too basic. It falls back to individual uploads for all files in the failed group. This needs to be more intelligent.

**New Logic:**
1.  Catch the `MediaInvalidError`.
2.  In the `except` block, iterate through the list of files that were part of the failed group.
3.  For each file, use a new helper function (e.g., `media_processing.is_telegram_compatible_video(file_path)`) to determine if it's a supported video format. This function will check the file extension (e.g., `.mp4`, `.mkv`) and potentially other properties if needed.
4.  Separate the files into two lists: `compatible_files` and `incompatible_files`.
5.  Immediately re-queue the `compatible_files` for a new grouped upload.
6.  For each file in `incompatible_files`, add a new task to the queue with a special type, `'deferred_conversion'`. This task will store the file path and original task metadata.

## 2. Implement Deferred Conversion Task Handler

**File:** `utils/queue_manager.py`

A new handler function will be created to process the `'deferred_conversion'` tasks. This ensures these tasks are handled by the queue manager's main processing loop but are distinct from regular uploads.

**New Logic:**
1.  Create a new function, e.g., `_execute_deferred_conversion(task)`.
2.  This function will be called when the queue processor encounters a task of type `'deferred_conversion'`.
3.  The handler will call a conversion function in `utils/media_processing.py` (e.g., `convert_video_for_recovery(file_path)`).
4.  This conversion function will use `ffmpeg` to convert the video to a standard H.264 MP4 file. It should handle cases where `ffmpeg` is not installed by logging an error and quarantining the file.
5.  Upon successful conversion, it will return the path to the new, converted file.
6.  The `_execute_deferred_conversion` handler will then add a *new* standard `'upload'` task to the queue for the converted file, ensuring it gets uploaded individually.

## 3. Create Video Processing Helper Functions

**File:** `utils/media_processing.py`

This file will contain the low-level logic for checking compatibility and running the conversion.

**New Functions:**
1.  `is_telegram_compatible_video(file_path)`:
    *   Takes a file path as input.
    *   Returns `True` if the file extension is in a list of known-good formats (e.g., `['.mp4', '.mkv']`).
    *   Returns `False` otherwise.
2.  `convert_video_for_recovery(file_path)`:
    *   Checks for the presence of `ffmpeg` using `shutil.which('ffmpeg')`. If not found, it logs a critical error and returns `None`.
    *   Constructs and executes an `ffmpeg` command to convert the video. A sensible default would be: `ffmpeg -i "{input_file}" -c:v libx264 -c:a aac -preset fast -crf 23 "{output_file}.mp4"`.
    *   It should handle potential errors during conversion.
    *   Upon success, it returns the path to the newly created `.mp4` file.
    *   The original incompatible file should be cleaned up after successful conversion and upload.

## 4. Configuration

**File:** `config.py`

To allow the user to control this feature, a new configuration option will be added.

*   `DEFERRED_VIDEO_CONVERSION = True`

This flag will be checked in `_execute_grouped_upload` before attempting to queue a `'deferred_conversion'` task. If `False`, the system will fall back to the old behavior of individual retries to avoid unexpected conversions.
