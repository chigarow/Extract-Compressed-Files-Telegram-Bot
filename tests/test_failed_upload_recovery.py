import importlib.util
import os
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "extract-compressed-files.py"


def load_extractor(monkeypatch, tmp_path):
    """Load the extractor script as a module with isolated paths."""
    module_name = f"extractor_recovery_{os.urandom(4).hex()}"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Route persistence folders to the temporary test path
    failed_file = tmp_path / "failed_uploads.json"
    quarantine_dir = tmp_path / "quarantine"
    recovery_dir = tmp_path / "recovery"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    recovery_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(module, "FAILED_UPLOADS_FILE", str(failed_file), raising=False)
    monkeypatch.setattr(module, "QUARANTINE_DIR", str(quarantine_dir), raising=False)
    monkeypatch.setattr(module, "RECOVERY_DIR", str(recovery_dir), raising=False)

    # Prevent cross-test leakage
    module.failed_media_files = []

    return module


@pytest.mark.asyncio
async def test_recovery_success(monkeypatch, tmp_path):
    mod = load_extractor(monkeypatch, tmp_path)

    original = tmp_path / "bad_video.mp4"
    original.write_bytes(b"bad")

    converted = tmp_path / "recovery" / "converted.mp4"

    def fake_convert(path):
        converted.parent.mkdir(parents=True, exist_ok=True)
        converted.write_bytes(b"converted")
        return str(converted)

    class DummyOps:
        def __init__(self, client):
            self.client = client

        async def upload_media_file(self, target, file_path, caption=None, progress_callback=None):
            return True

    async def fake_target(client=None):
        return "chat123"

    monkeypatch.setattr(mod, "convert_video_for_recovery", fake_convert)
    monkeypatch.setattr(mod, "TelegramOperations", DummyOps)
    monkeypatch.setattr(mod, "ensure_target_entity", fake_target)

    mod.failed_media_files = [
        {
            "file_path": str(original),
            "chat_id": "chat123",
            "caption": "retry me",
            "original_filename": "bad_video.mp4",
            "status": "pending",
        }
    ]

    await mod._handle_failed_uploads()

    assert mod.failed_media_files == []
    assert not original.exists()
    assert not converted.exists()
    # Ensure state was persisted and cleared
    assert os.path.exists(mod.FAILED_UPLOADS_FILE)
    persisted = Path(mod.FAILED_UPLOADS_FILE).read_text()
    assert "bad_video.mp4" not in persisted


@pytest.mark.asyncio
async def test_recovery_quarantine_on_upload_failure(monkeypatch, tmp_path):
    mod = load_extractor(monkeypatch, tmp_path)

    original = tmp_path / "bad_upload.mp4"
    original.write_bytes(b"bad2")

    converted = tmp_path / "recovery" / "converted2.mp4"

    def fake_convert(path):
        converted.parent.mkdir(parents=True, exist_ok=True)
        converted.write_bytes(b"converted2")
        return str(converted)

    class FailingOps:
        def __init__(self, client):
            self.client = client

        async def upload_media_file(self, target, file_path, caption=None, progress_callback=None):
            raise RuntimeError("upload failed")

    async def fake_target(client=None):
        return "chat123"

    monkeypatch.setattr(mod, "convert_video_for_recovery", fake_convert)
    monkeypatch.setattr(mod, "TelegramOperations", FailingOps)
    monkeypatch.setattr(mod, "ensure_target_entity", fake_target)

    mod.failed_media_files = [
        {
            "file_path": str(original),
            "chat_id": "chat123",
            "caption": "retry me",
            "original_filename": "bad_upload.mp4",
            "status": "pending",
        }
    ]

    await mod._handle_failed_uploads()

    assert len(mod.failed_media_files) == 1
    assert mod.failed_media_files[0]["status"] == "quarantine"
    quarantined_path = Path(mod.QUARANTINE_DIR) / original.name
    assert quarantined_path.exists()
    # Converted file remains for inspection after failure
    assert converted.exists()
