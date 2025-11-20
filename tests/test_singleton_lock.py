import os
import importlib.util
from pathlib import Path
import pytest


@pytest.fixture()
def singleton_lock():
    module_path = Path(__file__).resolve().parents[1] / "utils" / "singleton_lock.py"
    spec = importlib.util.spec_from_file_location("singleton_lock", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_create_and_remove_lock(tmp_path, singleton_lock):
    lock_file = tmp_path / "script.lock"
    
    singleton_lock.create_lock_file(str(lock_file))
    assert lock_file.exists()
    assert lock_file.read_text().strip() == str(os.getpid())
    
    singleton_lock.remove_lock_file(str(lock_file))
    assert not lock_file.exists()


def test_active_pid_blocks_start(tmp_path, singleton_lock):
    lock_file = tmp_path / "script.lock"
    lock_file.write_text(str(os.getpid()))
    
    with pytest.raises(SystemExit):
        singleton_lock.create_lock_file(str(lock_file))
    
    # Lock should remain in place when active PID detected
    assert lock_file.exists()
    assert lock_file.read_text().strip() == str(os.getpid())


def test_stale_pid_is_cleaned_and_replaced(tmp_path, singleton_lock):
    lock_file = tmp_path / "script.lock"
    
    stale_pid = 999999
    while singleton_lock.pid_is_running(stale_pid):
        stale_pid += 1
    lock_file.write_text(str(stale_pid))
    
    singleton_lock.create_lock_file(str(lock_file))
    assert lock_file.exists()
    assert lock_file.read_text().strip() == str(os.getpid())
