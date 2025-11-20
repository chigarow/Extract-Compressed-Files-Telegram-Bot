
import asyncio
import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from utils.queue_manager import QueueManager, TELEGRAM_ALBUM_MAX_FILES
from utils.streaming_extractor import StreamingExtractor

@pytest.fixture
def mock_event():
    """Fixture for a mock Telethon event."""
    event = AsyncMock()
    event.reply = AsyncMock()
    return event

@pytest.fixture
def queue_manager(event_loop):
    """Fixture for a QueueManager instance."""
    with patch('utils.queue_manager.PersistentQueue'):
        qm = QueueManager(client=AsyncMock())
        # Set the loop for the queue manager
        asyncio.set_event_loop(event_loop)
        qm._skip_upload_idle_wait = True  # avoid waiting for idle uploads since workers are mocked out
        qm._disable_upload_worker_start = True
        yield qm

@pytest.mark.asyncio
async def test_archive_cleanup_after_multi_batch_streaming_upload(queue_manager, mock_event, tmp_path):
    """
    Tests that the original archive is cleaned up correctly after a streaming
    extraction that produces multiple batches of both images and videos.
    """
    archive_name = "test_archive.zip"
    archive_path = tmp_path / archive_name
    archive_path.touch()  # Create dummy archive file

    num_images = TELEGRAM_ALBUM_MAX_FILES + 5  # e.g., 15 -> 2 batches
    num_videos = TELEGRAM_ALBUM_MAX_FILES * 2 + 2 # e.g., 22 -> 3 batches
    expected_image_batches = 2
    expected_video_batches = 3
    expected_total_batches = expected_image_batches + expected_video_batches

    # Mock StreamingExtractor
    mock_extractor_instance = MagicMock(spec=StreamingExtractor)
    mock_extractor_instance.get_total_files_by_type.side_effect = lambda t: num_images if t == 'images' else num_videos
    
    async def mock_stream_entries(*args, **kwargs):
        for i in range(num_images):
            entry = MagicMock()
            entry.media_type = 'images'
            entry.temp_path = f"/tmp/img_{i}.jpg"
            entry.entry_name = f"img_{i}.jpg"
            yield entry
        for i in range(num_videos):
            entry = MagicMock()
            entry.media_type = 'videos'
            entry.temp_path = f"/tmp/vid_{i}.mp4"
            entry.entry_name = f"vid_{i}.mp4"
            yield entry

    mock_extractor_instance.stream_entries = mock_stream_entries
    mock_extractor_instance.manifest_path = "/tmp/manifest.json"
    mock_extractor_instance.finalize = MagicMock()

    with patch('utils.queue_manager.StreamingExtractor', return_value=mock_extractor_instance), \
         patch('asyncio.create_task', new_callable=MagicMock) as mock_create_task:

        # Start the processing
        processing_task = {
            'filename': archive_name,
            'temp_archive_path': str(archive_path),
            'event': mock_event
        }
        
        await queue_manager._process_streaming_archive(processing_task)

        # Verify that the upload processor was not started
        mock_create_task.assert_not_called()

        # Verify that the archive was registered with the correct number of batches
        assert str(archive_path) in queue_manager.archive_cleanup_registry.registry
        registry_entry = queue_manager.archive_cleanup_registry.registry[str(archive_path)]
        assert registry_entry['total_batches'] == expected_total_batches
        assert registry_entry['completed_batches'] == 0

        # Simulate the completion of all upload tasks
        upload_tasks = []
        while not queue_manager.upload_queue.empty():
            upload_tasks.append(queue_manager.upload_queue.get_nowait())

        assert len(upload_tasks) == expected_total_batches

        # Assert that the archive file still exists before marking batches complete
        assert archive_path.exists()

        with patch('utils.queue_manager.os.remove') as mock_os_remove:
            # Mark each batch as completed
            for i, task in enumerate(upload_tasks):
                await queue_manager.archive_cleanup_registry.mark_batch_completed(task['source_archive_path'])
                
                registry_entry = queue_manager.archive_cleanup_registry.registry.get(str(archive_path))
                if i < expected_total_batches - 1:
                    # The archive should not be deleted until the last batch is marked
                    mock_os_remove.assert_not_called()
                    assert registry_entry is not None
                    assert registry_entry['completed_batches'] == i + 1
                else:
                    # Last batch, archive should be deleted
                    mock_os_remove.assert_called_once_with(str(archive_path))
                    assert registry_entry is None # Entry should be removed after cleanup

            # Final check to ensure the archive file was "deleted"
            mock_os_remove.assert_called_once_with(str(archive_path))

    assert not queue_manager.archive_cleanup_registry.registry # Registry should be empty
