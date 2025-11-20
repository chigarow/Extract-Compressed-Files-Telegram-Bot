"""Tests for extraction failure notifications and cleanup behavior."""

import os
import pytest
from unittest.mock import AsyncMock

from utils.queue_manager import QueueManager


@pytest.mark.asyncio
async def test_handle_extraction_failure_notifies_and_cleans(tmp_path):
    """Ensure failures notify the user and cleanup both archive and extract dir."""
    queue_manager = QueueManager()
    archive_path = tmp_path / "torbox_archive.zip"
    archive_path.write_text("data")
    extract_dir = tmp_path / "extracted_torbox_archive"
    extract_dir.mkdir()
    (extract_dir / "file.txt").write_text("content")
    event = AsyncMock()
    event.reply = AsyncMock()

    await queue_manager._handle_extraction_failure(
        filename="torbox_archive.zip",
        error_msg="Test failure",
        temp_archive_path=str(archive_path),
        extract_path=str(extract_dir),
        event=event
    )

    event.reply.assert_awaited()
    message = event.reply.await_args.args[0]
    assert "Extraction failed" in message
    assert "Test failure" in message
    assert not archive_path.exists()
    assert not extract_dir.exists()


@pytest.mark.asyncio
async def test_handle_extraction_failure_disk_full_hint(tmp_path):
    """Disk full errors should include user guidance after notification."""
    queue_manager = QueueManager()
    archive_path = tmp_path / "big_archive.zip"
    archive_path.write_text("data")
    extract_dir = tmp_path / "extracted_big_archive"
    extract_dir.mkdir()
    event = AsyncMock()
    event.reply = AsyncMock()

    await queue_manager._handle_extraction_failure(
        filename="big_archive.zip",
        error_msg="zipfile extraction failed: [Errno 28] No space left on device",
        temp_archive_path=str(archive_path),
        extract_path=str(extract_dir),
        event=event
    )

    event.reply.assert_awaited()
    message = event.reply.await_args.args[0]
    assert "Please free up storage space" in message
    assert not os.path.exists(archive_path)
    assert not os.path.exists(extract_dir)
