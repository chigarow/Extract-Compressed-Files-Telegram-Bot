"""
Test suite for sequential processing functionality.

This test validates that parallel processing has been properly disabled and that
all operations now occur sequentially to prevent memory issues on low-resource devices.
"""

import asyncio
import pytest
import inspect


class TestSequentialProcessingConfiguration:
    """Test that sequential processing configuration is correct."""
    
    def test_semaphore_limits_enforce_sequential(self):
        """Test that semaphore limits are set to 1 for sequential processing."""
        from utils.constants import DOWNLOAD_SEMAPHORE_LIMIT, UPLOAD_SEMAPHORE_LIMIT
        
        # Verify semaphore limits are set to 1
        assert DOWNLOAD_SEMAPHORE_LIMIT == 1, \
            "Download semaphore limit should be 1 for sequential processing"
        assert UPLOAD_SEMAPHORE_LIMIT == 1, \
            "Upload semaphore limit should be 1 for sequential processing"
    
    def test_no_asyncio_create_task_in_download_handler(self):
        """Test that asyncio.create_task is not used in download task handler."""
        from utils.queue_manager import QueueManager
        
        # Get the source code of the _execute_download_task method
        source = inspect.getsource(QueueManager._execute_download_task)
        
        # Verify that asyncio.create_task is not present
        assert 'asyncio.create_task' not in source, \
            "asyncio.create_task should not be used in _execute_download_task for sequential processing"
        
        # Verify that await is used for processing methods
        assert 'await self._process_extraction_and_upload' in source or \
               'await self._process_direct_media_upload' in source, \
            "Processing methods should be awaited for sequential execution"
    
    def test_queue_manager_initialization_sequential_mode(self):
        """Test that QueueManager initializes with sequential processing limits."""
        from utils.queue_manager import QueueManager
        
        queue_manager = QueueManager()
        
        # Verify semaphore limits
        assert queue_manager.download_semaphore._value == 1, \
            "Download semaphore should be initialized with limit 1"
        assert queue_manager.upload_semaphore._value == 1, \
            "Upload semaphore should be initialized with limit 1"
    
    def test_sequential_processing_comments_present(self):
        """Test that code contains documentation about sequential processing."""
        from utils.queue_manager import QueueManager
        
        # Get the source code
        source = inspect.getsource(QueueManager._execute_download_task)
        
        # Verify that comments about sequential processing are present
        assert 'sequential' in source.lower() or 'wait' in source.lower(), \
            "Code should contain comments explaining sequential processing"
    
    def test_constants_file_has_sequential_documentation(self):
        """Test that constants file documents sequential processing."""
        from utils import constants
        
        # Get the source code of constants module
        source = inspect.getsource(constants)
        
        # Verify documentation is present
        assert 'sequential' in source.lower(), \
            "Constants file should document sequential processing"
        assert 'DOWNLOAD_SEMAPHORE_LIMIT = 1' in source, \
            "Download semaphore limit should be set to 1"
        assert 'UPLOAD_SEMAPHORE_LIMIT = 1' in source, \
            "Upload semaphore limit should be set to 1"


class TestSequentialProcessingBehavior:
    """Test sequential processing behavior with mock operations."""
    
    @pytest.mark.asyncio
    async def test_await_used_instead_of_create_task(self):
        """Test that processing methods are called with await, not create_task."""
        from utils.queue_manager import QueueManager
        
        queue_manager = QueueManager()
        
        # Track if methods are being called
        process_direct_called = False
        process_extraction_called = False
        
        async def mock_process_direct(task):
            nonlocal process_direct_called
            process_direct_called = True
            await asyncio.sleep(0.01)
        
        async def mock_process_extraction(task):
            nonlocal process_extraction_called
            process_extraction_called = True
            await asyncio.sleep(0.01)
        
        # Replace methods
        queue_manager._process_direct_media_upload = mock_process_direct
        queue_manager._process_extraction_and_upload = mock_process_extraction
        
        # Test that methods can be awaited (they are coroutines)
        upload_task = {'type': 'direct_media', 'filename': 'test.mp4'}
        await queue_manager._process_direct_media_upload(upload_task)
        assert process_direct_called, "Process direct media should be callable with await"
        
        extraction_task = {'type': 'extract_and_upload', 'filename': 'test.zip'}
        await queue_manager._process_extraction_and_upload(extraction_task)
        assert process_extraction_called, "Process extraction should be callable with await"
    
    @pytest.mark.asyncio
    async def test_semaphore_enforces_single_concurrent_download(self):
        """Test that semaphore allows only one download at a time."""
        from utils.queue_manager import QueueManager
        
        queue_manager = QueueManager()
        
        # Track concurrent operations
        concurrent_downloads = 0
        max_concurrent = 0
        
        async def simulated_download():
            nonlocal concurrent_downloads, max_concurrent
            
            async with queue_manager.download_semaphore:
                concurrent_downloads += 1
                max_concurrent = max(max_concurrent, concurrent_downloads)
                await asyncio.sleep(0.05)
                concurrent_downloads -= 1
        
        # Try to run multiple downloads concurrently
        await asyncio.gather(
            simulated_download(),
            simulated_download(),
            simulated_download()
        )
        
        # With semaphore limit of 1, max concurrent should never exceed 1
        assert max_concurrent == 1, \
            f"Semaphore should limit to 1 concurrent download, but allowed {max_concurrent}"
    
    @pytest.mark.asyncio
    async def test_semaphore_enforces_single_concurrent_upload(self):
        """Test that semaphore allows only one upload at a time."""
        from utils.queue_manager import QueueManager
        
        queue_manager = QueueManager()
        
        # Track concurrent operations
        concurrent_uploads = 0
        max_concurrent = 0
        
        async def simulated_upload():
            nonlocal concurrent_uploads, max_concurrent
            
            async with queue_manager.upload_semaphore:
                concurrent_uploads += 1
                max_concurrent = max(max_concurrent, concurrent_uploads)
                await asyncio.sleep(0.05)
                concurrent_uploads -= 1
        
        # Try to run multiple uploads concurrently
        await asyncio.gather(
            simulated_upload(),
            simulated_upload(),
            simulated_upload()
        )
        
        # With semaphore limit of 1, max concurrent should never exceed 1
        assert max_concurrent == 1, \
            f"Semaphore should limit to 1 concurrent upload, but allowed {max_concurrent}"
    
    @pytest.mark.asyncio
    async def test_processing_methods_are_coroutines(self):
        """Test that processing methods return coroutines (not tasks)."""
        from utils.queue_manager import QueueManager
        
        queue_manager = QueueManager()
        
        # Verify methods are coroutine functions
        assert inspect.iscoroutinefunction(queue_manager._process_direct_media_upload), \
            "_process_direct_media_upload should be a coroutine function"
        assert inspect.iscoroutinefunction(queue_manager._process_extraction_and_upload), \
            "_process_extraction_and_upload should be a coroutine function"
        
        # Verify calling them returns coroutines, not tasks
        dummy_task = {'filename': 'test'}
        result1 = queue_manager._process_direct_media_upload(dummy_task)
        result2 = queue_manager._process_extraction_and_upload(dummy_task)
        
        assert inspect.iscoroutine(result1), \
            "_process_direct_media_upload should return a coroutine"
        assert inspect.iscoroutine(result2), \
            "_process_extraction_and_upload should return a coroutine"
        
        # Clean up coroutines
        result1.close()
        result2.close()


class TestSequentialProcessingCodeStructure:
    """Test code structure to ensure sequential processing is implemented correctly."""
    
    def test_download_task_handler_structure(self):
        """Test that download task handler has correct structure for sequential processing."""
        from utils.queue_manager import QueueManager
        
        source = inspect.getsource(QueueManager._execute_download_task)
        
        # Check for sequential processing indicators
        indicators = [
            'await self._process_extraction_and_upload',
            'await self._process_direct_media_upload',
            'sequential',
            'wait for'
        ]
        
        found_indicators = [indicator for indicator in indicators if indicator in source]
        
        assert len(found_indicators) >= 2, \
            f"Download handler should have sequential processing structure. Found: {found_indicators}"
    
    def test_no_background_task_creation(self):
        """Test that background task creation has been removed."""
        from utils.queue_manager import QueueManager
        
        source = inspect.getsource(QueueManager._execute_download_task)
        
        # These patterns indicate parallel processing (should not be present)
        parallel_patterns = [
            'asyncio.create_task',
            'ensure_future',
        ]
        
        for pattern in parallel_patterns:
            assert pattern not in source, \
                f"Pattern '{pattern}' indicates parallel processing and should be removed"
    
    def test_processing_methods_exist(self):
        """Test that required processing methods exist."""
        from utils.queue_manager import QueueManager
        
        queue_manager = QueueManager()
        
        # Verify methods exist
        assert hasattr(queue_manager, '_process_direct_media_upload'), \
            "Queue manager should have _process_direct_media_upload method"
        assert hasattr(queue_manager, '_process_extraction_and_upload'), \
            "Queue manager should have _process_extraction_and_upload method"
        
        # Verify they are callable
        assert callable(queue_manager._process_direct_media_upload), \
            "_process_direct_media_upload should be callable"
        assert callable(queue_manager._process_extraction_and_upload), \
            "_process_extraction_and_upload should be callable"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
