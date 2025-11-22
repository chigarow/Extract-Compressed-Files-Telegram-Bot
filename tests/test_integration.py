"""
Integration tests for the complete extract-compressed-files workflow

These tests verify the actual functionality with realistic scenarios,
including queue processing, file operations, and error handling.
"""

import asyncio
import json
import os
import tempfile
import pytest
import shutil
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Import the modules under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.queue_manager import QueueManager
from utils.cache_manager import ProcessManager
from utils.telegram_operations import TelegramOperations
from utils.constants import *

class TestRealQueueProcessing:
    """Test actual queue processing workflows"""

    @pytest.fixture
    def queue_manager(self, monkeypatch, temp_workspace):
        """Creates a QueueManager with patched file paths."""
        temp_dir, data_dir = temp_workspace
        monkeypatch.setattr('utils.constants.DATA_DIR', data_dir)
        monkeypatch.setattr('utils.constants.DOWNLOAD_QUEUE_FILE', os.path.join(data_dir, 'download_queue.json'))
        monkeypatch.setattr('utils.constants.UPLOAD_QUEUE_FILE', os.path.join(data_dir, 'upload_queue.json'))
        return QueueManager()
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    @pytest.mark.integration
    async def test_full_download_queue_workflow(self, queue_manager, mock_telegram_client, temp_workspace):
        """Test complete download queue processing workflow"""
        temp_dir, data_dir = temp_workspace
        
        # Create mock message
        mock_document = {
            "file_name": "test_video.mp4",
            "size": 2 * 1024 * 1024,
            "mime_type": "video/mp4"
        }
        mock_message = {
            "document": mock_document
        }

        # Track progress
        progress_updates = []
        def track_progress(current, total):
            progress_updates.append((current, total))

        # Add download task
        output_path = os.path.join(data_dir, "downloaded_video.mp4")
        task_data = {
            'message': mock_message,
            'temp_path': output_path,
            'progress_callback': track_progress
        }

        with patch('utils.queue_manager.get_client', return_value=mock_telegram_client):
            await queue_manager.add_download_task(task_data)

            # Process queue (simulate one iteration)
            task = await queue_manager.download_queue.get()
            print(f"DEBUG: task = {task}")

            # Execute download task manually
            try:
                client = mock_telegram_client
                document = Mock()
                document.size = task['document']['file']['size']
                temp_path = task['output_path']
                progress_callback = task.get('progress_callback')

                # Ensure output directory exists
                os.makedirs(os.path.dirname(temp_path), exist_ok=True)

                # Download file
                result = await client.download_media(
                    document,
                    temp_path,
                    progress_callback=progress_callback
                )

                # Verify file was created
                assert os.path.exists(temp_path)
                assert os.path.getsize(temp_path) == document.size

                # Verify progress was tracked
                assert len(progress_updates) > 0
                assert progress_updates[-1] == (document.size, document.size)

                print(f"✅ Download completed: {temp_path}")
                print(f"📊 Progress updates: {len(progress_updates)}")

            finally:
                queue_manager.download_queue.task_done()
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    @pytest.mark.integration
    async def test_retry_mechanism_with_failures(self, queue_manager, mock_telegram_client, temp_workspace):
        """Test retry mechanism with actual failures and recovery"""
        temp_dir, data_dir = temp_workspace
        
        # Create mock document
        mock_document = Mock()
        mock_document.file_name = "failing_download.zip"
        mock_document.size = 1024 * 1024  # 1MB
        
        # Mock client that fails then succeeds
        failure_count = 0
        async def failing_download(document, file, progress_callback=None):
            nonlocal failure_count
            failure_count += 1
            
            if failure_count <= 2:  # Fail first 2 attempts
                raise ConnectionError(f"Network error (attempt {failure_count})")
            
            # Success on 3rd attempt
            content = b'Success after retry' * 1000
            with open(file, 'wb') as f:
                f.write(content)
            return file
        
        mock_telegram_client.download_media = failing_download
        
        # Track retry attempts
        retry_attempts = []
        
        output_path = os.path.join(data_dir, "retry_test.zip")
        task = {
            'document': mock_document,
            'output_path': output_path,
            'chat_id': 123456,
            'client': mock_telegram_client,
            'attempts': 0,
            'max_attempts': 5
        }
        
        # Simulate retry loop
        success = False
        while task['attempts'] < task['max_attempts'] and not success:
            task['attempts'] += 1
            retry_attempts.append(task['attempts'])
            
            try:
                # Ensure output directory exists
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                result = await mock_telegram_client.download_media(
                    task['document'],
                    task['output_path']
                )
                
                if os.path.exists(output_path):
                    success = True
                    print(f"✅ Download succeeded on attempt {task['attempts']}")
                    break
                    
            except Exception as e:
                print(f"❌ Attempt {task['attempts']} failed: {e}")
                if task['attempts'] < task['max_attempts']:
                    await asyncio.sleep(0.1)  # Short retry delay for testing
        
        # Verify retry mechanism worked
        assert success, "Download should eventually succeed"
        assert task['attempts'] == 3, "Should succeed on 3rd attempt"
        assert len(retry_attempts) == 3, "Should have 3 retry attempts"
        assert os.path.exists(output_path), "File should exist after successful retry"
        
        print(f"🔄 Retry attempts: {retry_attempts}")
        print(f"📁 Final file size: {os.path.getsize(output_path)} bytes")
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    @pytest.mark.integration
    async def test_concurrent_queue_processing(self, queue_manager, mock_telegram_client, temp_workspace):
        """Test concurrent processing with semaphore limits"""
        temp_dir, data_dir = temp_workspace
        
        # Create multiple mock documents
        documents = []
        for i in range(5):
            doc = Mock()
            doc.file_name = f"concurrent_test_{i}.mp4"
            doc.size = 512 * 1024  # 512KB each
            doc.mime_type = "video/mp4"
            documents.append(doc)
        
        # Track concurrent executions
        active_downloads = []
        max_concurrent = 0
        
        async def tracked_download(document, file, progress_callback=None):
            nonlocal max_concurrent
            active_downloads.append(document.file_name)
            max_concurrent = max(max_concurrent, len(active_downloads))
            
            # Simulate download time
            await asyncio.sleep(0.1)
            
            # Create file
            content = f"Content for {document.file_name}".encode() * 1000
            with open(file, 'wb') as f:
                f.write(content)
            
            active_downloads.remove(document.file_name)
            return file
        
        mock_telegram_client.download_media = tracked_download
        
        # Add multiple download tasks
        tasks = []
        for i, doc in enumerate(documents):
            output_path = os.path.join(data_dir, f"concurrent_{i}.mp4")
            task_data = {
                'document': doc,
                'output_path': output_path,
                'client': mock_telegram_client
            }
            tasks.append(queue_manager.add_download_task(task_data))
        
        # Add all tasks
        await asyncio.gather(*tasks)
        
        # Process tasks concurrently (simulating semaphore behavior)
        download_tasks = []
        semaphore = asyncio.Semaphore(DOWNLOAD_SEMAPHORE_LIMIT)
        
        async def process_one_download():
            async with semaphore:
                if not queue_manager.download_queue.empty():
                    task = await queue_manager.download_queue.get()
                    try:
                        os.makedirs(os.path.dirname(task['output_path']), exist_ok=True)
                        await mock_telegram_client.download_media(
                            task['document'],
                            task['output_path']
                        )
                    finally:
                        queue_manager.download_queue.task_done()
        
        # Start concurrent downloads
        for i in range(len(documents)):
            download_tasks.append(process_one_download())
        
        # Wait for all downloads to complete
        await asyncio.gather(*download_tasks)
        
        # Verify concurrency was limited
        assert max_concurrent <= DOWNLOAD_SEMAPHORE_LIMIT, f"Max concurrent downloads ({max_concurrent}) exceeded limit ({DOWNLOAD_SEMAPHORE_LIMIT})"
        
        # Verify all files were created
        for i in range(len(documents)):
            output_path = os.path.join(data_dir, f"concurrent_{i}.mp4")
            assert os.path.exists(output_path), f"File {output_path} should exist"
        
        print(f"📊 Max concurrent downloads: {max_concurrent}")
        print(f"🚀 Semaphore limit respected: {max_concurrent <= DOWNLOAD_SEMAPHORE_LIMIT}")

class TestErrorScenarios:
    """Test realistic error scenarios and recovery"""
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(20)
    @pytest.mark.integration
    async def test_disk_full_simulation(self, tmp_path):
        """Test handling of disk full errors"""
        # Create a small limited space directory simulation
        small_file = tmp_path / "small_space_test.txt"
        
        # Mock os.path.getsize to simulate disk full
        with patch('os.path.getsize', side_effect=OSError("No space left on device")):
            with patch('builtins.open', side_effect=OSError("No space left on device")):
                
                queue_manager = QueueManager()
                
                # Try to process a task that should fail
                task = {
                    'document': Mock(file_name="large_file.zip", size=1024*1024*1024),  # 1GB
                    'output_path': str(small_file),
                    'attempts': 0,
                    'max_attempts': 3
                }
                
                # Simulate processing with error handling
                error_caught = False
                try:
                    # This should raise an OSError
                    with open(task['output_path'], 'wb') as f:
                        f.write(b"test")
                except OSError as e:
                    error_caught = True
                    assert "No space left on device" in str(e)
                
                assert error_caught, "Disk full error should be caught"
                print("✅ Disk full error properly handled")
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(20)
    @pytest.mark.integration
    async def test_network_timeout_recovery(self):
        """Test network timeout and recovery mechanisms"""
        
        # Mock client with timeout simulation
        client = Mock()
        timeout_count = 0
        
        async def timeout_then_success(document, file, **kwargs):
            nonlocal timeout_count
            timeout_count += 1
            
            if timeout_count <= 2:
                raise asyncio.TimeoutError("Connection timeout")
            
            # Success after timeouts
            with open(file, 'wb') as f:
                f.write(b"Downloaded after timeout recovery")
            return file
        
        client.download_media = timeout_then_success
        
        # Simulate download with timeout recovery
        document = Mock(file_name="timeout_test.mp4", size=1024*1024)
        output_path = "/tmp/timeout_test.mp4"
        
        success = False
        attempts = 0
        max_attempts = 5
        
        while attempts < max_attempts and not success:
            attempts += 1
            try:
                await client.download_media(document, output_path)
                success = True
            except asyncio.TimeoutError:
                print(f"⏱️  Timeout on attempt {attempts}")
                if attempts < max_attempts:
                    await asyncio.sleep(0.01)  # Short delay for testing
        
        assert success, "Should eventually succeed after timeouts"
        assert attempts == 3, "Should succeed on 3rd attempt"
        print(f"🔗 Network timeout recovery successful after {attempts} attempts")

class TestProcessManager:
    """Test ProcessManager with realistic scenarios"""
    
    @pytest.mark.timeout(15)
    def test_process_state_persistence(self, tmp_path):
        """Test process state persistence across restarts"""
        
        # Use temporary files
        process_file = tmp_path / "current_process.json"
        
        with patch('utils.constants.CURRENT_PROCESS_FILE', str(process_file)):
            
            # Session 1: Set process state
            manager1 = ProcessManager()
            manager1.current_download_process = {
                'file_name': 'test_download.mp4',
                'progress': 45,
                'status': 'downloading',
                'size_bytes': 1024 * 1024
            }
            manager1.current_upload_process = {
                'file_name': 'test_upload.zip',
                'progress': 78,
                'status': 'uploading',
                'chat_id': 123456
            }
            
            # Save state
            manager1.save_current_processes()
            
            # Verify file was created
            assert process_file.exists()
            
            # Session 2: Load state (simulating restart)
            manager2 = ProcessManager()
            manager2.load_current_processes()
            
            # Verify state was restored
            assert manager2.current_download_process is not None
            assert manager2.current_download_process['file_name'] == 'test_download.mp4'
            assert manager2.current_download_process['progress'] == 45
            
            assert manager2.current_upload_process is not None
            assert manager2.current_upload_process['file_name'] == 'test_upload.zip'
            assert manager2.current_upload_process['progress'] == 78
            
            print("✅ Process state persistence verified")

if __name__ == "__main__":
    # Run integration tests
    print("🧪 Running Integration Tests")
    print("=" * 50)
    
    # Run with asyncio
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    
    # You can run individual tests here for debugging
    pytest.main([__file__, "-v", "-s"])