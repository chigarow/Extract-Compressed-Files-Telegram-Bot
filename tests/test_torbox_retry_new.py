"""
Tests for Torbox download retry mechanism and connection settings.
"""

import os
import sys
import tempfile
import shutil
import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
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
        # Yield data in chunks
        chunk_size = 256 * 1024
        offset = 0
        while offset < len(data):
            yield data[offset:offset + chunk_size]
            offset += chunk_size
    
    mock_response.content.iter_chunked = mock_iter_chunked
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    return mock_response


class TestTorboxRetryMechanism:
    """Test the retry mechanism for Torbox downloads."""
    
    @pytest.mark.asyncio
    async def test_download_success_first_attempt(self):
        """Test successful download on first attempt (no retries needed)."""
        temp_dir = tempfile.mkdtemp(prefix="test_retry_")
        output_path = os.path.join(temp_dir, "test_file.zip")
        
        try:
            mock_response = create_mock_response()
            
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
                    # First 2 attempts fail
                    mock_fail = AsyncMock()
                    async def raise_error():
                        raise aiohttp.ClientError("Connection reset")
                    mock_fail.__aenter__ = Mock(side_effect=raise_error)
                    return mock_fail
                
                # Third attempt succeeds
                return create_mock_response()
            
            mock_session = AsyncMock()
            mock_session.get = Mock(side_effect=mock_get_side_effect)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            with patch('utils.torbox_downloader.aiohttp.ClientSession', return_value=mock_session):
                with patch('asyncio.sleep', new_callable=AsyncMock):
                    success, error, filename = await download_from_torbox(
                        "https://test.torbox.com/file.zip",
                        output_path,
                        max_retries=5,
                        retry_delay=1
                    )
                    
                    assert success is True
                    assert call_count[0] == 3
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
            def mock_get_side_effect(*args, **kwargs):
                mock_fail = AsyncMock()
                async def raise_error():
                    raise aiohttp.ClientError("Persistent connection error")
                mock_fail.__aenter__ = Mock(side_effect=raise_error)
                return mock_fail
            
            mock_session = AsyncMock()
            mock_session.get = Mock(side_effect=mock_get_side_effect)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            with patch('utils.torbox_downloader.aiohttp.ClientSession', return_value=mock_session):
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
            
            def mock_get_side_effect(*args, **kwargs):
                mock_fail = AsyncMock()
                async def raise_error():
                    raise aiohttp.ClientError("Test error")
                mock_fail.__aenter__ = Mock(side_effect=raise_error)
                return mock_fail
            
            mock_session = AsyncMock()
            mock_session.get = Mock(side_effect=mock_get_side_effect)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            with patch('utils.torbox_downloader.aiohttp.ClientSession', return_value=mock_session):
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
        output_path = "/invalid/path/that/does/not/exist/file.zip"
        
        call_count = [0]
        
        def mock_get_side_effect(*args, **kwargs):
            call_count[0] += 1
            return create_mock_response()
        
        mock_session = AsyncMock()
        mock_session.get = Mock(side_effect=mock_get_side_effect)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('utils.torbox_downloader.aiohttp.ClientSession', return_value=mock_session):
            success, error, filename = await download_from_torbox(
                "https://test.torbox.com/file.zip",
                output_path,
                max_retries=5
            )
            
            assert success is False
            assert "File system error" in error
            assert call_count[0] == 0  # OSError happens before download


class TestTorboxConnectionSettings:
    """Test connection configuration settings."""
    
    @pytest.mark.asyncio
    async def test_timeout_settings_configured(self):
        """Test that timeout settings are properly configured."""
        temp_dir = tempfile.mkdtemp(prefix="test_retry_")
        output_path = os.path.join(temp_dir, "test_file.zip")
        
        try:
            mock_response = create_mock_response()
            
            mock_session = AsyncMock()
            mock_session.get = Mock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            captured_kwargs = {}
            
            def capture_session(*args, **kwargs):
                captured_kwargs.update(kwargs)
                return mock_session
            
            with patch('utils.torbox_downloader.aiohttp.ClientSession', side_effect=capture_session):
                await download_from_torbox(
                    "https://test.torbox.com/file.zip",
                    output_path
                )
                
                assert 'timeout' in captured_kwargs
                timeout = captured_kwargs['timeout']
                assert timeout.total is None
                assert timeout.connect == 60
                assert timeout.sock_read == 300
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
            
            mock_session = AsyncMock()
            mock_session.get = Mock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            captured_kwargs = {}
            
            def capture_session(*args, **kwargs):
                captured_kwargs.update(kwargs)
                return mock_session
            
            with patch('utils.torbox_downloader.aiohttp.ClientSession', side_effect=capture_session):
                await download_from_torbox(
                    "https://test.torbox.com/file.zip",
                    output_path
                )
                
                assert 'connector' in captured_kwargs
                connector = captured_kwargs['connector']
                assert hasattr(connector, '_keepalive_timeout')
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
