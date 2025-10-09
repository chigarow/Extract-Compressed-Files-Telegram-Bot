"""
Test suite for FloodWaitError handling in queue manager.

This test suite verifies:
1. FloodWaitError is caught and handled properly
2. Wait time is extracted correctly from the exception
3. Retry is scheduled with the proper wait time from Telegram
4. Files are not deleted during flood wait retries
5. Queue processor continues after FloodWaitError
6. User receives informative messages about rate limits
"""

import pytest
import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch, call
from telethon.errors import FloodWaitError

# Import the modules we're testing
from utils.queue_manager import QueueManager
from utils.constants import MAX_RETRY_ATTEMPTS, RETRY_BASE_INTERVAL


class TestFloodWaitErrorHandling:
    """Test FloodWaitError handling in upload queue."""
    
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
    def upload_task(self, tmp_path, mock_event):
        """Create a test upload task."""
        # Create a test file
        test_file = tmp_path / "test_video.mp4"
        test_file.write_text("test content")
        
        return {
            'type': 'direct_media',
            'event': mock_event,
            'file_path': str(test_file),
            'filename': 'test_video.mp4',
            'size_bytes': 100,
            'retry_count': 0
        }
    
    @pytest.mark.asyncio
    async def test_flood_wait_error_caught_and_handled(self, queue_manager, upload_task):
        """Test that FloodWaitError is caught and handled properly."""
        
        # Create FloodWaitError with specific wait time
        flood_error = FloodWaitError(None)
        flood_error.seconds = 1678  # 28 minutes as in the user's log
        
        # Mock the TelegramOperations to raise FloodWaitError
        with patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops:
            mock_ops_instance = MagicMock()
            mock_ops_instance.upload_media_file = AsyncMock(side_effect=flood_error)
            mock_telegram_ops.return_value = mock_ops_instance
            
            # Mock other dependencies
            with patch('utils.queue_manager.get_client'), \
                 patch('utils.queue_manager.ensure_target_entity'), \
                 patch('utils.queue_manager.CacheManager'):
                
                # Execute the upload task
                await queue_manager._execute_upload_task(upload_task)
        
        # Verify that the task was added to retry queue
        # The file should still exist (not deleted)
        assert os.path.exists(upload_task['file_path']), "File should not be deleted on FloodWaitError"
        
        # Verify that reply was called with informative message
        upload_task['event'].reply.assert_called_once()
        call_args = upload_task['event'].reply.call_args[0][0]
        assert 'rate limit' in call_args.lower()
        assert '28m' in call_args or '1678' in call_args  # Should mention wait time
    
    @pytest.mark.asyncio
    async def test_flood_wait_retry_uses_telegram_wait_time(self, queue_manager, upload_task):
        """Test that retry delay uses Telegram's wait time, not exponential backoff."""
        
        flood_error = FloodWaitError(None)
        flood_error.seconds = 120  # 2 minutes
        
        with patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops:
            mock_ops_instance = MagicMock()
            mock_ops_instance.upload_media_file = AsyncMock(side_effect=flood_error)
            mock_telegram_ops.return_value = mock_ops_instance
            
            with patch('utils.queue_manager.get_client'), \
                 patch('utils.queue_manager.ensure_target_entity'), \
                 patch('utils.queue_manager.CacheManager'), \
                 patch.object(queue_manager, '_add_to_retry_queue', new=AsyncMock()) as mock_retry:
                
                await queue_manager._execute_upload_task(upload_task)
                
                # Verify retry was scheduled
                mock_retry.assert_called_once()
                retry_task = mock_retry.call_args[0][0]
                
                # Verify wait time is from Telegram (120s) + buffer (5s) = 125s
                # Not exponential backoff which would be 5s for first retry
                current_time = time.time()
                scheduled_time = retry_task['retry_after']
                wait_time = scheduled_time - current_time
                
                # Allow some timing tolerance (±2 seconds)
                assert 123 <= wait_time <= 127, f"Wait time should be ~125s, got {wait_time}s"
                assert retry_task['flood_wait'] is True
                assert retry_task['telegram_wait_seconds'] == 120
    
    @pytest.mark.asyncio
    async def test_flood_wait_does_not_count_against_max_retries(self, queue_manager, upload_task):
        """Test that FloodWaitError retries don't fail after MAX_RETRY_ATTEMPTS."""
        
        # Set task to already have max retries
        upload_task['retry_count'] = MAX_RETRY_ATTEMPTS + 5
        
        flood_error = FloodWaitError(None)
        flood_error.seconds = 30
        
        with patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops:
            mock_ops_instance = MagicMock()
            mock_ops_instance.upload_media_file = AsyncMock(side_effect=flood_error)
            mock_telegram_ops.return_value = mock_ops_instance
            
            with patch('utils.queue_manager.get_client'), \
                 patch('utils.queue_manager.ensure_target_entity'), \
                 patch('utils.queue_manager.CacheManager'), \
                 patch.object(queue_manager, '_add_to_retry_queue', new=AsyncMock()) as mock_retry:
                
                await queue_manager._execute_upload_task(upload_task)
                
                # Should still schedule retry despite high retry count
                mock_retry.assert_called_once()
                
                # File should not be deleted
                assert os.path.exists(upload_task['file_path'])
    
    @pytest.mark.asyncio
    async def test_regular_error_uses_exponential_backoff(self, queue_manager, upload_task):
        """Test that non-FloodWait errors use exponential backoff."""
        
        # Regular exception (not FloodWaitError)
        regular_error = Exception("Network timeout")
        
        with patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops:
            mock_ops_instance = MagicMock()
            mock_ops_instance.upload_media_file = AsyncMock(side_effect=regular_error)
            mock_telegram_ops.return_value = mock_ops_instance
            
            with patch('utils.queue_manager.get_client'), \
                 patch('utils.queue_manager.ensure_target_entity'), \
                 patch('utils.queue_manager.CacheManager'), \
                 patch.object(queue_manager, '_add_to_retry_queue', new=AsyncMock()) as mock_retry:
                
                await queue_manager._execute_upload_task(upload_task)
                
                mock_retry.assert_called_once()
                retry_task = mock_retry.call_args[0][0]
                
                # Should use exponential backoff (5s for first retry)
                current_time = time.time()
                wait_time = retry_task['retry_after'] - current_time
                
                # First retry should be ~5 seconds (RETRY_BASE_INTERVAL)
                assert 3 <= wait_time <= 7, f"Wait time should be ~5s, got {wait_time}s"
                assert 'flood_wait' not in retry_task or not retry_task['flood_wait']
    
    @pytest.mark.asyncio
    async def test_queue_processor_continues_after_flood_wait(self, queue_manager, upload_task, tmp_path):
        """Test that upload queue processor continues after FloodWaitError."""
        
        # Create second task
        test_file_2 = tmp_path / "test_photo.jpg"
        test_file_2.write_text("test content 2")
        upload_task_2 = upload_task.copy()
        upload_task_2['file_path'] = str(test_file_2)
        upload_task_2['filename'] = 'test_photo.jpg'
        
        flood_error = FloodWaitError(None)
        flood_error.seconds = 10
        
        # First upload fails with FloodWaitError, second succeeds
        upload_call_count = {'count': 0}
        
        async def upload_side_effect(*args, **kwargs):
            upload_call_count['count'] += 1
            if upload_call_count['count'] == 1:
                raise flood_error
            # Second upload succeeds
            return True
        
        with patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops:
            mock_ops_instance = MagicMock()
            mock_ops_instance.upload_media_file = AsyncMock(side_effect=upload_side_effect)
            mock_telegram_ops.return_value = mock_ops_instance
            
            with patch('utils.queue_manager.get_client'), \
                 patch('utils.queue_manager.ensure_target_entity'), \
                 patch('utils.queue_manager.CacheManager'), \
                 patch.object(queue_manager, '_add_to_retry_queue', new=AsyncMock()):
                
                # Add both tasks to queue
                await queue_manager.add_upload_task(upload_task)
                await queue_manager.add_upload_task(upload_task_2)
                
                # Wait for processor to handle both tasks
                await asyncio.sleep(0.5)
                
                # Both upload attempts should have been made
                assert upload_call_count['count'] == 2, "Processor should continue after FloodWaitError"
                
                # Stop the processor
                await queue_manager.stop_all_tasks()
    
    @pytest.mark.asyncio
    async def test_flood_wait_message_formats_time_correctly(self, queue_manager, upload_task):
        """Test that user messages format wait time correctly."""
        
        test_cases = [
            (30, '30s'),           # 30 seconds
            (90, '1m 30s'),        # 1 minute 30 seconds
            (1678, '27m 58s'),     # 27 minutes 58 seconds (user's case)
            (3600, '1h'),          # 1 hour
            (7200, '2h'),          # 2 hours
            (3665, '1h 1m 5s'),    # 1 hour 1 minute 5 seconds
        ]
        
        for seconds, expected_format in test_cases:
            flood_error = FloodWaitError(None)
            flood_error.seconds = seconds
            
            # Reset the event mock
            upload_task['event'].reply.reset_mock()
            
            with patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops:
                mock_ops_instance = MagicMock()
                mock_ops_instance.upload_media_file = AsyncMock(side_effect=flood_error)
                mock_telegram_ops.return_value = mock_ops_instance
                
                with patch('utils.queue_manager.get_client'), \
                     patch('utils.queue_manager.ensure_target_entity'), \
                     patch('utils.queue_manager.CacheManager'), \
                     patch.object(queue_manager, '_add_to_retry_queue', new=AsyncMock()):
                    
                    await queue_manager._execute_upload_task(upload_task)
                    
                    # Check the reply message
                    call_args = upload_task['event'].reply.call_args[0][0]
                    assert expected_format in call_args, \
                        f"Expected '{expected_format}' in message for {seconds}s wait, got: {call_args}"
    
    @pytest.mark.asyncio
    async def test_flood_wait_without_event_logs_properly(self, queue_manager, upload_task):
        """Test that FloodWaitError is logged properly when no event is available."""
        
        # Remove event from task (background task scenario)
        upload_task['event'] = None
        
        flood_error = FloodWaitError(None)
        flood_error.seconds = 100
        
        with patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops:
            mock_ops_instance = MagicMock()
            mock_ops_instance.upload_media_file = AsyncMock(side_effect=flood_error)
            mock_telegram_ops.return_value = mock_ops_instance
            
            with patch('utils.queue_manager.get_client'), \
                 patch('utils.queue_manager.ensure_target_entity'), \
                 patch('utils.queue_manager.CacheManager'), \
                 patch.object(queue_manager, '_add_to_retry_queue', new=AsyncMock()), \
                 patch('utils.queue_manager.logger') as mock_logger:
                
                await queue_manager._execute_upload_task(upload_task)
                
                # Verify logging occurred
                assert any('FloodWaitError' in str(call) for call in mock_logger.warning.call_args_list)
                assert any('100 seconds' in str(call) for call in mock_logger.warning.call_args_list)
    
    @pytest.mark.asyncio
    async def test_file_preserved_through_multiple_flood_waits(self, queue_manager, upload_task):
        """Test that file is preserved through multiple consecutive FloodWaitErrors."""
        
        flood_error = FloodWaitError(None)
        flood_error.seconds = 30
        
        with patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops:
            mock_ops_instance = MagicMock()
            mock_ops_instance.upload_media_file = AsyncMock(side_effect=flood_error)
            mock_telegram_ops.return_value = mock_ops_instance
            
            with patch('utils.queue_manager.get_client'), \
                 patch('utils.queue_manager.ensure_target_entity'), \
                 patch('utils.queue_manager.CacheManager'), \
                 patch.object(queue_manager, '_add_to_retry_queue', new=AsyncMock()):
                
                # Simulate multiple retry attempts
                for i in range(5):
                    upload_task['retry_count'] = i
                    await queue_manager._execute_upload_task(upload_task)
                    
                    # File should exist after each attempt
                    assert os.path.exists(upload_task['file_path']), \
                        f"File should exist after retry attempt {i+1}"


class TestProgressCallbackRateLimit:
    """Test that progress callbacks handle rate limits gracefully."""
    
    @pytest.mark.asyncio
    async def test_progress_callback_handles_flood_wait(self):
        """Test that progress callback handles FloodWaitError gracefully."""
        from utils.telegram_operations import TelegramOperations
        
        # Create mock status message
        status_msg = MagicMock()
        
        # First edit succeeds, second hits rate limit, third succeeds
        edit_call_count = {'count': 0}
        
        async def edit_side_effect(text):
            edit_call_count['count'] += 1
            if edit_call_count['count'] == 2:
                flood_error = FloodWaitError(None)
                flood_error.seconds = 10
                raise flood_error
        
        status_msg.edit = AsyncMock(side_effect=edit_side_effect)
        
        # Create TelegramOperations instance
        telegram_ops = TelegramOperations()
        callback = telegram_ops.create_progress_callback(status_msg, "test.mp4")
        
        # Simulate progress updates
        await callback(1000, 10000)      # 10% - should succeed
        await asyncio.sleep(16)          # Wait for throttle
        await callback(2000, 10000)      # 20% - should hit rate limit
        await asyncio.sleep(16)          # Wait for throttle
        await callback(3000, 10000)      # 30% - should be skipped due to rate limit
        
        # Only first call should go through, second fails, third is skipped
        assert edit_call_count['count'] == 2
    
    @pytest.mark.asyncio  
    async def test_progress_callback_conservative_throttling(self):
        """Test that progress callback uses conservative throttling (15% intervals)."""
        from utils.telegram_operations import TelegramOperations
        
        status_msg = MagicMock()
        status_msg.edit = AsyncMock()
        
        telegram_ops = TelegramOperations()
        callback = telegram_ops.create_progress_callback(status_msg, "test.mp4")
        
        # Simulate rapid progress updates
        total = 10000
        for i in range(0, total, 100):
            await callback(i, total)
        
        # Should only update at 0%, 15%, 30%, 45%, 60%, 75%, 90% (7 times)
        # Plus initial 0% = 7-8 calls maximum
        assert status_msg.edit.call_count <= 8, \
            f"Should have max 8 progress updates, got {status_msg.edit.call_count}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
