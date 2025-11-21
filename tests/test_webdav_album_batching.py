"""
Unit tests for WebDAV album batching and quiet notification features.

Tests cover:
- WebDAVAlbumBatcher class functionality
- Image/video separation and ordering
- 10-item album batching
- Auto-flush when all files complete
- Quiet mode notification suppression
- Integration with retry/flood-wait handling
"""

import pytest
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from utils.queue_manager import QueueManager, WebDAVAlbumBatcher, TELEGRAM_ALBUM_MAX_FILES


@pytest.fixture
def mock_event():
    """Create a mock Telegram event with reply capability."""
    event = AsyncMock()
    event.reply = AsyncMock()
    return event


@pytest.fixture
def queue_manager(tmp_path):
    """Create a QueueManager instance for testing."""
    # Patch persistent storage paths to use tmp_path
    with patch('utils.queue_manager.DOWNLOAD_QUEUE_FILE', str(tmp_path / 'download_queue.json')), \
         patch('utils.queue_manager.UPLOAD_QUEUE_FILE', str(tmp_path / 'upload_queue.json')):
        qm = QueueManager()
        # Replace add_upload_task with a mock to track calls
        qm.add_upload_task = AsyncMock()
        return qm


@pytest.fixture
def batcher(queue_manager, mock_event):
    """Create a WebDAVAlbumBatcher instance for testing."""
    return WebDAVAlbumBatcher(queue_manager, mock_event, "test_webdav_source")


class TestWebDAVAlbumBatcher:
    """Test WebDAVAlbumBatcher class functionality."""
    
    @pytest.mark.asyncio
    async def test_batcher_initialization(self, batcher, queue_manager, mock_event):
        """Test batcher initializes with correct attributes."""
        assert batcher.queue_manager == queue_manager
        assert batcher.event == mock_event
        assert batcher.display_name == "test_webdav_source"
        assert batcher.buffers == {'images': [], 'videos': []}
        assert batcher.batch_counters == {'images': 0, 'videos': 0}
        assert batcher.total_queued == 0
        assert batcher.expected_files == 0
        assert batcher.completed_files == 0
    
    @pytest.mark.asyncio
    async def test_set_expected_files(self, batcher):
        """Test setting expected file count."""
        batcher.set_expected_files(25)
        assert batcher.expected_files == 25
    
    @pytest.mark.asyncio
    async def test_add_image_file(self, batcher, tmp_path):
        """Test adding an image file to batcher."""
        batcher.set_expected_files(5)
        
        # Create a temp image file
        image_path = tmp_path / "test.jpg"
        image_path.write_text("fake image data")
        
        await batcher.add_file(str(image_path), "test.jpg", "/remote/test.jpg", 1024)
        
        assert batcher.completed_files == 1
        assert len(batcher.buffers['images']) == 1
        assert len(batcher.buffers['videos']) == 0
        assert batcher.buffers['images'][0]['filename'] == "test.jpg"
    
    @pytest.mark.asyncio
    async def test_add_video_file(self, batcher, tmp_path):
        """Test adding a video file to batcher."""
        batcher.set_expected_files(5)
        
        # Create a temp video file
        video_path = tmp_path / "test.mp4"
        video_path.write_text("fake video data")
        
        await batcher.add_file(str(video_path), "test.mp4", "/remote/test.mp4", 2048)
        
        assert batcher.completed_files == 1
        assert len(batcher.buffers['images']) == 0
        assert len(batcher.buffers['videos']) == 1
        assert batcher.buffers['videos'][0]['filename'] == "test.mp4"
    
    @pytest.mark.asyncio
    async def test_auto_dispatch_at_10_items(self, batcher, tmp_path):
        """Test auto-dispatch when buffer reaches TELEGRAM_ALBUM_MAX_FILES (10)."""
        batcher.set_expected_files(15)
        
        # Add 10 image files
        for i in range(10):
            image_path = tmp_path / f"image{i}.jpg"
            image_path.write_text(f"fake image {i}")
            await batcher.add_file(str(image_path), f"image{i}.jpg", f"/remote/image{i}.jpg", 1024)
        
        # Should have dispatched once
        assert batcher.queue_manager.add_upload_task.call_count == 1
        
        # Buffer should be empty after dispatch
        assert len(batcher.buffers['images']) == 0
        assert batcher.batch_counters['images'] == 1
    
    @pytest.mark.asyncio
    async def test_image_video_separation(self, batcher, tmp_path):
        """Test that images and videos are batched separately."""
        batcher.set_expected_files(15)
        
        # Add 5 images
        for i in range(5):
            image_path = tmp_path / f"image{i}.jpg"
            image_path.write_text(f"fake image {i}")
            await batcher.add_file(str(image_path), f"image{i}.jpg", f"/remote/image{i}.jpg", 1024)
        
        # Add 5 videos
        for i in range(5):
            video_path = tmp_path / f"video{i}.mp4"
            video_path.write_text(f"fake video {i}")
            await batcher.add_file(str(video_path), f"video{i}.mp4", f"/remote/video{i}.mp4", 2048)
        
        # Should not have auto-dispatched (each type has less than 10)
        assert batcher.queue_manager.add_upload_task.call_count == 0
        
        # Check buffers
        assert len(batcher.buffers['images']) == 5
        assert len(batcher.buffers['videos']) == 5
    
    @pytest.mark.asyncio
    async def test_flush_dispatches_all_buffers(self, batcher, tmp_path):
        """Test flush dispatches images first, then videos."""
        batcher.set_expected_files(8)
        
        # Add 3 images
        for i in range(3):
            image_path = tmp_path / f"image{i}.jpg"
            image_path.write_text(f"fake image {i}")
            await batcher.add_file(str(image_path), f"image{i}.jpg", f"/remote/image{i}.jpg", 1024)
        
        # Add 5 videos
        for i in range(5):
            video_path = tmp_path / f"video{i}.mp4"
            video_path.write_text(f"fake video {i}")
            await batcher.add_file(str(video_path), f"video{i}.mp4", f"/remote/video{i}.mp4", 2048)
        
        # Manually flush
        await batcher.flush()
        
        # Should have dispatched both types
        assert batcher.queue_manager.add_upload_task.call_count == 2
        
        # Check call order (images first, then videos)
        calls = batcher.queue_manager.add_upload_task.call_args_list
        first_call_task = calls[0][0][0]
        second_call_task = calls[1][0][0]
        
        assert first_call_task['media_type'] == 'images'
        assert len(first_call_task['file_paths']) == 3
        
        assert second_call_task['media_type'] == 'videos'
        assert len(second_call_task['file_paths']) == 5
    
    @pytest.mark.asyncio
    async def test_auto_flush_when_all_files_complete(self, batcher, tmp_path):
        """Test auto-flush when all expected files are downloaded."""
        batcher.set_expected_files(3)
        
        # Add 2 images
        for i in range(2):
            image_path = tmp_path / f"image{i}.jpg"
            image_path.write_text(f"fake image {i}")
            await batcher.add_file(str(image_path), f"image{i}.jpg", f"/remote/image{i}.jpg", 1024)
        
        # Should not have auto-flushed yet
        assert batcher.queue_manager.add_upload_task.call_count == 0
        
        # Add 1 video (completes expected count)
        video_path = tmp_path / "video0.mp4"
        video_path.write_text("fake video")
        await batcher.add_file(str(video_path), "video0.mp4", "/remote/video0.mp4", 2048)
        
        # Should have auto-flushed
        assert batcher.queue_manager.add_upload_task.call_count == 2  # images + videos
    
    @pytest.mark.asyncio
    async def test_completion_notification_sent(self, batcher, tmp_path, mock_event):
        """Test completion notification is sent after flush."""
        batcher.set_expected_files(2)
        
        # Add files
        image_path = tmp_path / "image.jpg"
        image_path.write_text("fake image")
        await batcher.add_file(str(image_path), "image.jpg", "/remote/image.jpg", 1024)
        
        video_path = tmp_path / "video.mp4"
        video_path.write_text("fake video")
        await batcher.add_file(str(video_path), "video.mp4", "/remote/video.mp4", 2048)
        
        # Auto-flush should have triggered
        # Check completion notification was sent
        assert mock_event.reply.called
        completion_msg = mock_event.reply.call_args[0][0]
        assert "All media from test_webdav_source has been uploaded" in completion_msg
        assert "2 albums" in completion_msg
    
    @pytest.mark.asyncio
    async def test_grouped_upload_task_metadata(self, batcher, tmp_path):
        """Test grouped upload task has correct metadata."""
        batcher.set_expected_files(2)
        
        # Add files
        for i in range(2):
            image_path = tmp_path / f"image{i}.jpg"
            image_path.write_text(f"fake image {i}")
            await batcher.add_file(str(image_path), f"image{i}.jpg", f"/remote/image{i}.jpg", 1024)
        
        # Check task metadata
        assert batcher.queue_manager.add_upload_task.call_count == 1
        task = batcher.queue_manager.add_upload_task.call_args[0][0]
        
        assert task['type'] == 'grouped_media'
        assert task['media_type'] == 'images'
        assert task['source_webdav'] == 'test_webdav_source'
        assert task['is_grouped'] is True
        assert task['cleanup_file_paths'] is True
        assert task['webdav_quiet_mode'] is True
        assert task['retry_count'] == 0
        assert len(task['file_paths']) == 2


class TestWebDAVWalkTaskIntegration:
    """Test WebDAV walk task creates and manages batchers."""
    
    @pytest.mark.asyncio
    async def test_walk_creates_batcher(self, queue_manager, mock_event, tmp_path):
        """Test walk task creates a batcher for the source."""
        # Mock file items
        class FileItem:
            def __init__(self, path, size):
                self.path = path
                self.size = size
        
        # Create async generator for walk_files
        async def mock_walk_generator(remote_path):
            files = [
                FileItem('/remote/image1.jpg', 1024),
                FileItem('/remote/image2.jpg', 2048),
            ]
            for f in files:
                yield f
        
        # Mock WebDAV client
        mock_client = AsyncMock()
        mock_client.walk_files = mock_walk_generator
        
        # Mock get_webdav_client (it's imported inside the method from .webdav_client)
        async def mock_get_webdav_client():
            return mock_client
        
        with patch('utils.webdav_client.get_webdav_client', new=mock_get_webdav_client):
            task = {
                'type': 'webdav_walk',
                'remote_path': '/remote',
                'display_name': 'test_source',
                'event': mock_event
            }
            
            await queue_manager._execute_webdav_walk_task(task)
            
            # Check batcher was created
            assert 'test_source' in queue_manager.webdav_batchers
            batcher = queue_manager.webdav_batchers['test_source']
            assert batcher.expected_files == 2


class TestWebDAVQuietModeNotifications:
    """Test notification suppression for WebDAV quiet mode uploads."""
    
    @pytest.mark.asyncio
    async def test_quiet_mode_suppresses_upload_start_notification(self, queue_manager, mock_event, tmp_path):
        """Test quiet mode suppresses upload start notification."""
        # Create test files
        files = []
        for i in range(3):
            file_path = tmp_path / f"image{i}.jpg"
            file_path.write_text(f"fake image {i}")
            files.append(str(file_path))
        
        # Create quiet mode task
        task = {
            'type': 'grouped_media',
            'media_type': 'images',
            'event': mock_event,
            'file_paths': files,
            'filename': 'test_album',
            'is_grouped': True,
            'webdav_quiet_mode': True
        }
        
        # Mock dependencies
        with patch('utils.queue_manager.get_client') as mock_get_client, \
             patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops_class, \
             patch('utils.queue_manager.ensure_target_entity', new_callable=AsyncMock) as mock_target, \
             patch('utils.queue_manager.CacheManager'):
            
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_target.return_value = AsyncMock()
            
            mock_telegram_ops = AsyncMock()
            mock_telegram_ops.upload_media_grouped = AsyncMock()
            mock_telegram_ops_class.return_value = mock_telegram_ops
            
            await queue_manager._execute_grouped_upload(task)
            
            # Should NOT have called reply (quiet mode)
            assert not mock_event.reply.called
    
    @pytest.mark.asyncio
    async def test_non_quiet_mode_shows_upload_notification(self, queue_manager, mock_event, tmp_path):
        """Test non-quiet mode shows upload notifications."""
        # Create test files
        files = []
        for i in range(3):
            file_path = tmp_path / f"image{i}.jpg"
            file_path.write_text(f"fake image {i}")
            files.append(str(file_path))
        
        # Create normal task (no quiet mode)
        task = {
            'type': 'grouped_media',
            'media_type': 'images',
            'event': mock_event,
            'file_paths': files,
            'filename': 'test_album',
            'is_grouped': True,
            'webdav_quiet_mode': False  # Explicit non-quiet mode
        }
        
        # Mock dependencies
        with patch('utils.queue_manager.get_client') as mock_get_client, \
             patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops_class, \
             patch('utils.queue_manager.ensure_target_entity', new_callable=AsyncMock) as mock_target, \
             patch('utils.queue_manager.CacheManager'):
            
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_target.return_value = AsyncMock()
            
            mock_telegram_ops = AsyncMock()
            mock_telegram_ops.upload_media_grouped = AsyncMock()
            mock_telegram_ops_class.return_value = mock_telegram_ops
            
            await queue_manager._execute_grouped_upload(task)
            
            # Should have called reply (non-quiet mode)
            assert mock_event.reply.called


class TestWebDAVBatchingEdgeCases:
    """Test edge cases and error scenarios."""
    
    @pytest.mark.asyncio
    async def test_empty_batcher_flush(self, batcher):
        """Test flushing an empty batcher doesn't error."""
        batcher.set_expected_files(0)
        await batcher.flush()
        
        # Should not have dispatched anything
        assert batcher.queue_manager.add_upload_task.call_count == 0
    
    @pytest.mark.asyncio
    async def test_mixed_media_batching(self, batcher, tmp_path):
        """Test batching with mixed image/video files."""
        batcher.set_expected_files(20)
        
        # Add 15 images (will trigger one batch at 10)
        for i in range(15):
            image_path = tmp_path / f"image{i}.jpg"
            image_path.write_text(f"fake image {i}")
            await batcher.add_file(str(image_path), f"image{i}.jpg", f"/remote/image{i}.jpg", 1024)
        
        # Add 5 videos
        for i in range(5):
            video_path = tmp_path / f"video{i}.mp4"
            video_path.write_text(f"fake video {i}")
            await batcher.add_file(str(video_path), f"video{i}.mp4", f"/remote/video{i}.mp4", 2048)
        
        # Should have auto-dispatched images once (at 10 items)
        # Then auto-flushed remaining 5 images + 5 videos when expected count reached
        assert batcher.queue_manager.add_upload_task.call_count == 3
        
        # Check batches
        calls = batcher.queue_manager.add_upload_task.call_args_list
        
        # First batch: 10 images
        assert calls[0][0][0]['media_type'] == 'images'
        assert len(calls[0][0][0]['file_paths']) == 10
        
        # Second batch (auto-flush): 5 images
        assert calls[1][0][0]['media_type'] == 'images'
        assert len(calls[1][0][0]['file_paths']) == 5
        
        # Third batch (auto-flush): 5 videos
        assert calls[2][0][0]['media_type'] == 'videos'
        assert len(calls[2][0][0]['file_paths']) == 5
    
    @pytest.mark.asyncio
    async def test_batcher_without_event(self, queue_manager):
        """Test batcher works without an event (background processing)."""
        batcher = WebDAVAlbumBatcher(queue_manager, None, "background_source")
        batcher.set_expected_files(1)
        
        # Should not error when event is None
        await batcher.flush()
        
        # No exception should be raised


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
