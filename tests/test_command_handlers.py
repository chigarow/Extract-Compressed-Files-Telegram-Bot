"""
Tests for command handlers.
"""

import asyncio
import json
import os
from unittest.mock import AsyncMock, patch, Mock

import pytest

from utils.command_handlers import handle_queue_command


@pytest.fixture
def mock_event():
    """Provides a mock event with an async reply method."""
    event = AsyncMock()
    event.reply = AsyncMock()
    return event


@pytest.mark.asyncio
async def test_handle_queue_command_with_streaming_progress(mock_event, tmp_path):
    """
    Verify that the queue command correctly reports the progress
    of an in-flight streaming extraction.
    """
    # 1. Arrange
    # Create a temporary directory for manifests
    manifest_dir = tmp_path / "streaming_manifests"
    manifest_dir.mkdir()
    
    # Create a fake manifest file
    archive_name = "my_test_archive.zip"
    manifest_path = manifest_dir / f"{archive_name}.json"
    manifest_data = {
        "total_files": 150,
        "processed": [f"file_{i}.jpg" for i in range(25)]
    }
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest_data, f)

    # Mock dependencies that are not under test
    mock_queue_manager = Mock()
    mock_queue_manager.get_queue_status.return_value = {
        'download_queue_size': 0,
        'upload_queue_size': 0,
        'download_semaphore_available': 2,
        'upload_semaphore_available': 2,
        'download_task_running': False,
        'upload_task_running': False,
    }
    
    mock_processing_queue = Mock()
    mock_processing_queue.get_queue_size.return_value = 0
    mock_processing_queue.get_current_processing.return_value = None

    with patch('utils.command_handlers.STREAMING_MANIFEST_DIR', str(manifest_dir)), \
         patch('utils.command_handlers.get_queue_manager', return_value=mock_queue_manager), \
         patch('utils.command_handlers.get_processing_queue', return_value=mock_processing_queue), \
         patch('utils.command_handlers.pending_password', None):

        # 2. Act
        await handle_queue_command(mock_event)

    # 3. Assert
    mock_event.reply.assert_called_once()
    reply_text = mock_event.reply.call_args[0][0]

    # Check for the key parts of the progress report
    assert "Streaming Extraction Progress" in reply_text
    assert f"Stream-Extracting: **{archive_name}**" in reply_text
    assert "Progress: 25/150 files (16.7%)" in reply_text
