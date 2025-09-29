#!/usr/bin/env python3
"""
Comprehensive unit tests for queue processing auto-start fix.
Tests the fix for the RuntimeError: no running event loop issue.
"""

import pytest
import asyncio
import os
import json
import tempfile
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture
def temp_queue_files():
    """Create temporary queue files for testing"""
    with tempfile.TemporaryDirectory() as temp_dir:
        download_file = os.path.join(temp_dir, 'download_queue.json')
        upload_file = os.path.join(temp_dir, 'upload_queue.json')
        yield download_file, upload_file

def test_queue_manager_init_no_event_loop(temp_queue_files):
    """Test that QueueManager can be initialized without running event loop"""
    download_file, upload_file = temp_queue_files
    
    # Create test data
    test_tasks = [
        {'type': 'direct_media_download', 'filename': 'test1.mp4'},
        {'type': 'direct_media_download', 'filename': 'test2.mp4'}
    ]
    
    # Write test data to file
    with open(download_file, 'w') as f:
        json.dump(test_tasks, f)
    
    with patch('utils.constants.DOWNLOAD_QUEUE_FILE', download_file), \
         patch('utils.constants.UPLOAD_QUEUE_FILE', upload_file):
        
        # This should NOT raise RuntimeError: no running event loop
        from utils.queue_manager import QueueManager
        queue_manager = QueueManager()
        
        # Verify queue was restored
        assert queue_manager.download_queue.qsize() == 2
        assert queue_manager._pending_download_items == 2
        assert queue_manager.download_task is None  # No task created yet
        
        print("✅ QueueManager initialized successfully without event loop")

@pytest.mark.asyncio
async def test_ensure_processors_started(temp_queue_files):
    """Test that processors start correctly when event loop is available"""
    download_file, upload_file = temp_queue_files
    
    # Create test data
    test_download_tasks = [{'type': 'direct_media_download', 'filename': 'test1.mp4'}]
    test_upload_tasks = [{'type': 'upload_media', 'filename': 'test2.mp4'}]
    
    with open(download_file, 'w') as f:
        json.dump(test_download_tasks, f)
    with open(upload_file, 'w') as f:
        json.dump(test_upload_tasks, f)
    
    with patch('utils.constants.DOWNLOAD_QUEUE_FILE', download_file), \
         patch('utils.constants.UPLOAD_QUEUE_FILE', upload_file):
        
        from utils.queue_manager import QueueManager
        queue_manager = QueueManager()
        
        # Verify initial state
        assert queue_manager._pending_download_items == 1
        assert queue_manager._pending_upload_items == 1
        assert queue_manager.download_task is None
        assert queue_manager.upload_task is None
        
        # Now start processors (this requires event loop)
        await queue_manager.ensure_processors_started()
        
        # Verify processors were started
        assert queue_manager.download_task is not None
        assert queue_manager.upload_task is not None
        assert not queue_manager.download_task.done()
        assert not queue_manager.upload_task.done()
        assert queue_manager._pending_download_items == 0
        assert queue_manager._pending_upload_items == 0
        
        # Clean up
        queue_manager.download_task.cancel()
        queue_manager.upload_task.cancel()
        try:
            await queue_manager.download_task
        except asyncio.CancelledError:
            pass
        try:
            await queue_manager.upload_task
        except asyncio.CancelledError:
            pass
        
        print("✅ Processors started successfully when event loop available")

@pytest.mark.asyncio 
async def test_ensure_processors_started_empty_queue(temp_queue_files):
    """Test that processors don't start for empty queues"""
    download_file, upload_file = temp_queue_files
    
    # Create empty queue files
    with open(download_file, 'w') as f:
        json.dump([], f)
    with open(upload_file, 'w') as f:
        json.dump([], f)
    
    with patch('utils.constants.DOWNLOAD_QUEUE_FILE', download_file), \
         patch('utils.constants.UPLOAD_QUEUE_FILE', upload_file):
        
        from utils.queue_manager import QueueManager
        queue_manager = QueueManager()
        
        assert queue_manager._pending_download_items == 0
        assert queue_manager._pending_upload_items == 0
        
        # Call ensure_processors_started - should do nothing
        await queue_manager.ensure_processors_started()
        
        # Verify no processors started
        assert queue_manager.download_task is None
        assert queue_manager.upload_task is None
        
        print("✅ No processors started for empty queues")

@pytest.mark.asyncio
async def test_add_download_task_still_works(temp_queue_files):
    """Test that adding new download tasks still works correctly"""
    download_file, upload_file = temp_queue_files
    
    with patch('utils.constants.DOWNLOAD_QUEUE_FILE', download_file), \
         patch('utils.constants.UPLOAD_QUEUE_FILE', upload_file):
        
        from utils.queue_manager import QueueManager
        queue_manager = QueueManager()
        
        # Add a new task
        test_task = {'type': 'direct_media_download', 'filename': 'new_test.mp4'}
        await queue_manager.add_download_task(test_task)
        
        # Verify processor was started
        assert queue_manager.download_task is not None
        assert not queue_manager.download_task.done()
        
        # Clean up
        queue_manager.download_task.cancel()
        try:
            await queue_manager.download_task
        except asyncio.CancelledError:
            pass
        
        print("✅ Adding new download tasks works correctly")

@pytest.mark.asyncio
async def test_multiple_ensure_calls_safe(temp_queue_files):
    """Test that calling ensure_processors_started multiple times is safe"""
    download_file, upload_file = temp_queue_files
    
    test_tasks = [{'type': 'direct_media_download', 'filename': 'test.mp4'}]
    with open(download_file, 'w') as f:
        json.dump(test_tasks, f)
    
    with patch('utils.constants.DOWNLOAD_QUEUE_FILE', download_file), \
         patch('utils.constants.UPLOAD_QUEUE_FILE', upload_file):
        
        from utils.queue_manager import QueueManager
        queue_manager = QueueManager()
        
        # Call ensure_processors_started multiple times
        await queue_manager.ensure_processors_started()
        first_task = queue_manager.download_task
        
        await queue_manager.ensure_processors_started()
        second_task = queue_manager.download_task
        
        # Should be the same task (not recreated)
        assert first_task is second_task
        assert queue_manager._pending_download_items == 0
        
        # Clean up
        queue_manager.download_task.cancel()
        try:
            await queue_manager.download_task
        except asyncio.CancelledError:
            pass
        
        print("✅ Multiple ensure_processors_started calls are safe")

def test_get_queue_manager_singleton():
    """Test that get_queue_manager returns singleton"""
    from utils.queue_manager import get_queue_manager
    
    manager1 = get_queue_manager()
    manager2 = get_queue_manager()
    
    assert manager1 is manager2
    print("✅ Queue manager singleton works correctly")

@pytest.mark.asyncio
async def test_integration_scenario(temp_queue_files):
    """Test the complete integration scenario: init -> restore -> start processors"""
    download_file, upload_file = temp_queue_files
    
    # Simulate real queue data
    real_queue_data = [
        {
            'type': 'direct_media_download',
            'message': {'id': 123, 'date': '2025-09-29T19:00:00+00:00'},
            'filename': 'video1.mp4',
            'temp_path': '/tmp/video1.mp4'
        },
        {
            'type': 'direct_media_download', 
            'message': {'id': 124, 'date': '2025-09-29T19:01:00+00:00'},
            'filename': 'video2.mp4',
            'temp_path': '/tmp/video2.mp4'
        }
    ]
    
    with open(download_file, 'w') as f:
        json.dump(real_queue_data, f)
    
    with patch('utils.constants.DOWNLOAD_QUEUE_FILE', download_file), \
         patch('utils.constants.UPLOAD_QUEUE_FILE', upload_file):
        
        # Step 1: Initialize queue manager (no event loop errors)
        from utils.queue_manager import QueueManager
        queue_manager = QueueManager()
        
        # Step 2: Verify restoration but no processors yet
        assert queue_manager.download_queue.qsize() == 2
        assert queue_manager._pending_download_items == 2
        assert queue_manager.download_task is None
        
        # Step 3: Start processors when event loop available
        await queue_manager.ensure_processors_started()
        
        # Step 4: Verify processors are running
        assert queue_manager.download_task is not None
        assert not queue_manager.download_task.done()
        assert queue_manager._pending_download_items == 0
        
        # Clean up
        queue_manager.download_task.cancel()
        try:
            await queue_manager.download_task
        except asyncio.CancelledError:
            pass
        
        print("✅ Complete integration scenario works correctly")

if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])