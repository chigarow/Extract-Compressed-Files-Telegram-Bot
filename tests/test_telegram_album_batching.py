"""
Unit tests for Telegram album batching (10-file limit per grouped upload).

Tests the implementation of Telegram's hard limit of 10 media files per album,
ensuring large media groups are properly split into batches.

Reference: https://limits.tginfo.me/en
Telegram Limit: "Photos and videos in one message (album) up to 10 pieces"
"""

import pytest
import os
import tempfile
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from utils.queue_manager import QueueManager, TELEGRAM_ALBUM_MAX_FILES


class TestTelegramAlbumBatching:
    """Test batching of large media groups to respect Telegram's 10-file album limit."""
    
    def test_telegram_album_limit_constant(self):
        """Verify TELEGRAM_ALBUM_MAX_FILES constant is set correctly."""
        assert TELEGRAM_ALBUM_MAX_FILES == 10, "Telegram album limit should be 10 files"
    
    def test_small_group_no_batching(self):
        """Test that groups with <= 10 files are not batched."""
        queue_manager = QueueManager()
        
        # Create 5 image files (under limit)
        upload_items = []
        for i in range(5):
            upload_items.append({
                'type': 'extracted_file',
                'file_path': f'/tmp/test_{i}.jpg',
                'source_archive': 'test.zip',
                'extraction_folder': '/tmp/extracted'
            })
        
        # Mock os.path.exists to return True
        with patch('os.path.exists', return_value=True):
            grouped_tasks, individual_tasks = queue_manager._regroup_restored_uploads(upload_items)
        
        # Should create 1 group with 5 files (no batching needed)
        assert len(grouped_tasks) == 1
        assert len(grouped_tasks[0]['file_paths']) == 5
        assert 'Batch' not in grouped_tasks[0]['filename']
    
    def test_exactly_ten_files_no_batching(self):
        """Test that exactly 10 files don't get batched."""
        queue_manager = QueueManager()
        
        # Create exactly 10 image files
        upload_items = []
        for i in range(10):
            upload_items.append({
                'type': 'extracted_file',
                'file_path': f'/tmp/test_{i}.jpg',
                'source_archive': 'test.zip',
                'extraction_folder': '/tmp/extracted'
            })
        
        with patch('os.path.exists', return_value=True):
            grouped_tasks, individual_tasks = queue_manager._regroup_restored_uploads(upload_items)
        
        # Should create 1 group with exactly 10 files
        assert len(grouped_tasks) == 1
        assert len(grouped_tasks[0]['file_paths']) == 10
        assert 'Batch' not in grouped_tasks[0]['filename']
    
    def test_eleven_files_creates_two_batches(self):
        """Test that 11 files are split into 2 batches (10 + 1)."""
        queue_manager = QueueManager()
        
        # Create 11 image files (exceeds limit by 1)
        upload_items = []
        for i in range(11):
            upload_items.append({
                'type': 'extracted_file',
                'file_path': f'/tmp/test_{i}.jpg',
                'source_archive': 'test.zip',
                'extraction_folder': '/tmp/extracted'
            })
        
        with patch('os.path.exists', return_value=True):
            grouped_tasks, individual_tasks = queue_manager._regroup_restored_uploads(upload_items)
        
        # Should create 2 batches
        assert len(grouped_tasks) == 2
        
        # First batch: 10 files
        assert len(grouped_tasks[0]['file_paths']) == 10
        assert 'Batch 1/2' in grouped_tasks[0]['filename']
        assert grouped_tasks[0]['batch_info']['batch_num'] == 1
        assert grouped_tasks[0]['batch_info']['total_batches'] == 2
        
        # Second batch: 1 file
        assert len(grouped_tasks[1]['file_paths']) == 1
        assert 'Batch 2/2' in grouped_tasks[1]['filename']
        assert grouped_tasks[1]['batch_info']['batch_num'] == 2
        assert grouped_tasks[1]['batch_info']['total_batches'] == 2
    
    def test_large_group_multiple_batches(self):
        """Test that large groups (2726 files) are split into many batches."""
        queue_manager = QueueManager()
        
        # Create 2726 image files (real-world scenario from user's logs)
        upload_items = []
        for i in range(2726):
            upload_items.append({
                'type': 'extracted_file',
                'file_path': f'/tmp/test_{i}.jpg',
                'source_archive': 'PrincessAlura.zip',
                'extraction_folder': '/tmp/extracted_PrincessAlura'
            })
        
        with patch('os.path.exists', return_value=True):
            grouped_tasks, individual_tasks = queue_manager._regroup_restored_uploads(upload_items)
        
        # Calculate expected batches: ceil(2726 / 10) = 273 batches
        expected_batches = (2726 + TELEGRAM_ALBUM_MAX_FILES - 1) // TELEGRAM_ALBUM_MAX_FILES
        assert expected_batches == 273
        
        # Should create 273 batches
        assert len(grouped_tasks) == expected_batches
        
        # Verify each batch
        total_files = 0
        for i, batch in enumerate(grouped_tasks):
            batch_num = i + 1
            
            # All batches except last should have exactly 10 files
            if batch_num < expected_batches:
                assert len(batch['file_paths']) == TELEGRAM_ALBUM_MAX_FILES
            else:
                # Last batch has remainder: 2726 % 10 = 6 files
                assert len(batch['file_paths']) == 2726 % TELEGRAM_ALBUM_MAX_FILES
            
            total_files += len(batch['file_paths'])
            
            # Verify batch metadata
            assert f'Batch {batch_num}/{expected_batches}' in batch['filename']
            assert batch['batch_info']['batch_num'] == batch_num
            assert batch['batch_info']['total_batches'] == expected_batches
        
        # Verify total files preserved
        assert total_files == 2726
    
    def test_mixed_images_and_videos_batching(self):
        """Test that images and videos are batched separately."""
        queue_manager = QueueManager()
        
        # Create 25 images and 15 videos
        upload_items = []
        for i in range(25):
            upload_items.append({
                'type': 'extracted_file',
                'file_path': f'/tmp/image_{i}.jpg',
                'source_archive': 'mixed.zip',
                'extraction_folder': '/tmp/extracted_mixed'
            })
        for i in range(15):
            upload_items.append({
                'type': 'extracted_file',
                'file_path': f'/tmp/video_{i}.mp4',
                'source_archive': 'mixed.zip',
                'extraction_folder': '/tmp/extracted_mixed'
            })
        
        with patch('os.path.exists', return_value=True):
            grouped_tasks, individual_tasks = queue_manager._regroup_restored_uploads(upload_items)
        
        # Images: 25 files → 3 batches (10, 10, 5)
        # Videos: 15 files → 2 batches (10, 5)
        # Total: 5 batches
        assert len(grouped_tasks) == 5
        
        # Count image and video batches
        image_batches = [t for t in grouped_tasks if t['media_type'] == 'images']
        video_batches = [t for t in grouped_tasks if t['media_type'] == 'videos']
        
        assert len(image_batches) == 3
        assert len(video_batches) == 2
        
        # Verify image batches
        assert len(image_batches[0]['file_paths']) == 10
        assert len(image_batches[1]['file_paths']) == 10
        assert len(image_batches[2]['file_paths']) == 5
        
        # Verify video batches
        assert len(video_batches[0]['file_paths']) == 10
        assert len(video_batches[1]['file_paths']) == 5
    
    def test_batch_info_metadata_preserved(self):
        """Test that batch_info metadata is correctly added to batched tasks."""
        queue_manager = QueueManager()
        
        # Create 35 images
        upload_items = []
        for i in range(35):
            upload_items.append({
                'type': 'extracted_file',
                'file_path': f'/tmp/test_{i}.jpg',
                'source_archive': 'test.zip',
                'extraction_folder': '/tmp/extracted'
            })
        
        with patch('os.path.exists', return_value=True):
            grouped_tasks, individual_tasks = queue_manager._regroup_restored_uploads(upload_items)
        
        # 35 files → 4 batches (10, 10, 10, 5)
        assert len(grouped_tasks) == 4
        
        for i, task in enumerate(grouped_tasks):
            batch_num = i + 1
            
            # Verify batch_info exists
            assert 'batch_info' in task
            assert task['batch_info']['batch_num'] == batch_num
            assert task['batch_info']['total_batches'] == 4
            
            # Verify filename includes batch info
            assert f'Batch {batch_num}/4' in task['filename']
    
    def test_source_archive_preserved_in_batches(self):
        """Test that source_archive metadata is preserved across all batches."""
        queue_manager = QueueManager()
        
        # Create 20 images from specific archive
        upload_items = []
        for i in range(20):
            upload_items.append({
                'type': 'extracted_file',
                'file_path': f'/tmp/test_{i}.jpg',
                'source_archive': 'MyArchive.zip',
                'extraction_folder': '/tmp/extracted_MyArchive'
            })
        
        with patch('os.path.exists', return_value=True):
            grouped_tasks, individual_tasks = queue_manager._regroup_restored_uploads(upload_items)
        
        # Should create 2 batches
        assert len(grouped_tasks) == 2
        
        # Both batches should have same source_archive
        for task in grouped_tasks:
            assert task['source_archive'] == 'MyArchive.zip'
            assert task['extraction_folder'] == '/tmp/extracted_MyArchive'
            assert 'MyArchive.zip' in task['filename']
    
    @pytest.mark.asyncio
    async def test_execute_grouped_upload_validates_limit(self):
        """Test that _execute_grouped_upload validates and truncates oversized groups."""
        queue_manager = QueueManager()
        
        # Create a task with 15 files (exceeds limit)
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create actual test files
            file_paths = []
            for i in range(15):
                file_path = os.path.join(temp_dir, f'test_{i}.jpg')
                with open(file_path, 'w') as f:
                    f.write(f'test content {i}')
                file_paths.append(file_path)
            
            task = {
                'type': 'grouped_media',
                'filename': 'test - Images (15 files)',
                'file_paths': file_paths,
                'media_type': 'images',
                'source_archive': 'test.zip',
                'event': None,
                'is_grouped': True
            }
            
            # Mock upload methods
            with patch('utils.telegram_operations.get_client') as mock_get_client, \
                 patch('utils.telegram_operations.TelegramOperations') as mock_telegram_ops, \
                 patch('utils.telegram_operations.ensure_target_entity') as mock_ensure_target:
                
                mock_client = AsyncMock()
                mock_get_client.return_value = mock_client
                mock_ensure_target.return_value = AsyncMock()
                
                mock_ops = AsyncMock()
                mock_ops.upload_media_grouped = AsyncMock()
                mock_telegram_ops.return_value = mock_ops
                
                # Execute upload
                await queue_manager._execute_grouped_upload(task)
                
                # Should have truncated to 10 files
                assert mock_ops.upload_media_grouped.called
                call_args = mock_ops.upload_media_grouped.call_args
                uploaded_files = call_args[0][1]  # Second argument is file list
                assert len(uploaded_files) <= TELEGRAM_ALBUM_MAX_FILES


class TestLiveExtractionBatching:
    """Test batching during live extraction (not just queue restoration)."""
    
    @pytest.mark.asyncio
    async def test_process_extraction_creates_batches(self):
        """Test that _process_extraction_and_upload creates batched tasks for large groups."""
        queue_manager = QueueManager()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create mock archive
            archive_path = os.path.join(temp_dir, 'test.zip')
            with open(archive_path, 'w') as f:
                f.write('fake archive')
            
            # Create extraction directory with 25 image files
            extract_dir = os.path.join(temp_dir, 'extracted')
            os.makedirs(extract_dir)
            image_files = []
            for i in range(25):
                img_path = os.path.join(extract_dir, f'image_{i}.jpg')
                with open(img_path, 'w') as f:
                    f.write(f'image {i}')
                image_files.append(img_path)
            
            processing_task = {
                'filename': 'test.zip',
                'temp_archive_path': archive_path,
                'event': None
            }
            
            # Mock extraction to return success
            with patch('utils.file_operations.extract_archive_async') as mock_extract, \
                 patch('os.walk') as mock_walk, \
                 patch.object(queue_manager, 'add_upload_task', new=AsyncMock()) as mock_add_upload:
                
                mock_extract.return_value = (True, None)
                mock_walk.return_value = [(extract_dir, [], [f'image_{i}.jpg' for i in range(25)])]
                
                await queue_manager._process_extraction_and_upload(processing_task)
                
                # Should have created 3 upload tasks (10, 10, 5)
                assert mock_add_upload.call_count == 3
                
                # Verify batch sizes
                calls = mock_add_upload.call_args_list
                assert len(calls[0][0][0]['file_paths']) == 10  # Batch 1
                assert len(calls[1][0][0]['file_paths']) == 10  # Batch 2
                assert len(calls[2][0][0]['file_paths']) == 5   # Batch 3
                
                # Verify batch metadata
                assert 'Batch 1/3' in calls[0][0][0]['filename']
                assert 'Batch 2/3' in calls[1][0][0]['filename']
                assert 'Batch 3/3' in calls[2][0][0]['filename']


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_file_list(self):
        """Test handling of empty file list."""
        queue_manager = QueueManager()
        
        upload_items = []
        grouped_tasks, individual_tasks = queue_manager._regroup_restored_uploads(upload_items)
        
        assert len(grouped_tasks) == 0
        assert len(individual_tasks) == 0
    
    def test_single_file_no_grouping(self):
        """Test that single files are not grouped."""
        queue_manager = QueueManager()
        
        upload_items = [{
            'type': 'extracted_file',
            'file_path': '/tmp/single.jpg',
            'source_archive': 'test.zip',
            'extraction_folder': '/tmp/extracted'
        }]
        
        with patch('os.path.exists', return_value=True):
            grouped_tasks, individual_tasks = queue_manager._regroup_restored_uploads(upload_items)
        
        # Single file should remain individual
        assert len(grouped_tasks) == 0
        assert len(individual_tasks) == 1
    
    def test_missing_files_skipped(self):
        """Test that non-existent files are skipped during batching."""
        queue_manager = QueueManager()
        
        # Create 15 items, but only 12 files exist
        upload_items = []
        for i in range(15):
            upload_items.append({
                'type': 'extracted_file',
                'file_path': f'/tmp/test_{i}.jpg',
                'source_archive': 'test.zip',
                'extraction_folder': '/tmp/extracted'
            })
        
        # Mock: files 0-11 exist, files 12-14 don't exist
        def mock_exists(path):
            file_num = int(path.split('_')[-1].split('.')[0])
            return file_num < 12
        
        with patch('os.path.exists', side_effect=mock_exists):
            grouped_tasks, individual_tasks = queue_manager._regroup_restored_uploads(upload_items)
        
        # 12 existing files → 2 batches (10, 2)
        assert len(grouped_tasks) == 2
        assert len(grouped_tasks[0]['file_paths']) == 10
        assert len(grouped_tasks[1]['file_paths']) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
