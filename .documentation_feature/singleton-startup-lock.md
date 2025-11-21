# Singleton Startup Lock & Session Timeout

## What It Does
- Prevents concurrent bot instances by creating a PID-based lock file `script.lock` in the project root during startup.
- Detects stale locks after crashes: removes the lock if the recorded PID is no longer running, then starts normally.
- Cleans up the lock on shutdown via `atexit` and `finally` to avoid blocking restarts.
- Uses a custom `TimeoutSQLiteSession` with a 15s SQLite connection timeout to reduce transient `database is locked` failures in Telethon session storage.

## Why It Matters
Running multiple instances (e.g., after Termux crash/restart) can corrupt the Telethon session or hit SQLite `OperationalError: database is locked`. The startup lock and longer timeout keep the session stable and ensure only one worker controls the queue and download/upload processors.

## Operational Notes
- Lock file: `script.lock` in the repo root. If the script crashes and a lock remains, the next start will remove it automatically if the PID is stale. If a legitimate instance is running, startup exits immediately.
- Session path is unchanged (`data/session.session`), so no re-login is required.
- Tests cover lock create/remove, active PID blocking, stale PID cleanup, and the timeout wiring for the Telethon client.
