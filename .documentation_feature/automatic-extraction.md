# Automatic Extraction

## Overview
Archives sent to the account are automatically downloaded and extracted using multiple fallback strategies to maximize format coverage on diverse systems (Termux, Linux, etc.).

## Key Files & Components
- `extract-compressed-files.py`: orchestrates archive detection, download, queueing, and extraction tasks.
- `utils/file_operations.py`: `extract_archive_async()` tries patoolib, `zipfile`, `tarfile`, `unrar`, and `7z` in order; logs attempts and failures.
- `utils/constants.py`: defines supported extensions via `ARCHIVE_EXTENSIONS` and data directories for extraction and recovery.

## Process Flow
1. Event handler identifies documents with extensions in `ARCHIVE_EXTENSIONS` and downloads them to `data/`.
2. Extraction task enqueues `extract_archive_async()` in an executor to avoid blocking Telethon loop.
3. Extraction attempts patoolib when the system `file` command supports `--mime-type`; falls back to Python stdlib handlers, then CLI tools (`unrar`, `7z`).
4. On success, extracted files are passed to media filtering and upload queues; on failure, errors are surfaced to the chat.

## Edge Cases & Safeguards
- Validates archive existence and type before attempting extraction; logs size and path.
- Timeouts applied to `unrar` and subprocess calls; exceptions handled to continue fallback chain.
- Skips patoolib when the `file` binary lacks `--mime-type` to avoid Termux-specific crashes.
- Extraction failures preserve the downloaded archive for password retries or debugging unless cleanup explicitly removes it.

## Operational Notes
- For password-protected archives, see the dedicated feature doc; the extraction path is prepared but waits for password input.
- Ensure `p7zip`/`unrar` are installed for best coverage; otherwise only zip/tar subsets are guaranteed.
