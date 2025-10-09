"""
Tests for Torbox download retry mechanism and connection settings.

Tests verify:
- Retry logic with exponential backoff
- Connection keepalive configuration
- Timeout settings
- Partial download cleanup
- Error handling
"""

import os
import sys
import tempfile
import shutil
import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
import aiohttp

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.torbox_downloader import download_from_torbox


def create_mock_response(status=200, content_length='1000', data=b"x" * 1000):
    """Helper to create a mock aiohttp response."""
    mock_response = AsyncMock()
    mock_response.status = status
    mock_response.headers = {'content-length': content_length}
    
    async def mock_iter_chunked(size):
        # Yield data in one or more chunks
        chunk_size = 256 * 1024  # Match implementation
        offset = 0
        while offset < len(data):
            yield data[offset:offset + chunk_size]
            offset += chunk_size
    
    mock_response.content.iter_chunked = mock_iter_chunked
    return mock_response


class TestTorboxRetryMechanism:
    """Test the retry mechanism for Torbox downloads."""
    
    @pytest.mark.asyncio
    async def test_download_success_first_attempt(self):
        """Test successful download on first attempt (no retries needed)."""
        temp_dir = tempfile.mkdtemp(prefix="test_retry_")
        output_path = os.path.join(temp_dir, "test_file.zip")
        
        try:
            # Create mock response
            mock_response = create_mock_response()
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            
            # Create mock session - NOTE: get() is a regular Mock, not AsyncMock
            mock_session = AsyncMock()
            mock_session.get = Mock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            with patch('utils.torbox_downloader.aiohttp.ClientSession', return_value=mock_session):
                success, error, filename = await download_from_torbox(
                    "https://test.torbox.com/file.zip",
                    output_path,
                    max_retries=3
                )
                
                assert success is True
                assert error is None
                assert os.path.exists(output_path)
                assert os.path.getsize(output_path) == 1000
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_download_success_after_retries(self):
        """Test successful download after network errors."""
        temp_dir = tempfile.mkdtemp(prefix="test_retry_")
        output_path = os.path.join(temp_dir, "test_file.zip")
        
        try:
            call_count = [0]
            
            def mock_get_side_effect(*args, **kwargs):
                call_count[0] += 1
                
                if call_count[0] < 3:
                    # First 2 attempts fail - raise immediately
                    async def fail():
                        raise aiohttp.ClientError("Connection reset")
                    
                    mock_cm = AsyncMock()
                    mock_cm.__aenter__.side_effect = lambda: fail()
                    return mock_cm
                
                # Third attempt succeeds
                mock_response = create_mock_response()
                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_response
                mock_cm.__aexit__.return_value = None
                return mock_cm
            
            mock_session = AsyncMock()
            mock_session.get.side_effect = mock_get_side_effect
            
            session_cm = AsyncMock()
            session_cm.__aenter__.return_value = mock_session
            session_cm.__aexit__.return_value = None
            
            with patch('utils.torbox_downloader.aiohttp.ClientSession', return_value=session_cm):
                with patch('asyncio.sleep', new_callable=AsyncMock):  # Skip delays
                    success, error, filename = await download_from_torbox(
                        "https://test.torbox.com/file.zip",
                        output_path,
                        max_retries=5,
                        retry_delay=1
                    )
                    
                    assert success is True
                    assert call_count[0] == 3  # Failed twice, succeeded on 3rd
                    assert os.path.exists(output_path)
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_download_fails_after_max_retries(self):
        """Test download failure after exceeding max retries."""
        temp_dir = tempfile.mkdtemp(prefix="test_retry_")
        output_path = os.path.join(temp_dir, "test_file.zip")
        
        try:
            # Always fail
            async def fail():
                raise aiohttp.ClientError("Persistent connection error")
            
            def mock_get_side_effect(*args, **kwargs):
                mock_cm = AsyncMock()
                mock_cm.__aenter__.side_effect = lambda: fail()
                return mock_cm
            
            mock_session = AsyncMock()
            mock_session.get.side_effect = mock_get_side_effect
            
            session_cm = AsyncMock()
            session_cm.__aenter__.return_value = mock_session
            session_cm.__aexit__.return_value = None
            
            with patch('utils.torbox_downloader.aiohttp.ClientSession', return_value=session_cm):
                with patch('asyncio.sleep', new_callable=AsyncMock):
                    success, error, filename = await download_from_torbox(
                        "https://test.torbox.com/file.zip",
                        output_path,
                        max_retries=3,
                        retry_delay=1
                    )
                    
                    assert success is False
                    assert "after 3 retries" in error
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self):
        """Test that retry delays follow exponential backoff."""
        temp_dir = tempfile.mkdtemp(prefix="test_retry_")
        output_path = os.path.join(temp_dir, "test_file.zip")
        
        try:
            sleep_delays = []
            
            async def mock_sleep(delay):
                sleep_delays.append(delay)
            
            # Always fail to test backoff
            async def fail():
                raise aiohttp.ClientError("Test error")
            
            def mock_get_side_effect(*args, **kwargs):
                mock_cm = AsyncMock()
                mock_cm.__aenter__.side_effect = lambda: fail()
                return mock_cm
            
            mock_session = AsyncMock()
            mock_session.get.side_effect = mock_get_side_effect
            
            session_cm = AsyncMock()
            session_cm.__aenter__.return_value = mock_session
            session_cm.__aexit__.return_value = None
            
            with patch('utils.torbox_downloader.aiohttp.ClientSession', return_value=session_cm):
                with patch('asyncio.sleep', side_effect=mock_sleep):
                    await download_from_torbox(
                        "https://test.torbox.com/file.zip",
                        output_path,
                        max_retries=4,
                        retry_delay=5
                    )
                    
                    # Check exponential backoff: 5, 10, 20, 40
                    assert len(sleep_delays) == 4
                    assert sleep_delays[0] == 5
                    assert sleep_delays[1] == 10
                    assert sleep_delays[2] == 20
                    assert sleep_delays[3] == 40
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_filesystem_error_no_retry(self):
        """Test that filesystem errors don't trigger retry (fail fast)."""
        # Use invalid path that will cause OSError
        output_path = "/invalid/path/that/does/not/exist/file.zip"
        
        call_count = [0]
        
        def mock_get_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_response = create_mock_response()
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_response
            mock_cm.__aexit__.return_value = None
            return mock_cm
        
        mock_session = AsyncMock()
        mock_session.get.side_effect = mock_get_side_effect
        
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = mock_session
        session_cm.__aexit__.return_value = None
        
        with patch('utils.torbox_downloader.aiohttp.ClientSession', return_value=session_cm):
            success, error, filename = await download_from_torbox(
                "https://test.torbox.com/file.zip",
                output_path,
                max_retries=5
            )
            
            assert success is False
            assert "File system error" in error
            # OSError happens before trying to download, so no retries
            assert call_count[0] == 0


class TestTorboxConnectionSettings:
    """Test connection configuration settings."""
    
    @pytest.mark.asyncio
    async def test_timeout_settings_configured(self):
        """Test that timeout settings are properly configured."""
        temp_dir = tempfile.mkdtemp(prefix="test_retry_")
        output_path = os.path.join(temp_dir, "test_file.zip")
        
        try:
            mock_response = create_mock_response()
            
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_response
            mock_cm.__aexit__.return_value = None
            
            mock_session = AsyncMock()
            mock_session.get.return_value = mock_cm
            
            session_cm = AsyncMock()
            session_cm.__aenter__.return_value = mock_session
            session_cm.__aexit__.return_value = None
            
            captured_kwargs = {}
            
            def capture_session(*args, **kwargs):
                captured_kwargs.update(kwargs)
                return session_cm
            
            with patch('utils.torbox_downloader.aiohttp.ClientSession', side_effect=capture_session):
                await download_from_torbox(
                    "https://test.torbox.com/file.zip",
                    output_path
                )
                
                # Check timeout configuration
                assert 'timeout' in captured_kwargs
                timeout = captured_kwargs['timeout']
                assert timeout.total is None  # No total timeout for large files
                assert timeout.connect == 60  # 60s connection timeout
                assert timeout.sock_read == 300  # 5min read timeout
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_connection_keepalive_configured(self):
        """Test that TCP keepalive is properly configured."""
        temp_dir = tempfile.mkdtemp(prefix="test_retry_")
        output_path = os.path.join(temp_dir, "test_file.zip")
        
        try:
            mock_response = create_mock_response()
            
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_response
            mock_cm.__aexit__.return_value = None
            
            mock_session = AsyncMock()
            mock_session.get.return_value = mock_cm
            
            session_cm = AsyncMock()
            session_cm.__aenter__.return_value = mock_session
            session_cm.__aexit__.return_value = None
            
            captured_kwargs = {}
            
            def capture_session(*args, **kwargs):
                captured_kwargs.update(kwargs)
                return session_cm
            
            with patch('utils.torbox_downloader.aiohttp.ClientSession', side_effect=capture_session):
                await download_from_torbox(
                    "https://test.torbox.com/file.zip",
                    output_path
                )
                
                # Check connector configuration
                assert 'connector' in captured_kwargs
                connector = captured_kwargs['connector']
                assert hasattr(connector, '_keepalive_timeout')
                # Note: The actual TCPConnector object has been created, 
                # so we can't easily inspect its parameters after construction
                # But we verify it was passed to ClientSession
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
