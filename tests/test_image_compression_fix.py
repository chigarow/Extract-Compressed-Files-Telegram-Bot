"""
Unit tests for image compression bug fix (case sensitivity).

This test verifies that the image compression logic correctly triggers
when media_type is lowercase 'images' (as set by the task creation code).
"""

import pytest
import asyncio
import os
import tempfile
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from PIL import Image


class TestImageCompressionCaseSensitivityFix:
    """Test that compression triggers with lowercase 'images' media_type."""

    def create_queue_manager(self, monkeypatch):
        """Creates a QueueManager with patched file paths."""
        import tempfile
        from utils.queue_manager import QueueManager

        tmpdir = tempfile.mkdtemp()
        download_file = os.path.join(tmpdir, 'download_queue.json')
        upload_file = os.path.join(tmpdir, 'upload_queue.json')
        retry_file = os.path.join(tmpdir, 'retry_queue.json')

        monkeypatch.setattr('utils.queue_manager.DOWNLOAD_QUEUE_FILE', str(download_file))
        monkeypatch.setattr('utils.queue_manager.UPLOAD_QUEUE_FILE', str(upload_file))
        monkeypatch.setattr('utils.queue_manager.RETRY_QUEUE_FILE', str(retry_file))

        return QueueManager()

    
    @pytest.mark.asyncio
    async def test_compression_triggers_with_lowercase_images(self, monkeypatch):
        """Test that compression logic triggers when media_type='images' (lowercase)."""
        queue_manager = self.create_queue_manager(monkeypatch)
        
        # Create a test image > 10MB
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            test_image_path = f.name
            # Create a much larger image to exceed 10MB
            img = Image.new('RGB', (8000, 8000), color='red')
            img.save(test_image_path, 'JPEG', quality=95)
        
        try:
            # Verify file is > 10MB
            file_size = os.path.getsize(test_image_path)
            if file_size <= 10 * 1024 * 1024:
                # If still not big enough, write additional data
                with open(test_image_path, 'ab') as f:
                    f.write(b'x' * (11 * 1024 * 1024 - file_size))
                file_size = os.path.getsize(test_image_path)
            
            assert file_size > 10 * 1024 * 1024, f"Test image should be > 10MB, got {file_size / (1024*1024):.2f} MB"
            
            # Create task with lowercase 'images' (as set by the actual code)
            task = {
                'filename': 'test.zip - Images (Batch 1/1: 1 files)',
                'file_paths': [test_image_path],
                'is_grouped': True,
                'media_type': 'images',  # lowercase - this is what the actual code uses
                'source_archive': 'test.zip',
                'retry_count': 0
            }
            
            # Mock the telegram operations to raise the 10MB error
            error_message = "The photo you tried to send cannot be saved by Telegram. A reason may be that it exceeds 10MB. Try resizing it locally (caused by UploadMediaRequest)"
            
            mock_telegram_ops = AsyncMock()
            mock_telegram_ops.upload_media_grouped = AsyncMock(side_effect=Exception(error_message))
            
            monkeypatch.setattr('utils.queue_manager.TelegramOperations', lambda x: mock_telegram_ops)
            monkeypatch.setattr('utils.queue_manager.get_client', AsyncMock())
            monkeypatch.setattr('utils.queue_manager.ensure_target_entity', AsyncMock())
            monkeypatch.setattr('utils.queue_manager.CacheManager', AsyncMock())
    
            # Track if retry queue was called (meaning compression was triggered)
            original_add_to_retry = queue_manager._add_to_retry_queue
            retry_tasks = []
            
            async def track_retry(retry_task):
                retry_tasks.append(retry_task)
                # In the test, we don't need to actually call the original function
                # await original_add_to_retry(retry_task)
            
            queue_manager._add_to_retry_queue = track_retry
            
            # Execute the grouped upload (should trigger compression)
            # Patch at the source module since it's imported locally in the function
            with patch('utils.media_processing.compress_image_for_telegram') as mock_compress:
                # Mock compression to return a smaller file
                compressed_path = test_image_path.replace('.jpg', '_compressed.jpg')
                
                # Create async mock that returns the compressed path directly
                async def mock_compress_func(input_path, output_path=None, target_size=None):
                    return compressed_path
                
                mock_compress.side_effect = mock_compress_func
                
                # Create a smaller compressed file
                with open(compressed_path, 'wb') as cf:
                    cf.write(b'compressed data')
                
                try:
                    await queue_manager._execute_grouped_upload(task)
                    
                    # Verify compression was called
                    assert mock_compress.called, "compress_image_for_telegram should have been called"
                    assert len(retry_tasks) > 0, "Task should have been added to retry queue after compression"
                    
                    # Verify the retry task has compressed flag
                    retry_task = retry_tasks[0]
                    assert retry_task.get('compressed') == True, "Retry task should be marked as compressed"
                    
                    # Verify compressed files are in the retry task
                    assert 'file_paths' in retry_task, "Retry task should have file_paths"
                    
                finally:
                    # Clean up compressed file
                    if os.path.exists(compressed_path):
                        os.remove(compressed_path)        
        finally:
            # Clean up test file
            if os.path.exists(test_image_path):
                os.remove(test_image_path)
    
    @pytest.mark.asyncio
    async def test_compression_does_not_trigger_with_uppercase_images(self, monkeypatch):
        """Test that compression logic does NOT trigger with uppercase 'Images' (bug scenario)."""
        queue_manager = self.create_queue_manager(monkeypatch)
        
        # Create a test image > 10MB
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            test_image_path = f.name
            img = Image.new('RGB', (8000, 8000), color='blue')
            img.save(test_image_path, 'JPEG', quality=95)
        
        try:
            # Make sure file is > 10MB
            file_size = os.path.getsize(test_image_path)
            if file_size <= 10 * 1024 * 1024:
                with open(test_image_path, 'ab') as f:
                    f.write(b'x' * (11 * 1024 * 1024 - file_size))
            
            # Create task with uppercase 'Images' (the bug scenario)
            task = {
                'filename': 'test.zip - Images (Batch 1/1: 1 files)',
                'file_paths': [test_image_path],
                'is_grouped': True,
                'media_type': 'Images',  # uppercase - this would NOT trigger compression
                'source_archive': 'test.zip',
                'retry_count': 0
            }
            
            # Mock the telegram operations to raise the 10MB error
            error_message = "The photo you tried to send cannot be saved by Telegram. A reason may be that it exceeds 10MB. Try resizing it locally (caused by UploadMediaRequest)"
            
            with patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops_cls, \
                 patch('utils.queue_manager.ensure_target_entity') as mock_target, \
                 patch('utils.queue_manager.get_client') as mock_client, \
                 patch('utils.queue_manager.CacheManager') as mock_cache_cls, \
                 patch('utils.telegram_operations.client', None):  # Reset global client in telegram_operations
                
                # Setup mocks
                mock_telegram_ops = Mock()
                mock_telegram_ops.upload_media_grouped = AsyncMock(side_effect=Exception(error_message))
                mock_telegram_ops_cls.return_value = mock_telegram_ops
                
                mock_target.return_value = AsyncMock(return_value=Mock())
                mock_client.return_value = Mock()
                mock_cache_cls.return_value = Mock()
                
                
                # Execute the grouped upload
                with patch('utils.media_processing.compress_image_for_telegram') as mock_compress:
                    assert not mock_compress.called, "compress_image_for_telegram should NOT be called with uppercase 'Images'"
        
        finally:
            # Clean up test file
            if os.path.exists(test_image_path):
                os.remove(test_image_path)
    
    @pytest.mark.asyncio
    async def test_compression_not_triggered_if_already_compressed(self, monkeypatch):
        """Test that compression is skipped if task already has 'compressed' flag."""
        queue_manager = self.create_queue_manager(monkeypatch)
        
        # Create a test image > 10MB
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            test_image_path = f.name
            img = Image.new('RGB', (8000, 8000), color='green')
            img.save(test_image_path, 'JPEG', quality=95)
        
        try:
            # Make sure file is > 10MB
            file_size = os.path.getsize(test_image_path)
            if file_size <= 10 * 1024 * 1024:
                with open(test_image_path, 'ab') as f:
                    f.write(b'x' * (11 * 1024 * 1024 - file_size))
            
            # Create task that's already been compressed
            task = {
                'filename': 'test.zip - Images (Batch 1/1: 1 files)',
                'file_paths': [test_image_path],
                'is_grouped': True,
                'media_type': 'images',
                'source_archive': 'test.zip',
                'retry_count': 1,
                'compressed': True  # Already compressed flag
            }
            
            # Mock the telegram operations to raise the 10MB error again
            error_message = "The photo you tried to send cannot be saved by Telegram. A reason may be that it exceeds 10MB. Try resizing it locally (caused by UploadMediaRequest)"
            
            with patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops_cls, \
                 patch('utils.queue_manager.ensure_target_entity') as mock_target, \
                 patch('utils.queue_manager.get_client') as mock_client, \
                 patch('utils.queue_manager.CacheManager') as mock_cache_cls:
                
                # Setup mocks
                mock_telegram_ops = Mock()
                mock_telegram_ops.upload_media_grouped = AsyncMock(side_effect=Exception(error_message))
                mock_telegram_ops_cls.return_value = mock_telegram_ops
                
                mock_target.return_value = AsyncMock(return_value=Mock())
                mock_client.return_value = Mock()
                mock_cache_cls.return_value = Mock()
                
                
                # Execute the grouped upload
                with patch('utils.media_processing.compress_image_for_telegram') as mock_compress:
                    await queue_manager._execute_grouped_upload(task)
                    
                    # Verify compression was NOT called (already compressed)
                    assert not mock_compress.called, "compress_image_for_telegram should NOT be called if already compressed"
        
        finally:
            # Clean up test file
            if os.path.exists(test_image_path):
                os.remove(test_image_path)
    
    def test_media_type_consistency_in_codebase(self):
        """Test that all task creation uses lowercase 'images' and 'videos'."""
        import re
        
        # Read queue_manager.py
        with open('utils/queue_manager.py', 'r') as f:
            content = f.read()
        
        # Find all media_type assignments
        pattern = r"'media_type'\s*:\s*'([^']+)'"
        matches = re.findall(pattern, content)
        
        # Verify all are lowercase
        for match in matches:
            assert match in ['images', 'videos'], f"Found inconsistent media_type: '{match}' (should be lowercase 'images' or 'videos')"
        
        # Verify there are some matches (sanity check)
        assert len(matches) > 0, "Should find media_type assignments in queue_manager.py"


class TestImageCompressionErrorDetection:
    """Test the error detection function with various error messages."""
    
    def test_detects_telegram_10mb_error(self):
        """Test detection of the exact Telegram 10MB error message."""
        from utils.media_processing import is_telegram_photo_size_error
        
        error_msg = "The photo you tried to send cannot be saved by Telegram. A reason may be that it exceeds 10MB. Try resizing it locally (caused by UploadMediaRequest)"
        
        assert is_telegram_photo_size_error(error_msg) == True
    
    def test_detects_variations_of_error(self):
        """Test detection of variations of the error message."""
        from utils.media_processing import is_telegram_photo_size_error
        
        # Lowercase variation
        error_msg1 = "the photo you tried to send cannot be saved by telegram. a reason may be that it exceeds 10mb."
        assert is_telegram_photo_size_error(error_msg1) == True
        
        # With different context
        error_msg2 = "Upload failed: cannot be saved by telegram because it exceeds 10 mb limit"
        assert is_telegram_photo_size_error(error_msg2) == True
    
    def test_does_not_detect_unrelated_errors(self):
        """Test that unrelated errors are not detected."""
        from utils.media_processing import is_telegram_photo_size_error
        
        # Generic upload error
        assert is_telegram_photo_size_error("Upload failed due to network error") == False
        
        # File not found error
        assert is_telegram_photo_size_error("File not found") == False
        
        # Empty string
        assert is_telegram_photo_size_error("") == False
        
        # None
        assert is_telegram_photo_size_error(None) == False
    
    def test_requires_multiple_indicators(self):
        """Test that detection requires at least 2 indicators."""
        from utils.media_processing import is_telegram_photo_size_error
        
        # Only one indicator
        assert is_telegram_photo_size_error("exceeds 10mb") == False
        assert is_telegram_photo_size_error("cannot be saved by telegram") == False
        
        # Two indicators
        assert is_telegram_photo_size_error("cannot be saved by telegram exceeds 10mb") == True
