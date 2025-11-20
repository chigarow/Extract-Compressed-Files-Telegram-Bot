# Password Protected Archive Support

## Overview
Handles archives requiring passwords via a chat-based `/pass <password>` command so users can unlock files without terminal interaction.

## Key Files & Components
- `utils/command_handlers.py`: `handle_password_command()` manages pending password state, invokes extraction, and updates queues.
- `utils/file_operations.py`: `extract_with_password()` leverages `7z` for decryption; `is_password_error()` detects incorrect passwords from error text.
- `extract-compressed-files.py`: tracks `pending_password` and routes password replies to the appropriate archive context.

## Process Flow
1. When extraction hits a password error, the bot notifies the user and stores `pending_password` containing archive paths and original event.
2. User sends `/pass <password>`; handler attempts extraction with `7z` into the prepared directory.
3. On success, handler queues `extract_and_upload` task and clears pending state; on failure, it reports errors and cleans temp folders.
4. `/cancel-password` can abort the pending prompt and remove placeholders.

## Edge Cases & Safeguards
- Requires `7z`/`7za` in PATH; otherwise raises runtime error advising installation.
- Detects wrong passwords separately from other extraction errors to allow retries without restarting.
- Cleans up partially extracted data on non-password errors to avoid orphaned files.

## Operational Notes
- Password attempts are sequential; only one archive can await a password at a time to simplify state management.
- Logging includes only filenames, not passwords, to avoid secrets leakage.
