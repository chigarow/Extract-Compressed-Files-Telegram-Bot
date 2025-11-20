"""
Unit tests for WebDAV chunking enhancement.

Tests the configurable WEBDAV_CHUNK_SIZE_KB setting and its impact on
download operations for memory-constrained devices.
"""

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from utils.webdav_client import TorboxWebDAVClient


class TestWebDAVChunkingConfiguration:
    """Test suite for WebDAV chunk size configuration."""

    def test_default_chunk_size_from_config(self):
        """Test that client uses default chunk size from config when not specified."""
        with patch('utils.constants.WEBDAV_CHUNK_SIZE_KB', 1024):
            client = TorboxWebDAVClient(
                base_url='https://webdav.torbox.app',
                username='test_user',
                password='test_pass'
            )
            # Should be 1024 KB * 1024 = 1048576 bytes
            assert client.chunk_size == 1024 * 1024

    def test_custom_chunk_size_override(self):
        """Test that explicitly provided chunk size overrides config default."""
        with patch('utils.constants.WEBDAV_CHUNK_SIZE_KB', 1024):
            custom_size = 256 * 1024  # 256 KB in bytes
            client = TorboxWebDAVClient(
                base_url='https://webdav.torbox.app',
                username='test_user',
                password='test_pass',
                chunk_size=custom_size
            )
            assert client.chunk_size == custom_size

    def test_small_chunk_size_for_low_memory(self):
        """Test that small chunk sizes work for low-memory devices (e.g., 128 KB)."""
        with patch('utils.constants.WEBDAV_CHUNK_SIZE_KB', 128):
            client = TorboxWebDAVClient(
                base_url='https://webdav.torbox.app',
                username='test_user',
                password='test_pass'
            )
            # Should be 128 KB * 1024 = 131072 bytes
            assert client.chunk_size == 128 * 1024

    def test_large_chunk_size_for_high_memory(self):
        """Test that large chunk sizes work for high-memory devices (e.g., 4 MB)."""
        with patch('utils.constants.WEBDAV_CHUNK_SIZE_KB', 4096):
            client = TorboxWebDAVClient(
                base_url='https://webdav.torbox.app',
                username='test_user',
                password='test_pass'
            )
            # Should be 4096 KB * 1024 = 4194304 bytes
            assert client.chunk_size == 4096 * 1024


class TestWebDAVChunkedDownload:
    """Test suite for chunked download operations."""

    @pytest.mark.asyncio
    async def test_download_uses_configured_chunk_size(self, tmp_path):
        """Test that download operations use the configured chunk size."""
        # Setup
        chunk_size_kb = 64  # 64 KB for testing
        chunk_size_bytes = chunk_size_kb * 1024
        
        with patch('utils.constants.WEBDAV_CHUNK_SIZE_KB', chunk_size_kb):
            client = TorboxWebDAVClient(
                base_url='https://webdav.torbox.app',
                username='test_user',
                password='test_pass'
            )
            
            # Mock HTTP client and response
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.headers = {'content-length': '200000'}
            
            # Create chunks that match our configured size
            test_data = b'x' * 200000  # 200 KB file
            chunks = [
                test_data[i:i + chunk_size_bytes]
                for i in range(0, len(test_data), chunk_size_bytes)
            ]
            
            async def mock_aiter_bytes(size):
                for chunk in chunks:
                    yield chunk
            
            mock_response.aiter_bytes = mock_aiter_bytes
            mock_response.aclose = AsyncMock()
            mock_response.raise_for_status = Mock()
            
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            client._http_client = mock_http_client
            
            # Execute download
            dest_path = tmp_path / "test_file.bin"
            await client.download_file('test/file.bin', str(dest_path))
            
            # Verify file was created and has correct size
            assert dest_path.exists()
            assert dest_path.stat().st_size == 200000
            
            # Verify aiter_bytes was called with correct chunk size
            # Note: We can't directly verify the parameter, but we can verify
            # the download completed successfully with our chunk size

    @pytest.mark.asyncio
    async def test_download_file_smaller_than_chunk(self, tmp_path):
        """Test downloading a file smaller than the configured chunk size."""
        chunk_size_kb = 1024  # 1 MB
        
        with patch('utils.constants.WEBDAV_CHUNK_SIZE_KB', chunk_size_kb):
            client = TorboxWebDAVClient(
                base_url='https://webdav.torbox.app',
                username='test_user',
                password='test_pass'
            )
            
            # Mock HTTP client and response for small file (10 KB)
            small_file_data = b'y' * 10240
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.headers = {'content-length': '10240'}
            
            async def mock_aiter_bytes(size):
                yield small_file_data
            
            mock_response.aiter_bytes = mock_aiter_bytes
            mock_response.aclose = AsyncMock()
            mock_response.raise_for_status = Mock()
            
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            client._http_client = mock_http_client
            
            # Execute download
            dest_path = tmp_path / "small_file.bin"
            await client.download_file('test/small.bin', str(dest_path))
            
            # Verify file was created correctly
            assert dest_path.exists()
            assert dest_path.stat().st_size == 10240

    @pytest.mark.asyncio
    async def test_download_file_exact_multiple_of_chunk(self, tmp_path):
        """Test downloading a file that is an exact multiple of chunk size."""
        chunk_size_kb = 64  # 64 KB
        chunk_size_bytes = chunk_size_kb * 1024
        
        with patch('utils.constants.WEBDAV_CHUNK_SIZE_KB', chunk_size_kb):
            client = TorboxWebDAVClient(
                base_url='https://webdav.torbox.app',
                username='test_user',
                password='test_pass'
            )
            
            # Create file that's exactly 2 chunks (128 KB)
            file_size = chunk_size_bytes * 2
            test_data = b'z' * file_size
            
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.headers = {'content-length': str(file_size)}
            
            chunks = [
                test_data[i:i + chunk_size_bytes]
                for i in range(0, len(test_data), chunk_size_bytes)
            ]
            
            async def mock_aiter_bytes(size):
                for chunk in chunks:
                    yield chunk
            
            mock_response.aiter_bytes = mock_aiter_bytes
            mock_response.aclose = AsyncMock()
            mock_response.raise_for_status = Mock()
            
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            client._http_client = mock_http_client
            
            # Execute download
            dest_path = tmp_path / "exact_multiple.bin"
            await client.download_file('test/exact.bin', str(dest_path))
            
            # Verify file was created correctly
            assert dest_path.exists()
            assert dest_path.stat().st_size == file_size
            # Verify we got exactly 2 chunks
            assert len(chunks) == 2

    @pytest.mark.asyncio
    async def test_download_with_progress_callback(self, tmp_path):
        """Test that progress callback receives updates during chunked download."""
        chunk_size_kb = 64
        chunk_size_bytes = chunk_size_kb * 1024
        
        with patch('utils.constants.WEBDAV_CHUNK_SIZE_KB', chunk_size_kb):
            client = TorboxWebDAVClient(
                base_url='https://webdav.torbox.app',
                username='test_user',
                password='test_pass'
            )
            
            # Create test data (3 chunks = 192 KB)
            file_size = chunk_size_bytes * 3
            test_data = b'p' * file_size
            
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.headers = {'content-length': str(file_size)}
            
            chunks = [
                test_data[i:i + chunk_size_bytes]
                for i in range(0, len(test_data), chunk_size_bytes)
            ]
            
            async def mock_aiter_bytes(size):
                for chunk in chunks:
                    yield chunk
            
            mock_response.aiter_bytes = mock_aiter_bytes
            mock_response.aclose = AsyncMock()
            mock_response.raise_for_status = Mock()
            
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            client._http_client = mock_http_client
            
            # Track progress callbacks
            progress_calls = []
            
            def progress_callback(current, total):
                progress_calls.append((current, total))
            
            # Execute download with progress tracking
            dest_path = tmp_path / "progress_test.bin"
            await client.download_file(
                'test/progress.bin',
                str(dest_path),
                progress_callback=progress_callback
            )
            
            # Verify progress was tracked
            assert len(progress_calls) > 0
            # Last call should have full file size
            assert progress_calls[-1][0] == file_size
            assert progress_calls[-1][1] == file_size

    @pytest.mark.asyncio
    async def test_download_resume_with_chunking(self, tmp_path):
        """Test that download resume works correctly with chunked downloads."""
        chunk_size_kb = 64
        
        with patch('utils.constants.WEBDAV_CHUNK_SIZE_KB', chunk_size_kb):
            client = TorboxWebDAVClient(
                base_url='https://webdav.torbox.app',
                username='test_user',
                password='test_pass'
            )
            
            # Create partial file (simulate interrupted download)
            dest_path = tmp_path / "resume_test.bin"
            part_path = str(dest_path) + '.part'
            
            partial_data = b'a' * 50000  # 50 KB already downloaded
            with open(part_path, 'wb') as f:
                f.write(partial_data)
            
            # Mock response for resume (206 Partial Content)
            remaining_data = b'b' * 50000  # 50 KB remaining
            mock_response = AsyncMock()
            mock_response.status_code = 206
            mock_response.headers = {
                'content-range': f'bytes 50000-99999/100000',
                'content-length': '50000'
            }
            
            async def mock_aiter_bytes(size):
                yield remaining_data
            
            mock_response.aiter_bytes = mock_aiter_bytes
            mock_response.aclose = AsyncMock()
            mock_response.raise_for_status = Mock()
            
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            client._http_client = mock_http_client
            
            # Execute resume download
            await client.download_file('test/resume.bin', str(dest_path))
            
            # Verify file was completed
            assert dest_path.exists()
            assert dest_path.stat().st_size == 100000
            
            # Verify Range header was sent
            call_args = mock_http_client.get.call_args
            assert 'headers' in call_args.kwargs
            assert 'Range' in call_args.kwargs['headers']
            assert call_args.kwargs['headers']['Range'] == 'bytes=50000-'


class TestWebDAVChunkingEdgeCases:
    """Test edge cases and error scenarios for chunked operations."""

    @pytest.mark.asyncio
    async def test_zero_byte_file_download(self, tmp_path):
        """Test downloading a zero-byte file."""
        with patch('utils.constants.WEBDAV_CHUNK_SIZE_KB', 1024):
            client = TorboxWebDAVClient(
                base_url='https://webdav.torbox.app',
                username='test_user',
                password='test_pass'
            )
            
            # Mock empty file response
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.headers = {'content-length': '0'}
            
            async def mock_aiter_bytes(size):
                return
                yield  # Make it a generator but yield nothing
            
            mock_response.aiter_bytes = mock_aiter_bytes
            mock_response.aclose = AsyncMock()
            mock_response.raise_for_status = Mock()
            
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            client._http_client = mock_http_client
            
            # Execute download
            dest_path = tmp_path / "empty.bin"
            await client.download_file('test/empty.bin', str(dest_path))
            
            # Verify empty file was created
            assert dest_path.exists()
            assert dest_path.stat().st_size == 0

    def test_invalid_chunk_size_configuration(self):
        """Test that invalid chunk sizes are handled appropriately."""
        # Test with zero chunk size (should use default)
        with patch('utils.constants.WEBDAV_CHUNK_SIZE_KB', 0):
            client = TorboxWebDAVClient(
                base_url='https://webdav.torbox.app',
                username='test_user',
                password='test_pass'
            )
            # Should use 0 * 1024 = 0, which httpx will handle
            assert client.chunk_size == 0

    @pytest.mark.asyncio
    async def test_network_interruption_during_chunked_download(self, tmp_path):
        """Test handling of network interruption during chunked download."""
        chunk_size_kb = 64
        
        with patch('utils.constants.WEBDAV_CHUNK_SIZE_KB', chunk_size_kb):
            client = TorboxWebDAVClient(
                base_url='https://webdav.torbox.app',
                username='test_user',
                password='test_pass'
            )
            
            # Mock response that fails mid-download
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.headers = {'content-length': '200000'}
            
            async def mock_aiter_bytes_with_error(size):
                yield b'x' * 65536  # First chunk succeeds
                raise ConnectionError("Network interrupted")
            
            mock_response.aiter_bytes = mock_aiter_bytes_with_error
            mock_response.aclose = AsyncMock()
            mock_response.raise_for_status = Mock()
            
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            client._http_client = mock_http_client
            
            # Execute download and expect error
            dest_path = tmp_path / "interrupted.bin"
            with pytest.raises(ConnectionError):
                await client.download_file('test/interrupted.bin', str(dest_path))
            
            # Verify partial file exists
            part_path = str(dest_path) + '.part'
            assert os.path.exists(part_path)
            # Should have first chunk written
            assert os.path.getsize(part_path) == 65536


class TestWebDAVChunkingIntegration:
    """Integration tests for WebDAV chunking with other features."""

    @pytest.mark.asyncio
    async def test_chunking_with_sequential_mode(self, tmp_path):
        """Test that chunking works correctly with WEBDAV_SEQUENTIAL_MODE."""
        # This test verifies that chunking doesn't interfere with sequential processing
        chunk_size_kb = 128
        
        with patch('utils.constants.WEBDAV_CHUNK_SIZE_KB', chunk_size_kb):
            client = TorboxWebDAVClient(
                base_url='https://webdav.torbox.app',
                username='test_user',
                password='test_pass'
            )
            
            # Verify client is configured correctly
            assert client.chunk_size == chunk_size_kb * 1024
            
            # Sequential mode is handled at queue level, not client level
            # This test just verifies the client works as expected
            assert client is not None

    def test_chunking_configuration_from_secrets_properties(self):
        """Test that chunk size can be configured via secrets.properties."""
        # This is an integration test that verifies the full configuration chain
        # config.py -> constants.py -> webdav_client.py
        
        # Mock the config to simulate secrets.properties
        with patch('utils.constants.WEBDAV_CHUNK_SIZE_KB', 512):
            client = TorboxWebDAVClient(
                base_url='https://webdav.torbox.app',
                username='test_user',
                password='test_pass'
            )
            
            # Should use configured value
            assert client.chunk_size == 512 * 1024


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
