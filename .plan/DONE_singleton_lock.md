# Plan: Implement Singleton Lock for Application Stability

## 1. Objective

The primary goal is to prevent the `sqlite3.OperationalError: database is locked` error that occurs when multiple instances of the `extract-compressed-files.py` script run simultaneously, especially after a system crash and restart.

This will be achieved by enforcing a "singleton" pattern, ensuring only one instance of the application can run at any given time.

## 2. Core Strategy: File-Based Locking

We will implement a file-based locking mechanism.

- **Lock File:** A file named `script.lock` will be created in the application's root directory upon startup.
- **Startup Logic:** The script will check for this file's existence at launch.
  - If `script.lock` **exists**, the script will assume another instance is active and will exit immediately.
  - If `script.lock` **does not exist**, the script will create it, write its own Process ID (PID) into it, and proceed with normal execution.
- **Shutdown Logic:** The script will delete `script.lock` upon a clean shutdown (whether it finishes successfully, is manually stopped, or exits due to a handled error).

If the script crashes, the `script.lock` file will be left behind, preventing a new instance from starting until the lock file is manually removed. This is a fail-safe approach.

## 3. Detailed Implementation Steps

### Step 3.1: Modify `extract-compressed-files.py` for Lock Management

I will add the lock management logic at the very beginning of the script's execution flow.

1.  **Import necessary modules:** `os`, `sys`, and `atexit`.
2.  **Define Lock File Path:** The path will be defined as a constant, e.g., `LOCK_FILE = "script.lock"`.
3.  **Implement `create_lock_file()` function:**
    - This function will be called at the very start of the script.
    - It will check if `LOCK_FILE` exists.
    - If it exists, it will read the PID from the file.
    - It will then check if a process with that PID is still running.
      - If yes, log an error "Application is already running." and exit the script (`sys.exit(1)`).
      - If no (a stale lock file from a crash), it will remove the old lock file.
    - It will then create the new `LOCK_FILE` and write the current process's PID into it.
4.  **Implement `remove_lock_file()` function:**
    - This function will simply delete `LOCK_FILE` if it exists.
5.  **Register Cleanup Hook:**
    - I will use `atexit.register(remove_lock_file)` to ensure the lock file is removed on any clean exit.
    - I will also wrap the main application logic in a `try...finally` block to call `remove_lock_file()` to handle exits from unexpected errors.

### Step 3.2: Increase Telethon's Database Timeout

As a secondary resilience measure, I will increase the timeout for the SQLite session database used by Telethon. This helps the application wait for a lock to be released instead of immediately crashing in cases of very brief lock contention.

1.  **Locate Client Initialization:** Find the line where the `TelegramClient` is instantiated.
2.  **Modify Session:** The `SQLiteSession` will be explicitly created with a `timeout` parameter set to `15` seconds.

```python
# Example of the change
from telethon.sessions import SQLiteSession

session = SQLiteSession('my_session.session', timeout=15)
client = TelegramClient(session, api_id, api_hash)
```

## 4. Validation Plan

After implementing the changes, I will validate the fix by simulating the conditions that cause the error:

1.  **Test Singleton Behavior:**
    - Run `python3 extract-compressed-files.py`.
    - In a separate terminal, run the same command again.
    - **Expected Outcome:** The second instance should print an error message and exit immediately.
2.  **Test Clean Shutdown:**
    - Stop the running script (e.g., with Ctrl+C).
    - **Expected Outcome:** The `script.lock` file should be automatically deleted.
3.  **Test Crash Recovery:**
    - Manually create a `script.lock` file with a fake PID.
    - Run `python3 extract-compressed-files.py`.
    - **Expected Outcome:** The script should detect the stale lock file, remove it, create a new one, and start normally.
