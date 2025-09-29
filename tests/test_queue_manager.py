"""
Tests for utils.queue_manager module

Tests queue processing, concurrency control, retry mechanisms, and error handling.
"""

import asyncio
import json
import os
import tempfile
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.queue_manager import QueueManager
from utils.constants import *

class TestQueueManager:
    """Test suite for QueueManager class"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        import shutil
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def queue_manager(self, temp_dir, mock_client):
        """Create QueueManager instance for testing"""
        with patch('utils.queue_manager.DOWNLOAD_QUEUE_FILE', os.path.join(temp_dir, 'download_queue.json')):
            with patch('utils.queue_manager.UPLOAD_QUEUE_FILE', os.path.join(temp_dir, 'upload_queue.json')):
                with patch('utils.queue_manager.RETRY_QUEUE_FILE', os.path.join(temp_dir, 'retry_queue.json')):
                    manager = QueueManager(mock_client)
                    yield manager
    
    def test_initialization(self, queue_manager, mock_client):
        """Test QueueManager initialization"""
        assert queue_manager.client == mock_client
        assert queue_manager.download_semaphore._value == DOWNLOAD_SEMAPHORE_LIMIT
        assert queue_manager.upload_semaphore._value == UPLOAD_SEMAPHORE_LIMIT
        assert len(queue_manager.download_queue) == 0
        assert len(queue_manager.upload_queue) == 0
        assert len(queue_manager.retry_queue) == 0
        assert not queue_manager.is_processing
    
    @pytest.mark.asyncio
    async def test_add_download_task(self, queue_manager, mock_document):
        """Test adding download task to queue"""
        task_id = await queue_manager.add_download_task(
            mock_document, 
            "/test/output/path", 
            {"test": "metadata"}
        )
        
        assert task_id is not None
        assert len(queue_manager.download_queue) == 1
        
        task = queue_manager.download_queue[0]
        assert task['id'] == task_id
        assert task['document'] == mock_document
        assert task['output_path'] == "/test/output/path"
        assert task['metadata'] == {"test": "metadata"}
        assert task['status'] == 'pending'
        assert task['attempts'] == 0
    
    @pytest.mark.asyncio
    async def test_add_upload_task(self, queue_manager):
        """Test adding upload task to queue"""
        test_file = "/test/file.txt"
        task_id = await queue_manager.add_upload_task(
            test_file, 
            123456, 
            {"caption": "test file"}
        )
        
        assert task_id is not None
        assert len(queue_manager.upload_queue) == 1
        
        task = queue_manager.upload_queue[0]
        assert task['id'] == task_id
        assert task['file_path'] == test_file
        assert task['chat_id'] == 123456
        assert task['options'] == {"caption": "test file"}
        assert task['status'] == 'pending'
        assert task['attempts'] == 0
    
    @pytest.mark.asyncio
    async def test_queue_persistence(self, queue_manager, mock_document, temp_dir):
        """Test saving and loading queue data"""
        # Add tasks to queues
        await queue_manager.add_download_task(mock_document, "/test/path1")
        await queue_manager.add_upload_task("/test/file1.txt", 123456)
        
        # Save queues
        queue_manager.save_queues()
        
        # Verify files were created
        download_file = os.path.join(temp_dir, 'download_queue.json')
        upload_file = os.path.join(temp_dir, 'upload_queue.json')
        assert os.path.exists(download_file)
        assert os.path.exists(upload_file)
        
        # Create new instance and load
        with patch('utils.queue_manager.DOWNLOAD_QUEUE_FILE', download_file):
            with patch('utils.queue_manager.UPLOAD_QUEUE_FILE', upload_file):
                new_manager = QueueManager(queue_manager.client)
                new_manager.load_queues()
        
        assert len(new_manager.download_queue) == 1
        assert len(new_manager.upload_queue) == 1
    
    @pytest.mark.asyncio
    async def test_concurrency_limits(self, queue_manager, mock_document):
        """Test that concurrency limits are enforced"""
        # Add more tasks than the semaphore limit
        tasks = []
        for i in range(DOWNLOAD_SEMAPHORE_LIMIT + 2):
            task_id = await queue_manager.add_download_task(
                mock_document, f"/test/path{i}"
            )
            tasks.append(task_id)
        
        # Mock the download execution to take some time
        original_execute = queue_manager._execute_download_task
        call_count = 0
        concurrent_calls = []
        
        async def mock_execute(task):
            nonlocal call_count, concurrent_calls
            call_count += 1
            concurrent_calls.append(call_count)
            await asyncio.sleep(0.1)  # Simulate work
            call_count -= 1
            return True, "Success"
        
        queue_manager._execute_download_task = mock_execute
        
        # Start processing (should respect concurrency limit)
        await queue_manager.start_processing()
        
        # Wait a bit for processing to start
        await asyncio.sleep(0.05)
        
        # Check that no more than DOWNLOAD_SEMAPHORE_LIMIT tasks run concurrently
        assert max(concurrent_calls) <= DOWNLOAD_SEMAPHORE_LIMIT
        
        await queue_manager.stop_processing()
    
    @pytest.mark.asyncio
    async def test_retry_mechanism(self, queue_manager, mock_document):
        """Test retry mechanism for failed tasks"""
        task_id = await queue_manager.add_download_task(mock_document, "/test/path")
        
        # Mock download to fail initially, then succeed
        call_count = 0
        async def mock_failing_execute(task):
            nonlocal call_count
            call_count += 1
            if call_count < 3:  # Fail first 2 attempts
                return False, "Connection error"
            return True, "Success"
        
        queue_manager._execute_download_task = mock_failing_execute
        
        await queue_manager.start_processing()
        
        # Wait for processing to complete
        await asyncio.sleep(1)
        
        await queue_manager.stop_processing()
        
        # Check that task eventually succeeded after retries
        assert call_count >= 3
        # Task should be removed from queue after success
        completed_task = next((t for t in queue_manager.download_queue if t['id'] == task_id), None)
        assert completed_task is None or completed_task['status'] == 'completed'
    
    @pytest.mark.asyncio
    async def test_max_retry_attempts(self, queue_manager, mock_document):
        """Test that tasks are moved to failed after max retries"""
        task_id = await queue_manager.add_download_task(mock_document, "/test/path")
        
        # Mock download to always fail
        async def mock_always_fail(task):
            return False, "Permanent error"
        
        queue_manager._execute_download_task = mock_always_fail
        
        await queue_manager.start_processing()
        
        # Wait for all retry attempts
        await asyncio.sleep(2)
        
        await queue_manager.stop_processing()
        
        # Task should be marked as failed
        failed_task = next((t for t in queue_manager.download_queue if t['id'] == task_id), None)
        assert failed_task is not None
        assert failed_task['status'] == 'failed'
        assert failed_task['attempts'] >= MAX_RETRY_ATTEMPTS
    
    @pytest.mark.asyncio
    async def test_progress_callback(self, queue_manager, mock_document, mock_progress_callback):
        """Test progress callback functionality"""
        task_id = await queue_manager.add_download_task(
            mock_document, 
            "/test/path",
            progress_callback=mock_progress_callback
        )
        
        # Mock download execution to call progress callback
        async def mock_execute_with_progress(task):
            callback = task.get('progress_callback')
            if callback:
                callback(512, 1024)  # 50% progress
                callback(1024, 1024)  # 100% progress
            return True, "Success"
        
        queue_manager._execute_download_task = mock_execute_with_progress
        
        await queue_manager.start_processing()
        await asyncio.sleep(0.5)
        await queue_manager.stop_processing()
        
        # Check that progress callback was called
        progress_history = mock_progress_callback.get_progress_history()
        assert len(progress_history) >= 2
        assert progress_history[-1]['progress'] == 100.0
    
    @pytest.mark.asyncio
    async def test_queue_statistics(self, queue_manager, mock_document):
        """Test queue statistics functionality"""
        # Add various tasks
        await queue_manager.add_download_task(mock_document, "/test/path1")
        await queue_manager.add_download_task(mock_document, "/test/path2")
        await queue_manager.add_upload_task("/test/file1.txt", 123456)
        
        stats = await queue_manager.get_queue_stats()
        
        assert stats['download']['pending'] == 2
        assert stats['download']['processing'] == 0
        assert stats['download']['completed'] == 0
        assert stats['download']['failed'] == 0
        assert stats['upload']['pending'] == 1
        assert stats['total_tasks'] == 3
    
    @pytest.mark.asyncio
    async def test_clear_completed_tasks(self, queue_manager, mock_document):
        """Test clearing completed tasks from queues"""
        # Add and mark some tasks as completed
        task_id = await queue_manager.add_download_task(mock_document, "/test/path")
        
        # Manually mark as completed for testing
        for task in queue_manager.download_queue:
            if task['id'] == task_id:
                task['status'] = 'completed'
                break
        
        initial_count = len(queue_manager.download_queue)
        await queue_manager.clear_completed_tasks()
        final_count = len(queue_manager.download_queue)
        
        assert final_count < initial_count
    
    @pytest.mark.asyncio
    async def test_pause_resume_processing(self, queue_manager, mock_document):  
        """Test pausing and resuming queue processing"""
        await queue_manager.add_download_task(mock_document, "/test/path")
        
        # Start processing
        await queue_manager.start_processing()
        assert queue_manager.is_processing
        
        # Pause processing
        await queue_manager.pause_processing()
        assert not queue_manager.is_processing
        
        # Resume processing
        await queue_manager.resume_processing()
        assert queue_manager.is_processing
        
        await queue_manager.stop_processing()
    
    @pytest.mark.asyncio
    async def test_task_cancellation(self, queue_manager, mock_document):
        """Test cancelling specific tasks"""
        task_id = await queue_manager.add_download_task(mock_document, "/test/path")
        
        # Cancel the task
        success = await queue_manager.cancel_task(task_id)
        assert success
        
        # Task should be marked as cancelled
        cancelled_task = next((t for t in queue_manager.download_queue if t['id'] == task_id), None)
        assert cancelled_task is not None
        assert cancelled_task['status'] == 'cancelled'
    
    @pytest.mark.asyncio
    async def test_error_handling_in_processing(self, queue_manager, mock_document):
        """Test error handling during queue processing"""
        await queue_manager.add_download_task(mock_document, "/test/path")
        
        # Mock execute method to raise an exception
        async def mock_execute_with_exception(task):
            raise Exception("Unexpected error")
        
        queue_manager._execute_download_task = mock_execute_with_exception
        
        # Processing should handle the exception gracefully
        await queue_manager.start_processing()
        await asyncio.sleep(0.5)
        await queue_manager.stop_processing()
        
        # Task should be marked as failed
        failed_task = queue_manager.download_queue[0]
        assert failed_task['status'] == 'failed'
    
    def test_queue_serialization(self, queue_manager, mock_document):
        """Test JSON serialization of queue data"""
        # Add a task (synchronously for this test)
        queue_manager.download_queue.append({
            'id': 'test-123',
            'document': mock_document,
            'output_path': '/test/path',
            'status': 'pending',
            'attempts': 0,
            'created_at': '2025-01-01T00:00:00Z'
        })
        
        # Test that queues can be serialized to JSON
        json_data = queue_manager._queue_to_json_data()
        assert 'download_queue' in json_data
        assert len(json_data['download_queue']) == 1
        
        # Verify document serialization
        task_data = json_data['download_queue'][0]
        assert task_data['document']['file_name'] == mock_document.file_name
        assert task_data['document']['size'] == mock_document.size

class TestQueueManagerIntegration:
    """Integration tests for QueueManager"""
    
    @pytest.mark.asyncio
    async def test_full_download_workflow(self, mock_client, file_manager, mock_document):
        """Test complete download workflow from queue to completion"""
        temp_dir = file_manager.setup()
        
        with patch('utils.queue_manager.DOWNLOAD_QUEUE_FILE', os.path.join(temp_dir, 'download_queue.json')):
            queue_manager = QueueManager(mock_client)
            
            # Mock successful download
            async def mock_successful_download(task):
                output_path = task['output_path']
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'w') as f:
                    f.write("Downloaded content")
                return True, "Download completed"
            
            queue_manager._execute_download_task = mock_successful_download
            
            # Add download task
            output_path = os.path.join(temp_dir, "output", "test.pdf")
            task_id = await queue_manager.add_download_task(mock_document, output_path)
            
            # Process queue
            await queue_manager.start_processing()
            await asyncio.sleep(1)  # Allow processing time
            await queue_manager.stop_processing()
            
            # Verify file was created
            assert os.path.exists(output_path)
            with open(output_path, 'r') as f:
                content = f.read()
                assert content == "Downloaded content"
    
    @pytest.mark.asyncio
    async def test_queue_recovery_after_restart(self, mock_client, temp_dir, mock_document):
        """Test queue recovery after application restart"""
        download_file = os.path.join(temp_dir, 'download_queue.json')
        
        # First instance: add tasks and save
        with patch('utils.queue_manager.DOWNLOAD_QUEUE_FILE', download_file):
            manager1 = QueueManager(mock_client)
            await manager1.add_download_task(mock_document, "/test/path1")
            await manager1.add_download_task(mock_document, "/test/path2")
            manager1.save_queues()
        
        # Second instance: load and verify
        with patch('utils.queue_manager.DOWNLOAD_QUEUE_FILE', download_file):
            manager2 = QueueManager(mock_client)
            manager2.load_queues()
            
            assert len(manager2.download_queue) == 2
            assert manager2.download_queue[0]['output_path'] == "/test/path1"
            assert manager2.download_queue[1]['output_path'] == "/test/path2"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])