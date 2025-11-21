"""
Comprehensive tests for WebDAV upload processor fix.
Tests the enhanced error handling and queue continuity.
"""

import pytest
import asyncio
import os
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch, call
from telethon.errors import FloodWaitError

from utils.queue_manager import QueueManager
from utils.constants import WEBDAV_DIR


@pytest.fixture
def queue_manager(tmp_path, monkeypatch):
    """Create an isolated QueueManager instance for testing."""
    temp_dir = tmp_path
    monkeypatch.setattr('utils.queue_manager.DOWNLOAD_QUEUE_FILE', str(temp_dir / 'download_queue.json'))
    monkeypatch.setattr('utils.queue_manager.UPLOAD_QUEUE_FILE', str(temp_dir / 'upload_queue.json'))
    monkeypatch.setattr('utils.queue_manager.RETRY_QUEUE_FILE', str(temp_dir / 'retry_queue.json'))
    monkeypatch.setattr('utils.queue_manager.WEBDAV_DIR', str(temp_dir / 'webdav'))
    os.makedirs(temp_dir / 'webdav', exist_ok=True)
    
    manager = QueueManager()
    # Disable automatic processor start for controlled testing
    manager._disable_upload_worker_start = True
    manager.download_persistent.clear()
    manager.upload_persistent.clear()
    return manager


@pytest.fixture
def mock_webdav_client():
    """Create a mock WebDAV client."""
    client = AsyncMock()
    client.walk_files = AsyncMock()
    client.download_file = AsyncMock()
    return client


@pytest.fixture
def mock_telegram_ops():
    """Create mock Telegram operations."""
    ops = AsyncMock()
    ops.upload_media_file = AsyncMock()
    ops.upload_media_grouped = AsyncMock()
    return ops


class TestPersistentQueueSafety:
    """Ensure upload tasks are not lost when the processor encounters errors."""
    
    @pytest.mark.asyncio
    async def test_upload_task_persists_on_processor_error(self, tmp_path, monkeypatch):
        """Upload tasks should remain in persistence if processor errors before completion."""
        # Redirect queue files to temp paths
        monkeypatch.setattr('utils.queue_manager.UPLOAD_QUEUE_FILE', str(tmp_path / 'upload_queue.json'))
        monkeypatch.setattr('utils.queue_manager.DOWNLOAD_QUEUE_FILE', str(tmp_path / 'download_queue.json'))
        monkeypatch.setattr('utils.queue_manager.RETRY_QUEUE_FILE', str(tmp_path / 'retry_queue.json'))
        
        manager = QueueManager()
        
        # Force processor failure
        async def boom(task):
            raise Exception("boom")
        
        manager._execute_upload_task = boom
        
        file_path = tmp_path / "file.jpg"
        file_path.write_bytes(b"fake image data")
        
        task = {
            'type': 'webdav_media_upload',
            'filename': 'file.jpg',
            'file_path': str(file_path),
            'size_bytes': file_path.stat().st_size,
            'retry_count': 0
        }
        
        await manager.add_upload_task(task)
        
        # Wait for processor to handle and acknowledge the task
        await asyncio.wait_for(manager.upload_queue.join(), timeout=1)
        
        # Stop the background worker
        if manager.upload_task:
            manager.upload_task.cancel()
            with suppress(asyncio.CancelledError):
                await manager.upload_task
        
        persisted = manager.upload_persistent.get_items()
        assert len(persisted) == 1, "Task should remain persisted after processor error"
        assert persisted[0]['filename'] == 'file.jpg'
    
    @pytest.mark.asyncio
    async def test_upload_task_removed_after_success(self, tmp_path, monkeypatch):
        """Upload tasks should be removed from persistence after successful execution."""
        monkeypatch.setattr('utils.queue_manager.UPLOAD_QUEUE_FILE', str(tmp_path / 'upload_queue.json'))
        monkeypatch.setattr('utils.queue_manager.DOWNLOAD_QUEUE_FILE', str(tmp_path / 'download_queue.json'))
        monkeypatch.setattr('utils.queue_manager.RETRY_QUEUE_FILE', str(tmp_path / 'retry_queue.json'))
        
        manager = QueueManager()
        
        # Stub upload execution to succeed
        async def succeed(task):
            return
        
        manager._execute_upload_task = succeed
        
        file_path = tmp_path / "file2.mp4"
        file_path.write_bytes(b"fake video data")
        
        task = {
            'type': 'webdav_media_upload',
            'filename': 'file2.mp4',
            'file_path': str(file_path),
            'size_bytes': file_path.stat().st_size,
            'retry_count': 0
        }
        
        await manager.add_upload_task(task)
        
        await asyncio.wait_for(manager.upload_queue.join(), timeout=1)
        
        if manager.upload_task:
            manager.upload_task.cancel()
            with suppress(asyncio.CancelledError):
                await manager.upload_task
        
        assert manager.upload_persistent.get_items() == [], "Persistent queue should be cleared after successful upload"


class TestWebDAVUploadProcessorContinuity:
    """Test that upload processor continues after errors."""
    
    @pytest.mark.asyncio
    async def test_processor_continues_after_exception(self, queue_manager):
        """Test that processor continues to next task after an exception."""
        # Add multiple upload tasks
        tasks = []
        for i in range(5):
            task = {
                'type': 'webdav_media_upload',
                'filename': f'file{i}.jpg',
                'file_path': f'/tmp/file{i}.jpg',
                'size_bytes': 1000,
                'retry_count': 0
            }
            tasks.append(task)
            await queue_manager.add_upload_task(task)
        
        # Mock execute_upload_task to fail on second task
        original_execute = queue_manager._execute_upload_task
        call_count = [0]
        
        async def mock_execute(task):
            call_count[0] += 1
            if call_count[0] == 2:
                # Simulate error on second task
                raise Exception("Simulated upload error")
            # For other tasks, just mark as done
            return
        
        queue_manager._execute_upload_task = mock_execute
        
        # Start processor
        processor_task = asyncio.create_task(queue_manager._process_upload_queue())
        
        # Wait for all tasks to be processed
        await asyncio.sleep(2)
        
        # Cancel processor
        processor_task.cancel()
        try:
            await processor_task
        except asyncio.CancelledError:
            pass
        
        # Verify all 5 tasks were attempted (including the failed one)
        assert call_count[0] == 5, f"Expected 5 tasks processed, got {call_count[0]}"
        
        # Verify queue is empty (all tasks processed)
        assert queue_manager.upload_queue.qsize() == 0, "Upload queue should be empty"
    
    @pytest.mark.asyncio
    async def test_processor_continues_after_flood_wait(self, queue_manager):
        """Test that processor continues after FloodWaitError."""
        # Add multiple upload tasks
        for i in range(3):
            task = {
                'type': 'webdav_media_upload',
                'filename': f'file{i}.mp4',
                'file_path': f'/tmp/file{i}.mp4',
                'size_bytes': 1000,
                'retry_count': 0
            }
            await queue_manager.add_upload_task(task)
        
        # Mock execute_upload_task to raise FloodWaitError on first task
        call_count = [0]
        
        async def mock_execute(task):
            call_count[0] += 1
            if call_count[0] == 1:
                # Simulate FloodWaitError on first task
                error = FloodWaitError(request=None, capture=60)
                error.seconds = 60
                raise error
            return
        
        queue_manager._execute_upload_task = mock_execute
        
        # Start processor
        processor_task = asyncio.create_task(queue_manager._process_upload_queue())
        
        # Wait for processing
        await asyncio.sleep(2)
        
        # Cancel processor
        processor_task.cancel()
        try:
            await processor_task
        except asyncio.CancelledError:
            pass
        
        # Verify all 3 tasks were attempted
        assert call_count[0] == 3, f"Expected 3 tasks processed, got {call_count[0]}"
        
        # Verify queue is empty
        assert queue_manager.upload_queue.qsize() == 0, "Upload queue should be empty"


class TestWebDAVDownloadAndQueue:
    """Test WebDAV download and upload queueing."""
    
    @pytest.mark.asyncio
    async def test_webdav_file_download_queues_upload(self, queue_manager, mock_webdav_client, tmp_path):
        """Test that WebDAV file download successfully queues upload task."""
        # Setup
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")
        
        task = {
            'type': 'webdav_file_download',
            'filename': 'test.jpg',
            'remote_path': '/remote/test.jpg',
            'temp_path': str(test_file),
            'size_bytes': 100,
            'event': None
        }
        
        # Mock WebDAV client
        with patch('utils.webdav_client.get_webdav_client', return_value=mock_webdav_client):
            # Execute download task
            await queue_manager._execute_webdav_file_task(task)
        
        # Verify upload task was queued
        assert queue_manager.upload_queue.qsize() == 1, "Upload task should be queued"
        
        # Verify upload task details
        upload_task = await queue_manager.upload_queue.get()
        assert upload_task['filename'] == 'test.jpg'
        assert upload_task['type'] in ['webdav_media_upload', 'webdav_document_upload']
    
    @pytest.mark.asyncio
    async def test_webdav_walk_discovers_all_files(self, queue_manager, mock_webdav_client):
        """Test that WebDAV walk discovers and queues only media files."""
        # Create mock WebDAV items
        from utils.webdav_client import WebDAVItem
        
        mock_items = [
            WebDAVItem(path=f'/remote/file{i}.jpg', name=f'file{i}.jpg', is_dir=False, size=1000)
            for i in range(28)  # Test with 28 files like in the bug report
        ]
        # Add some non-media files that should be skipped
        mock_items.append(WebDAVItem(path='/remote/readme.txt', name='readme.txt', is_dir=False, size=100))
        mock_items.append(WebDAVItem(path='/remote/data.pdf', name='data.pdf', is_dir=False, size=200))
        
        async def mock_walk_files(path):
            for item in mock_items:
                yield item
        
        mock_webdav_client.walk_files = mock_walk_files
        
        task = {
            'type': 'webdav_walk_download',
            'remote_path': '/remote/',
            'display_name': 'TestFolder',
            'event': None
        }
        
        # Mock WebDAV client
        with patch('utils.webdav_client.get_webdav_client', return_value=mock_webdav_client):
            await queue_manager._execute_webdav_walk_task(task)
        
        # Verify only 28 media files were queued (2 non-media files should be skipped)
        assert queue_manager.download_queue.qsize() == 28, f"Expected 28 download tasks, got {queue_manager.download_queue.qsize()}"

    @pytest.mark.asyncio
    async def test_webdav_resume_skips_redownload(self, queue_manager, mock_webdav_client, tmp_path):
        """Ensure existing downloaded file is reused after crash/restart without re-downloading."""
        queue_manager._disable_upload_worker_start = True
        existing_file = tmp_path / "resume.mp4"
        existing_file.write_bytes(b"cached-data")

        task = {
            'type': 'webdav_file_download',
            'filename': 'resume.mp4',
            'remote_path': '/remote/resume.mp4',
            'temp_path': str(existing_file),
            'size_bytes': existing_file.stat().st_size,
            'event': None
        }

        with patch('utils.webdav_client.get_webdav_client', return_value=mock_webdav_client):
            await queue_manager._execute_webdav_file_task(task)

        # Should not attempt to download again
        mock_webdav_client.download_file.assert_not_awaited()

        # Upload task should still be queued using the existing file
        assert queue_manager.upload_queue.qsize() == 1
        upload_task = await queue_manager.upload_queue.get()
        assert upload_task['file_path'] == str(existing_file)
        assert upload_task['filename'] == 'resume.mp4'
        queue_manager.upload_queue.task_done()


class TestEnhancedLogging:
    """Test that enhanced logging works correctly."""
    
    @pytest.mark.asyncio
    async def test_queue_size_logged_after_error(self, queue_manager, caplog):
        """Test that queue size is logged after errors."""
        import logging
        caplog.set_level(logging.INFO)
        
        # Add tasks
        for i in range(3):
            task = {
                'type': 'webdav_media_upload',
                'filename': f'file{i}.png',
                'file_path': f'/tmp/file{i}.png',
                'size_bytes': 1000,
                'retry_count': 0
            }
            await queue_manager.add_upload_task(task)
        
        # Mock execute to raise error
        async def mock_execute(task):
            raise Exception("Test error")
        
        queue_manager._execute_upload_task = mock_execute
        
        # Start processor
        processor_task = asyncio.create_task(queue_manager._process_upload_queue())
        
        # Wait briefly
        await asyncio.sleep(1)
        
        # Cancel processor
        processor_task.cancel()
        try:
            await processor_task
        except asyncio.CancelledError:
            pass
        
        # Check logs contain queue size information
        log_messages = [record.message for record in caplog.records]
        queue_size_logs = [msg for msg in log_messages if 'Remaining queue size' in msg]
        
        assert len(queue_size_logs) > 0, "Should log queue size after errors"
    
    @pytest.mark.asyncio
    async def test_webdav_download_logging(self, queue_manager, mock_webdav_client, tmp_path, caplog):
        """Test that WebDAV download has proper logging."""
        import logging
        caplog.set_level(logging.INFO)
        
        test_file = tmp_path / "test.jpg"
        
        task = {
            'type': 'webdav_file_download',
            'filename': 'test.jpg',
            'remote_path': '/remote/test.jpg',
            'temp_path': str(test_file),
            'size_bytes': 100,
            'event': None
        }
        
        # Mock download to create file
        async def mock_download(remote_path, dest_path, progress_callback=None):
            with open(dest_path, 'wb') as f:
                f.write(b"test data")
        
        mock_webdav_client.download_file = mock_download
        
        with patch('utils.webdav_client.get_webdav_client', return_value=mock_webdav_client):
            await queue_manager._execute_webdav_file_task(task)
        
        # Check for expected log messages
        log_messages = [record.message for record in caplog.records]
        
        assert any('Starting WebDAV download' in msg for msg in log_messages), "Should log download start"
        assert any('WebDAV download completed' in msg for msg in log_messages), "Should log download completion"
        assert any('Queuing upload task' in msg for msg in log_messages), "Should log upload queueing"


class TestWebDAVSequentialMode:
    """Validate sequential download→upload flow for WebDAV."""

    @pytest.mark.asyncio
    async def test_webdav_sequential_waits_for_upload(self, queue_manager, tmp_path, monkeypatch):
        """Next WebDAV download should not start until the prior upload finishes."""
        # Start fresh upload worker for this test
        if queue_manager.upload_task and not queue_manager.upload_task.done():
            queue_manager.upload_task.cancel()
            with suppress(asyncio.CancelledError):
                await queue_manager.upload_task
        
        queue_manager.webdav_sequential = True
        monkeypatch.setattr('utils.queue_manager.WEBDAV_DIR', str(tmp_path / 'webdav_seq'))
        os.makedirs(tmp_path / 'webdav_seq', exist_ok=True)

        order = []

        async def mock_download(remote_path, dest_path, progress_callback=None):
            order.append(f"download:{os.path.basename(dest_path)}")
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with open(dest_path, 'wb') as f:
                f.write(b"data")

        async def mock_upload(task):
            order.append(f"upload:{task.get('filename')}")
            await asyncio.sleep(0.01)

        mock_webdav_client = AsyncMock()
        mock_webdav_client.download_file = mock_download
        mock_webdav_client.walk_files = AsyncMock()

        queue_manager._execute_upload_task = mock_upload

        # Start the upload worker
        queue_manager.upload_task = asyncio.create_task(queue_manager._process_upload_queue())

        tasks = []
        for name in ("one.mp4", "two.mp4"):
            task = {
                'type': 'webdav_file_download',
                'filename': name,
                'remote_path': f"/remote/{name}",
                'temp_path': str(tmp_path / 'webdav_seq' / name),
                'size_bytes': 10,
                'event': None
            }
            tasks.append(task)
            await queue_manager.download_queue.put(task)
            queue_manager.download_persistent.add_item(task)

        try:
            with patch('utils.webdav_client.get_webdav_client', return_value=mock_webdav_client):
                download_worker = asyncio.create_task(queue_manager._process_download_queue())
                
                # Wait for downloads to complete
                await asyncio.wait_for(queue_manager.download_queue.join(), timeout=5)
                # Wait for uploads to complete
                await asyncio.wait_for(queue_manager.upload_queue.join(), timeout=5)

                download_worker.cancel()
                with suppress(asyncio.CancelledError):
                    await download_worker
        finally:
            if queue_manager.upload_task:
                queue_manager.upload_task.cancel()
                with suppress(asyncio.CancelledError):
                    await queue_manager.upload_task

        assert order.index("upload:one.mp4") < order.index("download:two.mp4"), "Second download should wait for first upload"
        assert order == [
            "download:one.mp4",
            "upload:one.mp4",
            "download:two.mp4",
            "upload:two.mp4",
        ]


class TestErrorRecovery:
    """Test error recovery mechanisms."""
    
    @pytest.mark.asyncio
    async def test_failed_task_added_to_retry_queue(self, queue_manager, tmp_path):
        """Test that failed tasks are added to retry queue."""
        # Create a task that will fail
        task = {
            'type': 'webdav_media_upload',
            'filename': 'test.jpg',
            'file_path': '/nonexistent/file.jpg',  # File doesn't exist
            'size_bytes': 1000,
            'retry_count': 0,
            'event': None
        }
        
        # Mock add_to_retry_queue to track calls
        retry_calls = []
        original_add_retry = queue_manager._add_to_retry_queue
        
        async def mock_add_retry(retry_task):
            retry_calls.append(retry_task)
            await original_add_retry(retry_task)
        
        queue_manager._add_to_retry_queue = mock_add_retry
        
        # Execute task (should fail due to missing file)
        await queue_manager._execute_upload_task(task)
        
        # Verify task was added to retry queue
        assert len(retry_calls) > 0, "Failed task should be added to retry queue"
        assert retry_calls[0]['filename'] == 'test.jpg'
        assert retry_calls[0]['retry_count'] == 1


class TestQueueContinuity:
    """Test that queue processing is continuous."""
    
    @pytest.mark.asyncio
    async def test_all_tasks_processed_despite_errors(self, queue_manager):
        """Test that all tasks are processed even when some fail."""
        # Add 10 tasks
        task_count = 10
        for i in range(task_count):
            task = {
                'type': 'webdav_media_upload',
                'filename': f'file{i}.mp4',
                'file_path': f'/tmp/file{i}.mp4',
                'size_bytes': 1000,
                'retry_count': 0
            }
            await queue_manager.add_upload_task(task)
        
        # Mock execute to fail on even-numbered tasks
        processed_tasks = []
        
        async def mock_execute(task):
            processed_tasks.append(task['filename'])
            # Fail on even-numbered files
            if int(task['filename'].replace('file', '').replace('.txt', '')) % 2 == 0:
                raise Exception(f"Simulated error for {task['filename']}")
        
        queue_manager._execute_upload_task = mock_execute
        
        # Start processor
        processor_task = asyncio.create_task(queue_manager._process_upload_queue())
        
        # Wait for all tasks to be processed
        await asyncio.sleep(3)
        
        # Cancel processor
        processor_task.cancel()
        try:
            await processor_task
        except asyncio.CancelledError:
            pass
        
        # Verify all 10 tasks were attempted
        assert len(processed_tasks) == task_count, f"Expected {task_count} tasks processed, got {len(processed_tasks)}"
        
        # Verify queue is empty
        assert queue_manager.upload_queue.qsize() == 0, "Queue should be empty after processing"


@pytest.mark.asyncio
async def test_integration_webdav_full_workflow(tmp_path, monkeypatch):
    """Integration test: Full WebDAV workflow from discovery to upload."""
    from utils.webdav_client import WebDAVItem
    
    monkeypatch.setattr('utils.queue_manager.DOWNLOAD_QUEUE_FILE', str(tmp_path / 'download_queue.json'))
    monkeypatch.setattr('utils.queue_manager.UPLOAD_QUEUE_FILE', str(tmp_path / 'upload_queue.json'))
    monkeypatch.setattr('utils.queue_manager.RETRY_QUEUE_FILE', str(tmp_path / 'retry_queue.json'))
    monkeypatch.setattr('utils.queue_manager.WEBDAV_DIR', str(tmp_path / 'webdav'))
    os.makedirs(tmp_path / 'webdav', exist_ok=True)

    # Create queue manager
    queue_manager = QueueManager()
    queue_manager._disable_upload_worker_start = True
    queue_manager.download_persistent.clear()
    queue_manager.upload_persistent.clear()
    
    # Create mock WebDAV client
    mock_client = AsyncMock()
    
    # Create 5 mock files
    mock_items = [
        WebDAVItem(path=f'/remote/file{i}.jpg', name=f'file{i}.jpg', is_dir=False, size=1000)
        for i in range(5)
    ]
    
    async def mock_walk_files(path):
        for item in mock_items:
            yield item
    
    mock_client.walk_files = mock_walk_files
    
    # Mock download to create actual files
    async def mock_download(remote_path, dest_path, progress_callback=None):
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, 'wb') as f:
            f.write(b"fake image data")
    
    mock_client.download_file = mock_download
    
    # Execute walk task
    walk_task = {
        'type': 'webdav_walk_download',
        'remote_path': '/remote/',
        'display_name': 'TestFolder',
        'event': None
    }
    
    with patch('utils.webdav_client.get_webdav_client', return_value=mock_client):
        await queue_manager._execute_webdav_walk_task(walk_task)
    
    # Verify 5 download tasks were queued
    assert queue_manager.download_queue.qsize() == 5, "Should queue 5 download tasks"
    
    # Process download tasks
    download_count = 0
    with patch('utils.webdav_client.get_webdav_client', return_value=mock_client):
        while not queue_manager.download_queue.empty():
            task = await queue_manager.download_queue.get()
            await queue_manager._execute_webdav_file_task(task)
            download_count += 1
            queue_manager.download_queue.task_done()
    
    # Verify all downloads processed
    assert download_count == 5, f"Should process 5 downloads, got {download_count}"
    
    # NEW BEHAVIOR: With album batching, 5 files are grouped into 1 grouped upload task
    assert queue_manager.upload_queue.qsize() == 1, f"Should queue 1 grouped upload task, got {queue_manager.upload_queue.qsize()}"
    
    # Verify the grouped task has correct metadata
    upload_task = list(queue_manager.upload_queue)[0]
    assert upload_task['type'] == 'grouped_media', "Should be a grouped media task"
    assert upload_task['is_grouped'] is True, "Task should be marked as grouped"
    assert upload_task['webdav_quiet_mode'] is True, "Should have quiet mode enabled"
    assert len(upload_task['file_paths']) == 5, "Should contain all 5 files in the album"
    assert upload_task['source_webdav'] == 'TestFolder', "Should reference the source folder"
    
    print("✅ Integration test passed: Full WebDAV workflow completed successfully with album batching")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
