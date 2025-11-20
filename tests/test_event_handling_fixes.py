"""
Unit tests for event handling fixes in queue manager.

Tests the fixes for:
1. AttributeError: 'dict' object has no attribute 'reply' 
2. Enhanced error handling for media upload failures
3. File validation and fallback upload mechanisms
"""

import asyncio
import pytest
import os
import tempfile
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import json

from utils.queue_manager import QueueManager


class TestEventHandlingFixes:
    """Test the fixes for event handling issues."""

    @pytest.fixture
    def mock_event_dict(self):
        """Mock serialized event (dict without reply method)."""
        return {
            'id': 123,
            'message': 'test message',
            'date': '2025-10-17T10:00:00',
            '_type': 'Message'
        }

    @pytest.fixture
    def mock_event_object(self):
        """Mock proper Telethon event object with reply method."""
        event = Mock()
        event.reply = AsyncMock()
        return event

    @pytest.fixture
    def mock_invalid_event(self):
        """Mock event with non-callable reply."""
        event = Mock()
        event.reply = "not_callable"
        return event

    @pytest.fixture
    def queue_manager(self):
        """Create a queue manager instance."""
        with patch('utils.queue_manager.os.makedirs'):
            return QueueManager()

    @pytest.fixture
    def temp_file(self):
        """Create a temporary file for testing."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as f:
            f.write(b'test video content')
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.fixture
    def missing_file_path(self):
        """Path to a non-existent file."""
        return "/nonexistent/path/test.mp4"

    @pytest.mark.asyncio
    async def test_execute_upload_task_with_dict_event(self, queue_manager, mock_event_dict, missing_file_path):
        """Test upload task execution with serialized event (dict) - should not crash."""
        task = {
            'filename': 'test.mp4',
            'file_path': missing_file_path,
            'event': mock_event_dict,
            'is_grouped': False
        }

        # This should not raise AttributeError
        await queue_manager._execute_upload_task(task)

    @pytest.mark.asyncio
    async def test_execute_upload_task_with_proper_event(self, queue_manager, mock_event_object, missing_file_path):
        """Test upload task execution with proper event object."""
        task = {
            'filename': 'test.mp4',
            'file_path': missing_file_path,
            'event': mock_event_object,
            'is_grouped': False
        }

        await queue_manager._execute_upload_task(task)
        
        # Should have called reply on proper event object
        mock_event_object.reply.assert_called_once_with("❌ File not found: test.mp4")

    @pytest.mark.asyncio
    async def test_execute_upload_task_with_invalid_event(self, queue_manager, mock_invalid_event, missing_file_path):
        """Test upload task execution with event that has non-callable reply."""
        task = {
            'filename': 'test.mp4',
            'file_path': missing_file_path,
            'event': mock_invalid_event,
            'is_grouped': False
        }

        # Should not crash with non-callable reply
        await queue_manager._execute_upload_task(task)

    @pytest.mark.asyncio
    async def test_execute_upload_task_no_event(self, queue_manager, missing_file_path):
        """Test upload task execution with no event."""
        task = {
            'filename': 'test.mp4',
            'file_path': missing_file_path,
            'event': None,
            'is_grouped': False
        }

        # Should handle gracefully
        await queue_manager._execute_upload_task(task)

    @pytest.mark.asyncio
    async def test_execute_grouped_upload_with_dict_event(self, queue_manager, mock_event_dict, temp_file):
        """Test grouped upload with serialized event."""
        task = {
            'filename': 'test_archive.zip - Videos',
            'file_paths': [temp_file],
            'event': mock_event_dict,
            'is_grouped': True,
            'media_type': 'videos',
            'source_archive': 'test_archive.zip'
        }

        with patch('utils.queue_manager.get_client'), \
             patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops, \
             patch('utils.queue_manager.ensure_target_entity'), \
             patch('utils.queue_manager.needs_video_processing', return_value=False), \
             patch('utils.queue_manager.CacheManager'):
            
            mock_ops_instance = Mock()
            mock_ops_instance.upload_media_grouped = AsyncMock()
            mock_telegram_ops.return_value = mock_ops_instance

            # Should not crash with dict event
            await queue_manager._execute_grouped_upload(task)

    @pytest.mark.asyncio
    async def test_execute_grouped_upload_with_proper_event(self, queue_manager, mock_event_object, temp_file):
        """Test grouped upload with proper event object."""
        task = {
            'filename': 'test_archive.zip - Videos',
            'file_paths': [temp_file],
            'event': mock_event_object,
            'is_grouped': True,
            'media_type': 'videos',
            'source_archive': 'test_archive.zip'
        }

        with patch('utils.queue_manager.get_client'), \
             patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops, \
             patch('utils.queue_manager.ensure_target_entity'), \
             patch('utils.queue_manager.needs_video_processing', return_value=False), \
             patch('utils.queue_manager.CacheManager'):
            
            mock_ops_instance = Mock()
            mock_ops_instance.upload_media_grouped = AsyncMock()
            mock_telegram_ops.return_value = mock_ops_instance

            await queue_manager._execute_grouped_upload(task)
            
            # Should have called reply on event
            assert mock_event_object.reply.call_count >= 1

    @pytest.mark.asyncio
    async def test_file_validation_in_grouped_upload(self, queue_manager, mock_event_object):
        """Test file validation in grouped upload."""
        # Create multiple temp files
        temp_files = []
        for i in range(3):
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as f:
                f.write(b'test content ' * 100)  # Add some content
                temp_files.append(f.name)

        # Add a missing file
        missing_file = "/nonexistent/file.mp4"
        all_files = temp_files + [missing_file]

        task = {
            'filename': 'test_archive.zip - Videos',
            'file_paths': all_files,
            'event': mock_event_object,
            'is_grouped': True,
            'media_type': 'videos',
            'source_archive': 'test_archive.zip'
        }

        with patch('utils.queue_manager.get_client'), \
             patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops, \
             patch('utils.queue_manager.ensure_target_entity'), \
             patch('utils.queue_manager.needs_video_processing', return_value=False), \
             patch('utils.queue_manager.CacheManager'):
            
            mock_ops_instance = Mock()
            mock_ops_instance.upload_media_grouped = AsyncMock()
            mock_telegram_ops.return_value = mock_ops_instance

            await queue_manager._execute_grouped_upload(task)
            
            # Should have filtered out the missing file
            upload_call_args = mock_ops_instance.upload_media_grouped.call_args
            if upload_call_args:
                uploaded_files = upload_call_args[0][1]  # Second argument is file list
                assert len(uploaded_files) == 3  # Only valid files
                assert missing_file not in uploaded_files

        # Cleanup
        for f in temp_files:
            if os.path.exists(f):
                os.unlink(f)

    @pytest.mark.asyncio
    async def test_grouped_upload_fallback_to_individual(self, queue_manager, mock_event_object):
        """Test fallback to individual uploads when grouped upload fails."""
        temp_files = []
        for i in range(2):
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as f:
                f.write(b'test content ' * 100)
                temp_files.append(f.name)

        task = {
            'filename': 'test_archive.zip - Videos',
            'file_paths': temp_files,
            'event': mock_event_object,
            'is_grouped': True,
            'media_type': 'videos',
            'source_archive': 'test_archive.zip'
        }

        with patch('utils.queue_manager.get_client'), \
             patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops, \
             patch('utils.queue_manager.ensure_target_entity'), \
             patch('utils.queue_manager.needs_video_processing', return_value=False), \
             patch('utils.queue_manager.CacheManager'):
            
            mock_ops_instance = Mock()
            # Simulate grouped upload failure
            mock_ops_instance.upload_media_grouped = AsyncMock(
                side_effect=Exception("The provided media object is invalid")
            )
            # Individual upload should succeed
            mock_ops_instance.upload_media_file = AsyncMock()
            mock_telegram_ops.return_value = mock_ops_instance

            await queue_manager._execute_grouped_upload(task)
            
            # Should have attempted grouped upload first
            mock_ops_instance.upload_media_grouped.assert_called_once()
            
            # Should have fallen back to individual uploads
            assert mock_ops_instance.upload_media_file.call_count == 2

        # Cleanup
        for f in temp_files:
            if os.path.exists(f):
                os.unlink(f)

    @pytest.mark.asyncio
    async def test_zero_size_file_filtering(self, queue_manager, mock_event_object):
        """Test that zero-size files are filtered out."""
        # Create a zero-size file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as f:
            zero_size_file = f.name

        # Create a normal file  
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as f:
            f.write(b'content')
            normal_file = f.name

        task = {
            'filename': 'test_archive.zip - Videos',
            'file_paths': [zero_size_file, normal_file],
            'event': mock_event_object,
            'is_grouped': True,
            'media_type': 'videos',
            'source_archive': 'test_archive.zip'
        }

        with patch('utils.queue_manager.get_client'), \
             patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops, \
             patch('utils.queue_manager.ensure_target_entity'), \
             patch('utils.queue_manager.needs_video_processing', return_value=False), \
             patch('utils.queue_manager.CacheManager'):
            
            mock_ops_instance = Mock()
            mock_ops_instance.upload_media_grouped = AsyncMock()
            mock_telegram_ops.return_value = mock_ops_instance

            await queue_manager._execute_grouped_upload(task)
            
            # Should have filtered out zero-size file
            upload_call_args = mock_ops_instance.upload_media_grouped.call_args
            if upload_call_args:
                uploaded_files = upload_call_args[0][1]
                assert len(uploaded_files) == 1
                assert normal_file in uploaded_files
                assert zero_size_file not in uploaded_files

        # Cleanup
        for f in [zero_size_file, normal_file]:
            if os.path.exists(f):
                os.unlink(f)

    @pytest.mark.asyncio
    async def test_event_reply_exception_handling(self, queue_manager, missing_file_path):
        """Test handling of exceptions during event.reply calls."""
        event = Mock()
        event.reply = AsyncMock(side_effect=Exception("Network error"))
        
        task = {
            'filename': 'test.mp4',
            'file_path': missing_file_path,
            'event': event,
            'is_grouped': False
        }

        # Should not crash when reply fails
        await queue_manager._execute_upload_task(task)

    @pytest.mark.asyncio
    async def test_upload_message_edit_exception_handling(self, queue_manager, temp_file):
        """Test handling of exceptions during upload message edits."""
        event = Mock()
        event.reply = AsyncMock()
        
        # Mock upload message that fails on edit
        upload_msg = Mock()
        upload_msg.edit = AsyncMock(side_effect=Exception("Message edit failed"))
        event.reply.return_value = upload_msg

        task = {
            'filename': 'test.mp4',
            'file_path': temp_file,
            'event': event,
            'is_grouped': False
        }

        with patch('utils.queue_manager.get_client'), \
             patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops, \
             patch('utils.queue_manager.ensure_target_entity'), \
             patch('utils.queue_manager.needs_video_processing', return_value=False), \
             patch('utils.queue_manager.CacheManager'):
            
            mock_ops_instance = Mock()
            mock_ops_instance.upload_media_file = AsyncMock()
            mock_telegram_ops.return_value = mock_ops_instance

            # Should handle edit failures gracefully
            await queue_manager._execute_upload_task(task)


class TestEventSerialization:
    """Test event serialization and deserialization scenarios."""

    def test_serialized_event_structure(self):
        """Test that serialized events are proper dicts."""
        from utils.cache_manager import make_serializable
        
        # Mock a Telethon event
        event = Mock()
        event.id = 123
        event.message = "test"
        event.date = "2025-10-17"
        event.reply = AsyncMock()
        
        serialized = make_serializable(event)
        
        # Should be a dict
        assert isinstance(serialized, dict)
        
        # Should not have reply method
        assert 'reply' not in serialized or not callable(serialized.get('reply'))

    def test_make_serializable_with_event_like_object(self):
        """Test make_serializable with event-like objects."""
        from utils.cache_manager import make_serializable
        
        # Create a mock event with to_dict method
        event = Mock()
        event.id = 123
        event.message = 'test'
        event.date = '2025-10-17'
        event.to_dict = Mock(return_value={
            'id': 123,
            'message': 'test',
            'date': '2025-10-17'
        })
        
        result = make_serializable(event)
        
        assert isinstance(result, dict)
        assert result['id'] == 123
        assert result['message'] == 'test'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])