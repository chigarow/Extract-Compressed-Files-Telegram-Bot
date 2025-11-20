"""
Test suite for grouped media upload functionality.

This test suite verifies:
1. Files are properly batched by type (images vs videos)
2. Grouped uploads reduce API calls (1 call per group vs N calls for N files)
3. Groups are uploaded with proper captions
4. Rate limiting is reduced with grouped uploads
5. Fallback to individual uploads works if grouped upload fails
6. Cleanup works properly for grouped uploads
"""

import pytest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch, call
from telethon.errors import FloodWaitError

from utils.queue_manager import QueueManager


class TestGroupedMediaUpload:
    """Test grouped media upload functionality."""
    
    @pytest.fixture
    def queue_manager(self):
        """Create a QueueManager instance for testing."""
        return QueueManager()
    
    @pytest.fixture
    def mock_event(self):
        """Create a mock event object."""
        event = MagicMock()
        event.reply = AsyncMock()
        return event
    
    @pytest.fixture
    def test_files(self, tmp_path):
        """Create test image and video files."""
        files = {
            'images': [],
            'videos': []
        }
        
        # Create 3 test images
        for i in range(3):
            img_file = tmp_path / f"image_{i}.jpg"
            img_file.write_text(f"image content {i}")
            files['images'].append(str(img_file))
        
        # Create 2 test videos
        for i in range(2):
            vid_file = tmp_path / f"video_{i}.mp4"
            vid_file.write_text(f"video content {i}")
            files['videos'].append(str(vid_file))
        
        return files
    
    @pytest.mark.asyncio
    async def test_files_batched_by_type(self, queue_manager, test_files, mock_event, tmp_path):
        """Test that extracted files are batched by type (images vs videos)."""
        
        # Create a mock extraction scenario
        extract_path = tmp_path / "extracted"
        extract_path.mkdir()
        
        # Copy test files to extraction path
        all_files = test_files['images'] + test_files['videos']
        extracted_files = []
        for src_file in all_files:
            dest_file = extract_path / os.path.basename(src_file)
            dest_file.write_text(open(src_file).read())
            extracted_files.append(str(dest_file))
        
        # Mock the extraction process
        processing_task = {
            'filename': 'test_archive.zip',
            'temp_archive_path': str(tmp_path / 'test.zip'),
            'event': mock_event
        }
        
        # Create temp archive file
        (tmp_path / 'test.zip').write_text("archive content")
        
        with patch('utils.file_operations.extract_archive_async') as mock_extract:
            mock_extract.return_value = (True, None)
            
            with patch('os.walk') as mock_walk:
                mock_walk.return_value = [(str(extract_path), [], [os.path.basename(f) for f in extracted_files])]
                
                # Spy on add_upload_task to see what gets queued
                original_add = queue_manager.add_upload_task
                upload_tasks = []
                
                async def spy_add_upload(task):
                    upload_tasks.append(task)
                    # Don't actually start the processor
                    return False
                
                queue_manager.add_upload_task = spy_add_upload
                
                try:
                    await queue_manager._process_extraction_and_upload(processing_task)
                    
                    # Should have 2 upload tasks (one for images, one for videos)
                    assert len(upload_tasks) == 2, f"Expected 2 upload tasks, got {len(upload_tasks)}"
                    
                    # Find image and video tasks
                    image_task = next((t for t in upload_tasks if t.get('media_type') == 'images'), None)
                    video_task = next((t for t in upload_tasks if t.get('media_type') == 'videos'), None)
                    
                    assert image_task is not None, "Image upload task not found"
                    assert video_task is not None, "Video upload task not found"
                    
                    # Verify correct number of files in each group
                    assert len(image_task['file_paths']) == 3, "Should have 3 images"
                    assert len(video_task['file_paths']) == 2, "Should have 2 videos"
                    
                    # Verify is_grouped flag
                    assert image_task['is_grouped'] is True
                    assert video_task['is_grouped'] is True
                    
                finally:
                    queue_manager.add_upload_task = original_add
    
    @pytest.mark.asyncio
    async def test_grouped_upload_single_api_call(self, queue_manager, test_files, mock_event):
        """Test that grouped upload makes single API call instead of multiple."""
        
        grouped_task = {
            'type': 'grouped_media',
            'media_type': 'images',
            'event': mock_event,
            'file_paths': test_files['images'],
            'filename': 'test_archive.zip - Images (3 files)',
            'source_archive': 'test_archive.zip',
            'is_grouped': True
        }
        
        with patch('utils.queue_manager.TelegramOperations') as mock_tg_ops_class:
            mock_tg_ops = MagicMock()
            mock_tg_ops.upload_media_grouped = AsyncMock()
            mock_tg_ops.upload_media_file = AsyncMock()
            mock_tg_ops_class.return_value = mock_tg_ops
            
            with patch('utils.queue_manager.get_client'), \
                 patch('utils.queue_manager.ensure_target_entity'), \
                 patch('utils.queue_manager.CacheManager'), \
                 patch('utils.media_processing.needs_video_processing', return_value=False):
                
                await queue_manager._execute_grouped_upload(grouped_task)
                
                # Should call upload_media_grouped exactly once
                assert mock_tg_ops.upload_media_grouped.call_count == 1, \
                    f"Expected 1 call to upload_media_grouped, got {mock_tg_ops.upload_media_grouped.call_count}"
                
                # Should NOT call upload_media_file (individual upload)
                assert mock_tg_ops.upload_media_file.call_count == 0, \
                    "Should not call upload_media_file for grouped uploads"
                
                # Verify all 3 files were passed
                call_args = mock_tg_ops.upload_media_grouped.call_args
                uploaded_files = call_args[0][1]  # Second positional arg is file list
                assert len(uploaded_files) == 3, f"Expected 3 files, got {len(uploaded_files)}"
    
    @pytest.mark.asyncio
    async def test_grouped_upload_with_caption(self, queue_manager, test_files, mock_event):
        """Test that grouped upload includes source archive in caption."""
        
        grouped_task = {
            'type': 'grouped_media',
            'media_type': 'videos',
            'event': mock_event,
            'file_paths': test_files['videos'],
            'filename': 'MyArchive.zip - Videos (2 files)',
            'source_archive': 'MyArchive.zip',
            'is_grouped': True
        }
        
        with patch('utils.queue_manager.TelegramOperations') as mock_tg_ops_class:
            mock_tg_ops = MagicMock()
            mock_tg_ops.upload_media_grouped = AsyncMock()
            mock_tg_ops_class.return_value = mock_tg_ops
            
            with patch('utils.queue_manager.get_client'), \
                 patch('utils.queue_manager.ensure_target_entity'), \
                 patch('utils.queue_manager.CacheManager'), \
                 patch('utils.media_processing.needs_video_processing', return_value=False):
                
                await queue_manager._execute_grouped_upload(grouped_task)
                
                # Verify caption contains source archive
                call_args = mock_tg_ops.upload_media_grouped.call_args
                caption = call_args[1]['caption']  # Keyword arg
                assert 'MyArchive.zip' in caption, f"Caption should contain archive name, got: {caption}"
                assert '📦' in caption, "Caption should have package emoji"
    
    @pytest.mark.asyncio
    async def test_grouped_upload_rate_limit_retry(self, queue_manager, test_files, mock_event):
        """Test that grouped upload handles FloodWaitError and retries."""
        
        grouped_task = {
            'type': 'grouped_media',
            'media_type': 'images',
            'event': mock_event,
            'file_paths': test_files['images'],
            'filename': 'test.zip - Images (3 files)',
            'source_archive': 'test.zip',
            'is_grouped': True,
            'retry_count': 0
        }
        
        flood_error = FloodWaitError(None)
        flood_error.seconds = 300  # 5 minutes
        
        with patch('utils.queue_manager.TelegramOperations') as mock_tg_ops_class:
            mock_tg_ops = MagicMock()
            mock_tg_ops.upload_media_grouped = AsyncMock(side_effect=flood_error)
            mock_tg_ops.upload_media_file = AsyncMock()
            mock_tg_ops_class.return_value = mock_tg_ops
            
            with patch('utils.queue_manager.get_client'), \
                 patch('utils.queue_manager.ensure_target_entity'), \
                 patch('utils.queue_manager.CacheManager'), \
                 patch('utils.media_processing.needs_video_processing', return_value=False), \
                 patch.object(queue_manager, '_add_to_retry_queue', new=AsyncMock()) as mock_retry:
                
                await queue_manager._execute_grouped_upload(grouped_task)
                
                # Should schedule retry
                mock_retry.assert_called_once()
                retry_task = mock_retry.call_args[0][0]
                
                # Verify proper wait time (300s + 5s buffer = 305s)
                import time
                wait_time = retry_task['retry_after'] - time.time()
                assert 303 <= wait_time <= 307, f"Wait time should be ~305s, got {wait_time}s"
                
                # Files should NOT be deleted
                for file_path in test_files['images']:
                    assert os.path.exists(file_path), f"File should not be deleted on rate limit: {file_path}"

                # Ensure fallback individual uploads were never attempted
                mock_tg_ops.upload_media_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_individual_fallback_respects_rate_limit(self, queue_manager, test_files, mock_event):
        """Fallback individual uploads should requeue when FloodWaitError occurs."""

        grouped_task = {
            'type': 'grouped_media',
            'media_type': 'images',
            'event': mock_event,
            'file_paths': test_files['images'].copy(),
            'filename': 'test.zip - Images (3 files)',
            'source_archive': 'test.zip',
            'is_grouped': True,
            'retry_count': 0
        }

        flood_error = FloodWaitError(None)
        flood_error.seconds = 120

        with patch('utils.queue_manager.TelegramOperations') as mock_tg_ops_class:
            mock_tg_ops = MagicMock()
            # Force grouped upload to fail with generic error so fallback kicks in
            mock_tg_ops.upload_media_grouped = AsyncMock(side_effect=RuntimeError('group fail'))
            # First individual upload hits FloodWait
            mock_tg_ops.upload_media_file = AsyncMock(side_effect=flood_error)
            mock_tg_ops_class.return_value = mock_tg_ops

            with patch('utils.queue_manager.get_client'), \
                 patch('utils.queue_manager.ensure_target_entity'), \
                 patch('utils.queue_manager.CacheManager'), \
                 patch('utils.media_processing.needs_video_processing', return_value=False), \
                 patch.object(queue_manager, '_add_to_retry_queue', new=AsyncMock()) as mock_retry:

                await queue_manager._execute_grouped_upload(grouped_task)

                # Should schedule retry due to FloodWait from fallback upload
                mock_retry.assert_called_once()
                retry_task = mock_retry.call_args[0][0]
                assert retry_task['retry_count'] == 1
                # Only first individual upload should have been attempted before propagation
                assert mock_tg_ops.upload_media_file.call_count == 1
    
    @pytest.mark.asyncio
    async def test_grouped_upload_cleans_up_on_success(self, queue_manager, test_files, mock_event):
        """Test that grouped upload cleans up files after successful upload."""
        
        grouped_task = {
            'type': 'grouped_media',
            'media_type': 'images',
            'event': mock_event,
            'file_paths': test_files['images'].copy(),
            'filename': 'test.zip - Images (3 files)',
            'source_archive': 'test.zip',
            'is_grouped': True
        }
        
        with patch('utils.queue_manager.TelegramOperations') as mock_tg_ops_class:
            mock_tg_ops = MagicMock()
            mock_tg_ops.upload_media_grouped = AsyncMock()
            mock_tg_ops_class.return_value = mock_tg_ops
            
            with patch('utils.queue_manager.get_client'), \
                 patch('utils.queue_manager.ensure_target_entity'), \
                 patch('utils.queue_manager.CacheManager'), \
                 patch('utils.media_processing.needs_video_processing', return_value=False):
                
                # Verify files exist before
                for file_path in test_files['images']:
                    assert os.path.exists(file_path), f"File should exist before upload: {file_path}"
                
                await queue_manager._execute_grouped_upload(grouped_task)
                
                # Verify files are deleted after successful upload
                for file_path in test_files['images']:
                    assert not os.path.exists(file_path), f"File should be deleted after upload: {file_path}"
    
    @pytest.mark.asyncio
    async def test_empty_group_skipped(self, queue_manager, mock_event, tmp_path):
        """Test that empty groups are skipped."""
        
        grouped_task = {
            'type': 'grouped_media',
            'media_type': 'images',
            'event': mock_event,
            'file_paths': [],  # Empty list
            'filename': 'test.zip - Images (0 files)',
            'source_archive': 'test.zip',
            'is_grouped': True
        }
        
        with patch('utils.queue_manager.TelegramOperations') as mock_tg_ops_class:
            mock_tg_ops = MagicMock()
            mock_tg_ops.upload_media_grouped = AsyncMock()
            mock_tg_ops_class.return_value = mock_tg_ops
            
            await queue_manager._execute_grouped_upload(grouped_task)
            
            # Should not attempt upload
            mock_tg_ops.upload_media_grouped.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_extraction_folder_cleanup_after_all_groups(self, queue_manager, test_files, mock_event, tmp_path):
        """Test that extraction folder is cleaned up after all groups are uploaded."""
        
        extract_path = tmp_path / "extracted"
        extract_path.mkdir()
        
        # Register 2 groups (images and videos)
        await queue_manager.extraction_cleanup_registry.register_extraction(str(extract_path), 2)
        
        # Upload first group (images)
        image_task = {
            'type': 'grouped_media',
            'media_type': 'images',
            'event': mock_event,
            'file_paths': test_files['images'].copy(),
            'filename': 'test.zip - Images (3 files)',
            'source_archive': 'test.zip',
            'extraction_folder': str(extract_path),
            'is_grouped': True
        }
        
        with patch('utils.queue_manager.TelegramOperations') as mock_tg_ops_class:
            mock_tg_ops = MagicMock()
            mock_tg_ops.upload_media_grouped = AsyncMock()
            mock_tg_ops_class.return_value = mock_tg_ops
            
            with patch('utils.queue_manager.get_client'), \
                 patch('utils.queue_manager.ensure_target_entity'), \
                 patch('utils.queue_manager.CacheManager'), \
                 patch('utils.media_processing.needs_video_processing', return_value=False):
                
                # Upload first group
                await queue_manager._execute_grouped_upload(image_task)
                
                # Folder should still exist (1 of 2 groups done)
                assert extract_path.exists(), "Extraction folder should exist after first group"
                
                # Upload second group (videos)
                video_task = {
                    'type': 'grouped_media',
                    'media_type': 'videos',
                    'event': mock_event,
                    'file_paths': test_files['videos'].copy(),
                    'filename': 'test.zip - Videos (2 files)',
                    'source_archive': 'test.zip',
                    'extraction_folder': str(extract_path),
                    'is_grouped': True
                }
                
                await queue_manager._execute_grouped_upload(video_task)
                
                # Folder should be deleted (2 of 2 groups done)
                assert not extract_path.exists(), "Extraction folder should be deleted after all groups"
    
    @pytest.mark.asyncio
    async def test_only_images_creates_one_group(self, queue_manager, mock_event, tmp_path):
        """Test that archive with only images creates only one group."""
        
        # Create test files - only images
        image_files = []
        for i in range(5):
            img_file = tmp_path / f"image_{i}.jpg"
            img_file.write_text(f"image {i}")
            image_files.append(str(img_file))
        
        extract_path = tmp_path / "extracted"
        extract_path.mkdir()
        
        processing_task = {
            'filename': 'images_only.zip',
            'temp_archive_path': str(tmp_path / 'test.zip'),
            'event': mock_event
        }
        
        (tmp_path / 'test.zip').write_text("archive")
        
        with patch('utils.file_operations.extract_archive_async') as mock_extract:
            mock_extract.return_value = (True, None)
            
            with patch('os.walk') as mock_walk:
                mock_walk.return_value = [(str(extract_path), [], [os.path.basename(f) for f in image_files])]
                
                upload_tasks = []
                
                async def spy_add_upload(task):
                    upload_tasks.append(task)
                    return False
                
                original_add = queue_manager.add_upload_task
                queue_manager.add_upload_task = spy_add_upload
                
                try:
                    await queue_manager._process_extraction_and_upload(processing_task)
                    
                    # Should have only 1 upload task (images only)
                    assert len(upload_tasks) == 1, f"Expected 1 upload task, got {len(upload_tasks)}"
                    assert upload_tasks[0]['media_type'] == 'images'
                    assert len(upload_tasks[0]['file_paths']) == 5
                    
                finally:
                    queue_manager.add_upload_task = original_add


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
