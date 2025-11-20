import os
import sys


def _log_or_print(message, logger=None, level="info"):
    """Use provided logger when available, otherwise print."""
    if logger:
        log_fn = getattr(logger, level, logger.info)
        log_fn(message)
    else:
        print(message)


def pid_is_running(pid: int) -> bool:
    """Check if a PID is currently running."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Assume running if we lack permissions to signal
        return True
    except OSError:
        return False


def create_lock_file(lock_file: str, logger=None):
    """Create singleton lock or exit if another instance is running."""
    if os.path.exists(lock_file):
        try:
            with open(lock_file, "r", encoding="utf-8") as f:
                existing_pid = int(f.read().strip() or 0)
        except Exception:
            existing_pid = None
        
        if existing_pid and pid_is_running(existing_pid):
            _log_or_print(f"Another instance is already running (PID {existing_pid}). Exiting.", logger=logger, level="error")
            sys.exit(1)
        else:
            try:
                os.remove(lock_file)
                _log_or_print("Removed stale lock file.", logger=logger, level="warning")
            except FileNotFoundError:
                pass
            except Exception as e:
                _log_or_print(f"Failed to remove stale lock file: {e}", logger=logger, level="error")
                sys.exit(1)
    
    try:
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        _log_or_print(f"Acquired singleton lock at {lock_file}", logger=logger)
    except FileExistsError:
        _log_or_print("Lock file already exists, refusing to start.", logger=logger, level="error")
        sys.exit(1)
    except Exception as e:
        _log_or_print(f"Failed to create lock file: {e}", logger=logger, level="error")
        sys.exit(1)


def remove_lock_file(lock_file: str, logger=None):
    """Remove singleton lock file if it exists."""
    try:
        if os.path.exists(lock_file):
            os.remove(lock_file)
            _log_or_print("Removed singleton lock.", logger=logger, level="info")
    except Exception as e:
        _log_or_print(f"Failed to remove lock file: {e}", logger=logger, level="error")
