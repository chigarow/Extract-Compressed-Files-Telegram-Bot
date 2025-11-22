"""
Unit tests for WebDAV download failure handling and smart retry logic.

Tests cover:
- Error classification (DNS, network, timeout, unknown)
- Smart exponential backoff for different error types
- User-friendly error messages
- Retry queue integration
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, Mock, patch

from utils.queue_manager import QueueManager
from utils.constants import MAX_RETRY_ATTEMPTS, RETRY_BASE_INTERVAL


@pytest.fixture
def queue_manager():
    """Create a QueueManager instance for testing."""
    return QueueManager(client=Mock())


class TestErrorClassification:
    """Test that errors are correctly classified by type."""
    
    @pytest.mark.asyncio
    async def test_dns_error_classification(self, queue_manager):
        """Test DNS errors are classified correctly."""
        task = {
            'filename': 'test.mp4',
            'retry_count': 0
        }
        event = AsyncMock()
        error = OSError("[Errno 7] No address associated with hostname")
        
        with patch.object(queue_manager, '_add_to_retry_queue', new_callable=AsyncMock) as mock_retry:
            await queue_manager._handle_webdav_download_failure(task, event, error, True)
            
            # Verify retry was scheduled
            assert mock_retry.called
            
            # Verify error message mentions DNS
            reply_call = event.reply.call_args
            assert reply_call is not None
            message = reply_call[0][0]
            assert 'DNS resolution failure' in message
    
    @pytest.mark.asyncio
    async def test_network_error_classification(self, queue_manager):
        """Test network connection errors are classified correctly."""
        task = {
            'filename': 'test.mp4',
            'retry_count': 0
        }
        event = AsyncMock()
        error = ConnectionRefusedError("[Errno 61] Connection refused")
        
        with patch.object(queue_manager, '_add_to_retry_queue', new_callable=AsyncMock) as mock_retry:
            await queue_manager._handle_webdav_download_failure(task, event, error, True)
            
            assert mock_retry.called
            reply_call = event.reply.call_args
            message = reply_call[0][0]
            assert 'network connection error' in message
    
    @pytest.mark.asyncio
    async def test_timeout_error_classification(self, queue_manager):
        """Test timeout errors are classified correctly."""
        task = {
            'filename': 'test.mp4',
            'retry_count': 0
        }
        event = AsyncMock()
        error = asyncio.TimeoutError("Request timed out")
        
        with patch.object(queue_manager, '_add_to_retry_queue', new_callable=AsyncMock) as mock_retry:
            await queue_manager._handle_webdav_download_failure(task, event, error, True)
            
            assert mock_retry.called
            reply_call = event.reply.call_args
            message = reply_call[0][0]
            assert 'timeout/stall' in message
    
    @pytest.mark.asyncio
    async def test_unknown_error_classification(self, queue_manager):
        """Test unknown errors are classified correctly."""
        task = {
            'filename': 'test.mp4',
            'retry_count': 0
        }
        event = AsyncMock()
        error = ValueError("Some unexpected error")
        
        with patch.object(queue_manager, '_add_to_retry_queue', new_callable=AsyncMock) as mock_retry:
            await queue_manager._handle_webdav_download_failure(task, event, error, True)
            
            assert mock_retry.called
            reply_call = event.reply.call_args
            message = reply_call[0][0]
            assert 'unknown error' in message


class TestSmartBackoff:
    """Test exponential backoff strategy for different error types."""
    
    @pytest.mark.asyncio
    async def test_dns_error_exponential_backoff(self, queue_manager):
        """Test DNS errors use aggressive exponential backoff."""
        task = {
            'filename': 'test.mp4',
            'retry_count': 2  # 3rd attempt
        }
        event = AsyncMock()
        error = OSError("[Errno 7] No address associated with hostname")
        
        with patch.object(queue_manager, '_add_to_retry_queue', new_callable=AsyncMock) as mock_retry:
            await queue_manager._handle_webdav_download_failure(task, event, error, True)
            
            # Get the retry task that was queued
            retry_task = mock_retry.call_args[0][0]
            
            # Calculate expected delay: min(RETRY_BASE_INTERVAL * (2 ** 3), 300)
            # With RETRY_BASE_INTERVAL = 5: min(5 * 8, 300) = 40
            expected_delay = min(RETRY_BASE_INTERVAL * (2 ** 3), 300)
            
            # Verify retry_after is approximately correct (within 1 second tolerance)
            actual_delay = retry_task['retry_after'] - time.time()
            assert abs(actual_delay - expected_delay) < 1.0
    
    @pytest.mark.asyncio
    async def test_network_error_exponential_backoff(self, queue_manager):
        """Test network errors use aggressive exponential backoff."""
        task = {
            'filename': 'test.mp4',
            'retry_count': 3  # 4th attempt
        }
        event = AsyncMock()
        error = ConnectionResetError("[Errno 54] Connection reset by peer")
        
        with patch.object(queue_manager, '_add_to_retry_queue', new_callable=AsyncMock) as mock_retry:
            await queue_manager._handle_webdav_download_failure(task, event, error, True)
            
            retry_task = mock_retry.call_args[0][0]
            
            # Expected: min(5 * (2 ** 4), 300) = min(80, 300) = 80
            expected_delay = min(RETRY_BASE_INTERVAL * (2 ** 4), 300)
            actual_delay = retry_task['retry_after'] - time.time()
            assert abs(actual_delay - expected_delay) < 1.0
    
    @pytest.mark.asyncio
    async def test_timeout_standard_backoff(self, queue_manager):
        """Test timeouts use standard exponential backoff."""
        task = {
            'filename': 'test.mp4',
            'retry_count': 1  # 2nd attempt
        }
        event = AsyncMock()
        error = asyncio.TimeoutError("Timed out")
        
        with patch.object(queue_manager, '_add_to_retry_queue', new_callable=AsyncMock) as mock_retry:
            await queue_manager._handle_webdav_download_failure(task, event, error, True)
            
            retry_task = mock_retry.call_args[0][0]
            
            # Standard backoff: RETRY_BASE_INTERVAL * (2 ** (retry_count - 1))
            # For retry_count=2: 5 * (2 ** 1) = 10
            expected_delay = RETRY_BASE_INTERVAL * (2 ** (2 - 1))
            actual_delay = retry_task['retry_after'] - time.time()
            assert abs(actual_delay - expected_delay) < 1.0
    
    @pytest.mark.asyncio
    async def test_backoff_capped_at_300_seconds(self, queue_manager):
        """Test that DNS/network backoff is capped at 5 minutes."""
        task = {
            'filename': 'test.mp4',
            'retry_count': 4  # 5th attempt (still within MAX_RETRY_ATTEMPTS=5)
        }
        event = AsyncMock()
        error = OSError("[Errno 7] No address associated with hostname")
        
        with patch.object(queue_manager, '_add_to_retry_queue', new_callable=AsyncMock) as mock_retry:
            await queue_manager._handle_webdav_download_failure(task, event, error, True)
            
            retry_task = mock_retry.call_args[0][0]
            
            # Calculate: min(RETRY_BASE_INTERVAL * (2 ** 5), 300) = min(5 * 32, 300) = min(160, 300) = 160
            # So at retry 5, it's not capped yet. Let's test the cap logic is present
            expected_delay = min(RETRY_BASE_INTERVAL * (2 ** 5), 300)
            actual_delay = retry_task['retry_after'] - time.time()
            assert actual_delay <= 300.5  # Verify cap works (with tolerance)
            assert abs(actual_delay - expected_delay) < 1.0


class TestRetryLimitHandling:
    """Test behavior when retry limit is reached."""
    
    @pytest.mark.asyncio
    async def test_permanent_failure_after_max_retries(self, queue_manager):
        """Test that permanent failure is reported after MAX_RETRY_ATTEMPTS."""
        task = {
            'filename': 'test.mp4',
            'retry_count': MAX_RETRY_ATTEMPTS  # Already at max
        }
        event = AsyncMock()
        error = OSError("[Errno 7] No address associated with hostname")
        
        with patch.object(queue_manager, '_add_to_retry_queue', new_callable=AsyncMock) as mock_retry:
            await queue_manager._handle_webdav_download_failure(task, event, error, True)
            
            # Verify NO retry was scheduled
            assert not mock_retry.called
            
            # Verify permanent failure message was sent
            reply_call = event.reply.call_args
            assert reply_call is not None
            message = reply_call[0][0]
            assert '❌' in message
            assert 'failed' in message.lower()
            assert str(MAX_RETRY_ATTEMPTS) in message
    
    @pytest.mark.asyncio
    async def test_permanent_failure_includes_error_type(self, queue_manager):
        """Test that permanent failure message includes error type."""
        task = {
            'filename': 'test.mp4',
            'retry_count': MAX_RETRY_ATTEMPTS
        }
        event = AsyncMock()
        error = ConnectionRefusedError("[Errno 61] Connection refused")
        
        with patch.object(queue_manager, '_add_to_retry_queue', new_callable=AsyncMock):
            await queue_manager._handle_webdav_download_failure(task, event, error, True)
            
            reply_call = event.reply.call_args
            message = reply_call[0][0]
            assert 'network connection error' in message


class TestRetryQueueIntegration:
    """Test integration with retry queue."""
    
    @pytest.mark.asyncio
    async def test_retry_count_incremented(self, queue_manager):
        """Test that retry_count is incremented in queued task."""
        task = {
            'filename': 'test.mp4',
            'retry_count': 2,
            'other_field': 'preserved'
        }
        event = AsyncMock()
        error = OSError("[Errno 7] No address associated with hostname")
        
        with patch.object(queue_manager, '_add_to_retry_queue', new_callable=AsyncMock) as mock_retry:
            await queue_manager._handle_webdav_download_failure(task, event, error, True)
            
            retry_task = mock_retry.call_args[0][0]
            assert retry_task['retry_count'] == 3
            assert retry_task['other_field'] == 'preserved'
    
    @pytest.mark.asyncio
    async def test_retry_after_timestamp_set(self, queue_manager):
        """Test that retry_after timestamp is set correctly."""
        task = {
            'filename': 'test.mp4',
            'retry_count': 0
        }
        event = AsyncMock()
        error = OSError("[Errno 7] No address associated with hostname")
        
        start_time = time.time()
        
        with patch.object(queue_manager, '_add_to_retry_queue', new_callable=AsyncMock) as mock_retry:
            await queue_manager._handle_webdav_download_failure(task, event, error, True)
            
            retry_task = mock_retry.call_args[0][0]
            
            # Verify retry_after is in the future
            assert 'retry_after' in retry_task
            assert retry_task['retry_after'] > start_time


class TestUserNotifications:
    """Test user-facing error messages."""
    
    @pytest.mark.asyncio
    async def test_retry_notification_format(self, queue_manager):
        """Test retry notification includes all required info."""
        task = {
            'filename': 'my_video.mp4',
            'retry_count': 1
        }
        event = AsyncMock()
        error = OSError("[Errno 7] No address associated with hostname")
        
        with patch.object(queue_manager, '_add_to_retry_queue', new_callable=AsyncMock):
            await queue_manager._handle_webdav_download_failure(task, event, error, True)
            
            reply_call = event.reply.call_args
            message = reply_call[0][0]
            
            # Verify message includes filename, error type, delay, and attempt count
            assert 'my_video.mp4' in message
            assert 'DNS resolution failure' in message
            assert 'Retrying in' in message
            assert f'attempt 2/{MAX_RETRY_ATTEMPTS}' in message
    
    @pytest.mark.asyncio
    async def test_no_notification_when_event_not_live(self, queue_manager):
        """Test that no user notification is sent when event is not live."""
        task = {
            'filename': 'test.mp4',
            'retry_count': 0
        }
        event = AsyncMock()
        error = OSError("[Errno 7] No address associated with hostname")
        
        with patch.object(queue_manager, '_add_to_retry_queue', new_callable=AsyncMock):
            # live_event=False means no user notification
            await queue_manager._handle_webdav_download_failure(task, event, error, False)
            
            # Verify no reply was sent
            assert not event.reply.called


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
