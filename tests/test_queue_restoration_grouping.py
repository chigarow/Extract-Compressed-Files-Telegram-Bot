"""
Tests for queue restoration with intelligent grouping functionality.
"""

import pytest
import asyncio
import os
import tempfile
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from utils.queue_manager import QueueManager
from utils.constants import UPLOAD_QUEUE_FILE


class TestQueueRestorationGrouping:
    """Test suite for queue restoration with intelligent file grouping."""
    
    @pytest.fixture
    def temp_files(self):
        """Create temporary test files."""
        temp_dir = tempfile.mkdtemp()
        files = []
        
        # Create test image files
        for i in range(5):
            img_path = os.path.join(temp_dir, f"image_{i}.jpg")
            with open(img_path, 'wb') as f:
                f.write(b'fake image data')
            files.append(img_path)
        
        # Create test video files
        for i in range(3):
            vid_path = os.path.join(temp_dir, f"video_{i}.mp4")
            with open(vid_path, 'wb') as f:
                f.write(b'fake video data')
            files.append(vid_path)
        
        yield temp_dir, files
        
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def mock_upload_queue_file(self, temp_files):
        """Create a mock upload queue file with individual tasks."""
        temp_dir, files = temp_files
        
        # Create individual upload tasks (simulating pre-crash state)
        tasks = []
        
        # Add image tasks
        for i in range(5):
            tasks.append({
                'type': 'extracted_file',
                'file_path': files[i],
                'filename': f'image_{i}.jpg',
                'archive_name': 'test_archive.zip',
                'source_archive': 'test_archive.zip',
                'extraction_folder': os.path.join(temp_dir, 'extracted_test_archive'),
                'size_bytes': 1024,
                'retry_count': 0
            })
        
        # Add video tasks
        for i in range(3):
            tasks.append({
                'type': 'extracted_file',
                'file_path': files[i + 5],
                'filename': f'video_{i}.mp4',
                'archive_name': 'test_archive.zip',
                'source_archive': 'test_archive.zip',
                'extraction_folder': os.path.join(temp_dir, 'extracted_test_archive'),
                'size_bytes': 2048,
                'retry_count': 0
            })
        
        # Write to temporary queue file
        queue_file = os.path.join(temp_dir, 'test_upload_queue.json')
        with open(queue_file, 'w') as f:
            json.dump(tasks, f)
        
        return queue_file, tasks, temp_dir
    
    @pytest.mark.asyncio
    async def test_regroup_individual_files_by_archive(self, mock_upload_queue_file):
        """Test that individual files from same archive are regrouped."""
        queue_file, original_tasks, temp_dir = mock_upload_queue_file
        
        # Patch the UPLOAD_QUEUE_FILE constant
        with patch('utils.queue_manager.UPLOAD_QUEUE_FILE', queue_file):
            # Create queue manager (will trigger restoration)
            queue_manager = QueueManager()
            
            # Check that files were regrouped
            # Original: 8 individual tasks
            # Expected: 2 grouped tasks (1 for images, 1 for videos)
            queue_size = queue_manager.upload_queue.qsize()
            
            assert queue_size == 2, f"Expected 2 grouped tasks, got {queue_size}"
            
            # Verify the grouped tasks
            tasks_in_queue = []
            while not queue_manager.upload_queue.empty():
                task = await queue_manager.upload_queue.get()
                tasks_in_queue.append(task)
            
            # Check that we have grouped tasks
            grouped_tasks = [t for t in tasks_in_queue if t.get('is_grouped')]
            assert len(grouped_tasks) == 2, "Should have 2 grouped tasks"
            
            # Verify image group
            image_group = next((t for t in grouped_tasks if t.get('media_type') == 'images'), None)
            assert image_group is not None, "Should have image group"
            assert len(image_group.get('file_paths', [])) == 5, "Image group should have 5 files"
            
            # Verify video group
            video_group = next((t for t in grouped_tasks if t.get('media_type') == 'videos'), None)
            assert video_group is not None, "Should have video group"
            assert len(video_group.get('file_paths', [])) == 3, "Video group should have 3 files"
    
    @pytest.mark.asyncio
    async def test_regroup_preserves_metadata(self, mock_upload_queue_file):
        """Test that regrouping preserves important metadata."""
        queue_file, original_tasks, temp_dir = mock_upload_queue_file
        
        with patch('utils.queue_manager.UPLOAD_QUEUE_FILE', queue_file):
            queue_manager = QueueManager()
            
            # Get the grouped tasks
            tasks_in_queue = []
            while not queue_manager.upload_queue.empty():
                task = await queue_manager.upload_queue.get()
                tasks_in_queue.append(task)
            
            for task in tasks_in_queue:
                # Verify essential metadata is preserved
                assert task.get('source_archive') == 'test_archive.zip'
                assert task.get('extraction_folder') is not None
                assert task.get('is_grouped') is True
                assert task.get('type') == 'grouped_media'
    
    @pytest.mark.asyncio
    async def test_regroup_skips_missing_files(self, temp_files):
        """Test that regrouping skips files that no longer exist."""
        temp_dir, files = temp_files
        
        # Create tasks with some files that don't exist
        tasks = []
        for i in range(5):
            file_path = files[i] if i < 3 else os.path.join(temp_dir, f"missing_{i}.jpg")
            tasks.append({
                'type': 'extracted_file',
                'file_path': file_path,
                'filename': f'image_{i}.jpg',
                'archive_name': 'test_archive.zip',
                'source_archive': 'test_archive.zip',
                'extraction_folder': os.path.join(temp_dir, 'extracted_test_archive'),
                'size_bytes': 1024
            })
        
        # Write to temporary queue file
        queue_file = os.path.join(temp_dir, 'test_upload_queue.json')
        with open(queue_file, 'w') as f:
            json.dump(tasks, f)
        
        with patch('utils.queue_manager.UPLOAD_QUEUE_FILE', queue_file):
            queue_manager = QueueManager()
            
            # Should only group the 3 existing files
            queue_size = queue_manager.upload_queue.qsize()
            
            # Get grouped task
            if queue_size > 0:
                task = await queue_manager.upload_queue.get()
                if task.get('is_grouped'):
                    # Should only have files that exist
                    file_paths = task.get('file_paths', [])
                    assert len(file_paths) == 3, f"Should only have 3 existing files, got {len(file_paths)}"
    
    @pytest.mark.asyncio
    async def test_regroup_keeps_single_files_individual(self, temp_files):
        """Test that single files from different archives remain individual."""
        temp_dir, files = temp_files
        
        # Create tasks from different archives (won't be grouped)
        tasks = []
        for i in range(3):
            tasks.append({
                'type': 'extracted_file',
                'file_path': files[i],
                'filename': f'image_{i}.jpg',
                'archive_name': f'archive_{i}.zip',  # Different archive for each
                'source_archive': f'archive_{i}.zip',
                'extraction_folder': os.path.join(temp_dir, f'extracted_archive_{i}'),
                'size_bytes': 1024
            })
        
        # Write to temporary queue file
        queue_file = os.path.join(temp_dir, 'test_upload_queue.json')
        with open(queue_file, 'w') as f:
            json.dump(tasks, f)
        
        with patch('utils.queue_manager.UPLOAD_QUEUE_FILE', queue_file):
            queue_manager = QueueManager()
            
            # Should remain as 3 individual tasks (not grouped since from different archives)
            queue_size = queue_manager.upload_queue.qsize()
            assert queue_size == 3, f"Expected 3 individual tasks, got {queue_size}"
            
            # Verify none are grouped
            tasks_in_queue = []
            while not queue_manager.upload_queue.empty():
                task = await queue_manager.upload_queue.get()
                tasks_in_queue.append(task)
            
            grouped = [t for t in tasks_in_queue if t.get('is_grouped')]
            assert len(grouped) == 0, "Should have no grouped tasks for files from different archives"
    
    @pytest.mark.asyncio
    async def test_regroup_optimization_logging(self, mock_upload_queue_file):
        """Test that optimization metrics are logged."""
        import logging
        queue_file, original_tasks, temp_dir = mock_upload_queue_file
        
        # Set up logger to capture messages
        logger = logging.getLogger('extractor')
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        captured_logs = []
        original_info = logger.info
        
        def capture_log(msg, *args, **kwargs):
            captured_logs.append(msg)
            return original_info(msg, *args, **kwargs)
        
        logger.info = capture_log
        
        try:
            with patch('utils.queue_manager.UPLOAD_QUEUE_FILE', queue_file):
                queue_manager = QueueManager()
                
                # Check captured logs for optimization message
                optimization_logs = [msg for msg in captured_logs if 'Optimized upload queue' in msg or 'Created grouped task' in msg or 'Regrouping complete' in msg]
                
                assert len(optimization_logs) > 0, f"Should log optimization information. Captured logs: {captured_logs}"
        finally:
            logger.info = original_info
            logger.removeHandler(handler)
    
    @pytest.mark.asyncio
    async def test_already_grouped_tasks_preserved(self, temp_files):
        """Test that already-grouped tasks are preserved as-is."""
        temp_dir, files = temp_files
        
        # Create a mix of individual and already-grouped tasks
        tasks = [
            # Already grouped task
            {
                'type': 'grouped_media',
                'media_type': 'images',
                'is_grouped': True,
                'file_paths': files[:3],
                'filename': 'Already Grouped - Images (3 files)',
                'source_archive': 'test.zip',
                'extraction_folder': temp_dir
            },
            # Individual task
            {
                'type': 'extracted_file',
                'file_path': files[3],
                'filename': 'image_3.jpg',
                'archive_name': 'another.zip',
                'source_archive': 'another.zip',
                'extraction_folder': temp_dir,
                'size_bytes': 1024
            }
        ]
        
        # Write to temporary queue file
        queue_file = os.path.join(temp_dir, 'test_upload_queue.json')
        with open(queue_file, 'w') as f:
            json.dump(tasks, f)
        
        with patch('utils.queue_manager.UPLOAD_QUEUE_FILE', queue_file):
            queue_manager = QueueManager()
            
            # Should have 2 tasks total
            queue_size = queue_manager.upload_queue.qsize()
            assert queue_size == 2, f"Expected 2 tasks, got {queue_size}"
            
            # Get tasks
            tasks_in_queue = []
            while not queue_manager.upload_queue.empty():
                task = await queue_manager.upload_queue.get()
                tasks_in_queue.append(task)
            
            # One should be the original grouped task
            grouped = [t for t in tasks_in_queue if t.get('is_grouped') and 'Already Grouped' in t.get('filename', '')]
            assert len(grouped) == 1, "Already-grouped task should be preserved"


class TestFloodWaitProcessorContinuation:
    """Test that upload processor continues after FloodWaitError."""
    
    @pytest.mark.asyncio
    async def test_processor_continues_after_flood_wait(self):
        """Test that processor continues with next task after FloodWaitError.
        
        This test verifies that when a FloodWaitError occurs, the processor:
        1. Continues with the next task in the queue
        2. Does not stop processing entirely
        3. Successfully processes subsequent tasks
        """
        
        # Create a proper FloodWaitError mock
        class MockFloodWaitError(Exception):
            def __init__(self, seconds=60):
                self.seconds = seconds
                super().__init__(f"A wait of {seconds} seconds is required")
        
        queue_manager = QueueManager()
        
        # Track execution order
        execution_log = []
        
        async def mock_execute(task):
            filename = task.get('filename', 'unknown')
            execution_log.append(f"executing_{filename}")
            
            if filename == 'task1.jpg':
                # First task hits rate limit
                raise MockFloodWaitError(seconds=60)
            # Second task succeeds
            return True
        
        # Patch FloodWaitError in the queue_manager module
        with patch('utils.queue_manager.FloodWaitError', MockFloodWaitError):
            with patch.object(queue_manager, '_execute_upload_task', side_effect=mock_execute):
                # Add two tasks
                await queue_manager.add_upload_task({
                    'type': 'test',
                    'filename': 'task1.jpg',
                    'file_path': '/tmp/task1.jpg'
                })
                
                await queue_manager.add_upload_task({
                    'type': 'test',
                    'filename': 'task2.jpg',
                    'file_path': '/tmp/task2.jpg'
                })
                
                # Wait for processing to complete
                await asyncio.sleep(1.0)
                
                # Should have tried both tasks
                assert len(execution_log) == 2, f"Expected 2 execution attempts, got {len(execution_log)}: {execution_log}"
                assert 'executing_task1.jpg' in execution_log, "Should have attempted task1"
                assert 'executing_task2.jpg' in execution_log, "Should have attempted task2"
                
                # Verify task order
                assert execution_log.index('executing_task1.jpg') < execution_log.index('executing_task2.jpg'), \
                    "task1 should be executed before task2"
                
                # Most importantly: processor continued after FloodWaitError
                # This is proven by task2 being executed after task1 raised FloodWaitError


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
