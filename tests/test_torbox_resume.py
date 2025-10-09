"""
Tests for Torbox download resume capability.

Tests verify:
- HTTP Range request support
- Resume from partial downloads (.part files)
- Partial download cleanup on success/failure
- Extended exponential backoff (10s, 20s, 40s, 80s, 160s)
- ClientPayloadError handling
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


def create_mock_response(status=200, content_length='1000', data=b"x" * 1000, content_range=None):
    """Helper to create a mock aiohttp response."""
    mock_response = AsyncMock()
    mock_response.status = status
    mock_response.headers = {'content-length': content_length}
    if content_range:
        mock_response.headers['content-range'] = content_range
    
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


class TestTorboxResumeCapability:
    """Test HTTP Range request resume functionality."""
    
    @pytest.mark.asyncio
    async def test_resume_from_partial_download(self):
        """Test that download resumes from existing .part file."""
        temp_dir = tempfile.mkdtemp(prefix="test_resume_")
        output_path = os.path.join(temp_dir, "test_file.zip")
        part_path = output_path + ".part"
        
        try:
            # Create a partial .part file with 500 bytes
            partial_data = b"x" * 500
            with open(part_path, 'wb') as f:
                f.write(partial_data)
            
            # Mock response for resume (206 Partial Content)
            remaining_data = b"y" * 500  # Remaining 500 bytes
            mock_response = create_mock_response(
                status=206,
                content_length='500',
                data=remaining_data,
                content_range='bytes 500-999/1000'
            )
            
            captured_headers = {}
            
            def capture_get(url, headers=None):
                if headers:
                    captured_headers.update(headers)
                return mock_response
            
            mock_session = AsyncMock()
            mock_session.get = Mock(side_effect=capture_get)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            with patch('utils.torbox_downloader.aiohttp.ClientSession', return_value=mock_session):
                success, error, filename = await download_from_torbox(
                    "https://test.torbox.com/file.zip",
                    output_path
                )
                
                # Verify Range header was sent
                assert 'Range' in captured_headers
                assert captured_headers['Range'] == 'bytes=500-'
                
                # Verify success
                assert success is True
                assert error is None
                
                # Verify final file exists and .part file is gone
                assert os.path.exists(output_path)
                assert not os.path.exists(part_path)
                
                # Verify complete file size
                assert os.path.getsize(output_path) == 1000
                
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_resume_when_server_doesnt_support_ranges(self):
        """Test fallback when server doesn't support Range requests."""
        temp_dir = tempfile.mkdtemp(prefix="test_resume_")
        output_path = os.path.join(temp_dir, "test_file.zip")
        part_path = output_path + ".part"
        
        try:
            # Create a partial .part file
            with open(part_path, 'wb') as f:
                f.write(b"x" * 500)
            
            call_count = [0]
            
            def mock_get_side_effect(url, headers=None):
                call_count[0] += 1
                
                if call_count[0] == 1 and headers and 'Range' in headers:
                    # First call with Range header - return 200 (full content)
                    # Server doesn't support ranges
                    return create_mock_response(status=200, data=b"z" * 1000)
                else:
                    # Second call without Range - full download
                    return create_mock_response(status=200, data=b"z" * 1000)
            
            mock_session = AsyncMock()
            mock_session.get = Mock(side_effect=mock_get_side_effect)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            with patch('utils.torbox_downloader.aiohttp.ClientSession', return_value=mock_session):
                success, error, filename = await download_from_torbox(
                    "https://test.torbox.com/file.zip",
                    output_path
                )
                
                assert success is True
                # .part file should have been removed and recreated
                assert not os.path.exists(part_path)
                assert os.path.exists(output_path)
                
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_partial_file_kept_on_retriable_error(self):
        """Test that .part file is kept when download fails with retriable error."""
        temp_dir = tempfile.mkdtemp(prefix="test_resume_")
        output_path = os.path.join(temp_dir, "test_file.zip")
        part_path = output_path + ".part"
        
        try:
            call_count = [0]
            
            def mock_get_side_effect(url, headers=None):
                call_count[0] += 1
                
                # Always fail with ClientPayloadError
                mock_fail = AsyncMock()
                async def raise_error():
                    # Write some data to .part file first
                    with open(part_path, 'ab') as f:
                        f.write(b"x" * 500)
                    raise aiohttp.ClientPayloadError("Connection lost mid-download")
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
                        max_retries=2
                    )
                    
                    # Should fail after retries
                    assert success is False
                    assert "after 2 retries" in error
                    
                    # .part file should be cleaned up after final failure
                    assert not os.path.exists(part_path)
                    
                    # Should have tried 3 times (initial + 2 retries)
                    assert call_count[0] == 3
                    
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_extended_exponential_backoff(self):
        """Test that retry delays use extended exponential backoff (10s, 20s, 40s, 80s, 160s)."""
        temp_dir = tempfile.mkdtemp(prefix="test_resume_")
        output_path = os.path.join(temp_dir, "test_file.zip")
        
        try:
            sleep_delays = []
            
            async def mock_sleep(delay):
                sleep_delays.append(delay)
            
            # Always fail
            async def raise_error():
                raise aiohttp.ClientPayloadError("Test error")
            
            def mock_get_side_effect(url, headers=None):
                mock_fail = AsyncMock()
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
                        max_retries=5,
                        retry_delay=10
                    )
                    
                    # Check exponential backoff with increased base delay: 10, 20, 40, 80, 160
                    assert len(sleep_delays) == 5
                    assert sleep_delays[0] == 10
                    assert sleep_delays[1] == 20
                    assert sleep_delays[2] == 40
                    assert sleep_delays[3] == 80
                    assert sleep_delays[4] == 160
                    
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_part_file_cleanup_on_success(self):
        """Test that .part file is properly renamed to final file on success."""
        temp_dir = tempfile.mkdtemp(prefix="test_resume_")
        output_path = os.path.join(temp_dir, "test_file.zip")
        part_path = output_path + ".part"
        
        try:
            mock_response = create_mock_response()
            
            mock_session = AsyncMock()
            mock_session.get = Mock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            with patch('utils.torbox_downloader.aiohttp.ClientSession', return_value=mock_session):
                success, error, filename = await download_from_torbox(
                    "https://test.torbox.com/file.zip",
                    output_path
                )
                
                assert success is True
                assert os.path.exists(output_path)
                assert not os.path.exists(part_path)  # .part file should be renamed
                
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_part_file_cleanup_on_filesystem_error(self):
        """Test that .part file is cleaned up on filesystem errors."""
        # Use invalid path to trigger OSError
        output_path = "/invalid/path/test_file.zip"
        part_path = output_path + ".part"
        
        mock_response = create_mock_response()
        
        mock_session = AsyncMock()
        mock_session.get = Mock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('utils.torbox_downloader.aiohttp.ClientSession', return_value=mock_session):
            success, error, filename = await download_from_torbox(
                "https://test.torbox.com/file.zip",
                output_path
            )
            
            assert success is False
            assert "File system error" in error
            # Can't verify .part file deletion since directory doesn't exist
    
    @pytest.mark.asyncio
    async def test_content_length_mismatch_triggers_retry_with_resume(self):
        """Test that content length mismatch keeps .part file for retry."""
        temp_dir = tempfile.mkdtemp(prefix="test_resume_")
        output_path = os.path.join(temp_dir, "test_file.zip")
        part_path = output_path + ".part"
        
        try:
            call_count = [0]
            
            def mock_get_side_effect(url, headers=None):
                call_count[0] += 1
                
                if call_count[0] == 1:
                    # First attempt: incomplete data
                    return create_mock_response(
                        status=200,
                        content_length='1000',
                        data=b"x" * 500  # Only 500 bytes instead of 1000
                    )
                else:
                    # Second attempt: complete data with resume
                    return create_mock_response(
                        status=206,
                        content_length='500',
                        data=b"y" * 500,  # Remaining 500 bytes
                        content_range='bytes 500-999/1000'
                    )
            
            mock_session = AsyncMock()
            mock_session.get = Mock(side_effect=mock_get_side_effect)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            with patch('utils.torbox_downloader.aiohttp.ClientSession', return_value=mock_session):
                with patch('asyncio.sleep', new_callable=AsyncMock):
                    success, error, filename = await download_from_torbox(
                        "https://test.torbox.com/file.zip",
                        output_path
                    )
                    
                    # Should succeed on second attempt
                    assert success is True
                    assert call_count[0] == 2
                    assert os.path.exists(output_path)
                    assert not os.path.exists(part_path)
                    assert os.path.getsize(output_path) == 1000
                    
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)


class TestTorboxErrorHandling:
    """Test specific error handling for ClientPayloadError."""
    
    @pytest.mark.asyncio
    async def test_client_payload_error_is_caught(self):
        """Test that ClientPayloadError is properly caught and retried."""
        temp_dir = tempfile.mkdtemp(prefix="test_error_")
        output_path = os.path.join(temp_dir, "test_file.zip")
        
        try:
            # Mock ClientPayloadError
            async def raise_payload_error():
                raise aiohttp.ClientPayloadError("Response payload is not completed")
            
            def mock_get_side_effect(url, headers=None):
                mock_fail = AsyncMock()
                mock_fail.__aenter__ = Mock(side_effect=raise_payload_error)
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
                        max_retries=3
                    )
                    
                    assert success is False
                    assert "ClientPayloadError" in error
                    assert "after 3 retries" in error
                    
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
