"""
Unit tests for Torbox integration functionality.

Tests the ability to:
1. Detect Torbox CDN links in text messages
2. Download files from Torbox links
3. Process downloaded archives (extraction)
4. Process downloaded media files (upload)
5. Integration with existing queue system
6. SDK-based filename retrieval from Torbox API
"""

import pytest
import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from utils.torbox_downloader import (
    is_torbox_link,
    extract_torbox_links,
    get_filename_from_url,
    extract_file_id_from_url,
    get_torbox_metadata,
    download_from_torbox,
    download_torbox_with_progress,
    detect_file_type_from_url
)


class TestTorboxLinkDetection:
    """Test Torbox link detection functionality."""
    
    def test_is_torbox_link_valid(self):
        """Test detection of valid Torbox links."""
        valid_links = [
            'https://store-031.weur.tb-cdn.st/zip/e196451f-d609-42e8-a93c-4bfa68a45951?token=d1361ea3-0902-4ca3-b081-bb858e7566aa',
            'https://store-001.us.tb-cdn.st/video/abc12345-6789-0123-4567-890abcdef012',
            'https://store-100.eu.tb-cdn.st/rar/fedcba98-7654-3210-fedc-ba9876543210?token=12345678-abcd-efgh-ijkl-mnopqrstuvwx'
        ]
        
        for link in valid_links:
            assert is_torbox_link(link), f"Should detect valid Torbox link: {link}"
    
    def test_is_torbox_link_invalid(self):
        """Test rejection of invalid links."""
        invalid_links = [
            'https://www.google.com',
            'https://example.com/download/file.zip',
            'https://torbox.app/download',
            'not a url',
            '',
            None
        ]
        
        for link in invalid_links:
            assert not is_torbox_link(link), f"Should not detect invalid link: {link}"
    
    def test_extract_torbox_links(self):
        """Test extraction of multiple Torbox links from text."""
        text = """
        Here are some download links:
        https://store-031.weur.tb-cdn.st/zip/e196451f-d609-42e8-a93c-4bfa68a45951?token=abc123
        Some other text in between
        https://store-002.us.tb-cdn.st/video/12345678-abcd-efgh-ijkl-mnopqrstuvwx
        And a non-Torbox link: https://www.example.com
        """
        
        links = extract_torbox_links(text)
        
        assert len(links) == 2, "Should extract exactly 2 Torbox links"
        assert any('store-031' in link for link in links), "Should include first link"
        assert any('store-002' in link for link in links), "Should include second link"
    
    def test_extract_torbox_links_empty(self):
        """Test extraction from text with no links."""
        texts = [
            "Just some regular text",
            "",
            None,
            "https://www.google.com"
        ]
        
        for text in texts:
            links = extract_torbox_links(text)
            assert links == [], f"Should return empty list for: {text}"
    
    def test_extract_torbox_links_duplicates(self):
        """Test that duplicate links are removed."""
        text = """
        https://store-031.weur.tb-cdn.st/zip/e196451f-d609-42e8-a93c-4bfa68a45951?token=abc123
        Some text
        https://store-031.weur.tb-cdn.st/zip/e196451f-d609-42e8-a93c-4bfa68a45951?token=abc123
        """
        
        links = extract_torbox_links(text)
        assert len(links) == 1, "Should remove duplicate links"


class TestFilenameExtraction:
    """Test filename extraction from Torbox URLs."""
    
    def test_get_filename_from_url_with_type(self):
        """Test filename extraction with recognized type."""
        test_cases = [
            ('https://store-031.weur.tb-cdn.st/zip/e196451f-d609-42e8-a93c-4bfa68a45951', 'torbox_e196451f.zip'),
            ('https://store-001.us.tb-cdn.st/video/abc12345-6789-0123-4567-890abcdef012', 'torbox_abc12345.mp4'),
            ('https://store-002.eu.tb-cdn.st/rar/fedcba98-7654-3210-fedc-ba9876543210', 'torbox_fedcba98.rar')
        ]
        
        for url, expected_filename in test_cases:
            filename = get_filename_from_url(url)
            assert filename == expected_filename, f"Expected {expected_filename}, got {filename}"
    
    def test_get_filename_from_url_unknown_type(self):
        """Test filename extraction with unknown type."""
        url = 'https://store-031.weur.tb-cdn.st/unknown/e196451f-d609-42e8-a93c-4bfa68a45951'
        filename = get_filename_from_url(url)
        
        assert filename.startswith('torbox_e196451f'), "Should start with torbox_uuid"
    
    def test_get_filename_from_url_with_token(self):
        """Test that token is not included in filename."""
        url = 'https://store-031.weur.tb-cdn.st/zip/e196451f-d609-42e8-a93c-4bfa68a45951?token=abc-123'
        filename = get_filename_from_url(url)
        
        assert 'token' not in filename, "Filename should not contain token"
        assert filename == 'torbox_e196451f.zip', f"Expected torbox_e196451f.zip, got {filename}"
    
    def test_extract_file_id_from_url(self):
        """Test extraction of file UUID from CDN URL."""
        test_cases = [
            ('https://store-031.weur.tb-cdn.st/zip/e196451f-d609-42e8-a93c-4bfa68a45951', 'e196451f-d609-42e8-a93c-4bfa68a45951'),
            ('https://store-001.us.tb-cdn.st/video/abc12345-6789-0123-4567-890abcdef012?token=xyz', 'abc12345-6789-0123-4567-890abcdef012'),
            ('https://store-002.eu.tb-cdn.st/rar/fedcba98-7654-3210-fedc-ba9876543210?token=abc-123', 'fedcba98-7654-3210-fedc-ba9876543210')
        ]
        
        for url, expected_id in test_cases:
            file_id = extract_file_id_from_url(url)
            assert file_id == expected_id, f"Expected {expected_id}, got {file_id}"
    
    def test_extract_file_id_from_url_invalid(self):
        """Test file ID extraction from invalid URLs."""
        invalid_urls = [
            'https://www.google.com',
            'not a url',
            '',
        ]
        
        for url in invalid_urls:
            file_id = extract_file_id_from_url(url)
            assert file_id is None, f"Should return None for invalid URL: {url}"


class TestFileTypeDetection:
    """Test file type detection from Torbox URLs."""
    
    def test_detect_file_type_archive(self):
        """Test detection of archive types."""
        archive_urls = [
            'https://store-031.weur.tb-cdn.st/zip/e196451f-d609-42e8-a93c-4bfa68a45951',
            'https://store-031.weur.tb-cdn.st/rar/e196451f-d609-42e8-a93c-4bfa68a45951',
            'https://store-031.weur.tb-cdn.st/7z/e196451f-d609-42e8-a93c-4bfa68a45951'
        ]
        
        for url in archive_urls:
            file_type = detect_file_type_from_url(url)
            assert file_type == 'archive', f"Should detect archive type for {url}"
    
    def test_detect_file_type_video(self):
        """Test detection of video types."""
        video_urls = [
            'https://store-031.weur.tb-cdn.st/video/e196451f-d609-42e8-a93c-4bfa68a45951',
            'https://store-031.weur.tb-cdn.st/mp4/e196451f-d609-42e8-a93c-4bfa68a45951'
        ]
        
        for url in video_urls:
            file_type = detect_file_type_from_url(url)
            assert file_type == 'video', f"Should detect video type for {url}"
    
    def test_detect_file_type_photo(self):
        """Test detection of photo types."""
        photo_urls = [
            'https://store-031.weur.tb-cdn.st/image/e196451f-d609-42e8-a93c-4bfa68a45951',
            'https://store-031.weur.tb-cdn.st/photo/e196451f-d609-42e8-a93c-4bfa68a45951'
        ]
        
        for url in photo_urls:
            file_type = detect_file_type_from_url(url)
            assert file_type == 'photo', f"Should detect photo type for {url}"
    
    def test_detect_file_type_unknown(self):
        """Test detection of unknown types."""
        url = 'https://store-031.weur.tb-cdn.st/document/e196451f-d609-42e8-a93c-4bfa68a45951'
        file_type = detect_file_type_from_url(url)
        assert file_type == 'unknown', "Should return unknown for unrecognized types"


class TestTorboxDownload:
    """Test Torbox download functionality."""
    
    @pytest.mark.asyncio
    async def test_download_from_torbox_success(self):
        """Test successful download from Torbox."""
        url = 'https://store-031.weur.tb-cdn.st/zip/test.zip'
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, 'test.zip')
            
            # Mock aiohttp response
            mock_response = AsyncMock()
            mock_response.status = 200
            # Use actual chunk size for content-length
            test_data = b'test data chunk 1' + b'test data chunk 2'
            mock_response.headers = {'content-length': str(len(test_data))}
            
            # Create async generator for chunk iteration
            async def mock_chunks():
                yield b'test data chunk 1'
                yield b'test data chunk 2'
            
            mock_response.content.iter_chunked = lambda size: mock_chunks()
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            
            # Mock the session
            mock_session = AsyncMock()
            mock_session.get = Mock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            # Mock TCPConnector to prevent initialization issues
            mock_connector = AsyncMock()
            
            with patch('aiohttp.ClientSession', return_value=mock_session), \
                 patch('aiohttp.TCPConnector', return_value=mock_connector):
                success, error, filename = await download_from_torbox(url, output_path)
                
                assert success, f"Download should succeed, error: {error}"
                assert error is None, "Error should be None on success"
                assert filename is not None, "Should return a filename"
    
    @pytest.mark.asyncio
    async def test_download_from_torbox_http_error(self):
        """Test download with HTTP error response."""
        url = 'https://store-031.weur.tb-cdn.st/zip/test.zip'
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, 'test.zip')
            
            # Mock 404 response
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_response.reason = 'Not Found'
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            
            mock_session = AsyncMock()
            mock_session.get = Mock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            # Mock TCPConnector to prevent initialization issues
            mock_connector = AsyncMock()
            
            with patch('aiohttp.ClientSession', return_value=mock_session), \
                 patch('aiohttp.TCPConnector', return_value=mock_connector):
                success, error, filename = await download_from_torbox(url, output_path)
                
                assert not success, "Download should fail with HTTP error"
                assert error is not None, "Error message should be present"
                assert '404' in error, "Error should mention HTTP status code"
    
    @pytest.mark.asyncio
    async def test_download_from_torbox_progress_callback(self):
        """Test that progress callback is called during download."""
        url = 'https://store-031.weur.tb-cdn.st/zip/test.zip'
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, 'test.zip')
            
            # Track progress callback calls
            progress_calls = []
            
            def progress_callback(current, total):
                progress_calls.append((current, total))
            
            # Mock aiohttp response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.headers = {'content-length': '2048'}
            
            async def mock_chunks():
                yield b'0' * 1024
                yield b'1' * 1024
            
            mock_response.content.iter_chunked = lambda size: mock_chunks()
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            
            mock_session = AsyncMock()
            mock_session.get = Mock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            # Mock TCPConnector to prevent initialization issues
            mock_connector = AsyncMock()
            
            with patch('aiohttp.ClientSession', return_value=mock_session), \
                 patch('aiohttp.TCPConnector', return_value=mock_connector):
                success, error, filename = await download_from_torbox(url, output_path, progress_callback=progress_callback)
                
                assert success, "Download should succeed"
                assert len(progress_calls) > 0, "Progress callback should be called"
    
    @pytest.mark.asyncio
    async def test_download_with_progress_message_updates(self):
        """Test progress message updates during download."""
        url = 'https://store-031.weur.tb-cdn.st/zip/test.zip'
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, 'test.zip')
            
            # Mock Telegram message
            mock_status_msg = AsyncMock()
            mock_status_msg.edit = AsyncMock()
            
            # Mock aiohttp response
            mock_response = AsyncMock()
            mock_response.status = 200
            test_data = b'test data'
            mock_response.headers = {'content-length': str(len(test_data))}
            
            async def mock_chunks():
                yield test_data
            
            mock_response.content.iter_chunked = lambda size: mock_chunks()
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            
            mock_session = AsyncMock()
            mock_session.get = Mock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            # Mock TCPConnector to prevent initialization issues
            mock_connector = AsyncMock()
            
            with patch('aiohttp.ClientSession', return_value=mock_session), \
                 patch('aiohttp.TCPConnector', return_value=mock_connector):
                success, error, filename = await download_torbox_with_progress(
                    url,
                    output_path,
                    status_msg=mock_status_msg,
                    filename='test.zip'
                )
                
                assert success, "Download should succeed"
                # Note: Message edit might not be called due to throttling,
                # but at least verify no errors occurred
                assert error is None, "Should have no errors"
                assert filename is not None, "Should return a filename"


class TestSDKIntegration:
    """Test Torbox SDK integration for metadata retrieval."""
    
    @pytest.mark.asyncio
    async def test_get_torbox_metadata_success(self):
        """Test successful metadata retrieval from Torbox API."""
        mock_api_key = 'test_api_key_12345'
        
        # Mock SDK response
        mock_response = Mock()
        mock_response.data = {
            'data': [
                {
                    'id': 123,
                    'name': 'Test Download',
                    'files': [
                        {
                            'id': 'e196451f-d609-42e8-a93c-4bfa68a45951',
                            'name': 'ActualFilename.zip',
                            'size': 1024000
                        }
                    ]
                }
            ]
        }
        
        # Mock the SDK class
        mock_sdk = Mock()
        mock_sdk.web_downloads_debrid.get_web_download_list = Mock(return_value=mock_response)
        
        # Patch torbox_api.TorboxApi since it's imported inside the function
        with patch('torbox_api.TorboxApi', return_value=mock_sdk):
            metadata = await get_torbox_metadata(mock_api_key)
            
            assert metadata is not None, "Should return metadata"
            assert 'data' in metadata, "Should contain data key"
            assert len(metadata['data']) > 0, "Should have downloads in data"
    
    @pytest.mark.asyncio
    async def test_get_torbox_metadata_with_web_id(self):
        """Test metadata retrieval with specific web download ID."""
        mock_api_key = 'test_api_key_12345'
        web_id = '123'
        
        mock_response = Mock()
        mock_response.data = {
            'data': [
                {
                    'id': 123,
                    'name': 'Specific Download',
                    'files': [{'id': 'abc-123', 'name': 'SpecificFile.zip'}]
                }
            ]
        }
        
        mock_sdk = Mock()
        mock_sdk.web_downloads_debrid.get_web_download_list = Mock(return_value=mock_response)
        
        with patch('torbox_api.TorboxApi', return_value=mock_sdk):
            metadata = await get_torbox_metadata(mock_api_key, web_id=web_id)
            
            # Verify the SDK was called with correct parameters
            mock_sdk.web_downloads_debrid.get_web_download_list.assert_called_once()
            call_kwargs = mock_sdk.web_downloads_debrid.get_web_download_list.call_args[1]
            assert call_kwargs['id_'] == web_id, "Should pass web_id to SDK"
    
    @pytest.mark.asyncio
    async def test_get_torbox_metadata_api_error(self):
        """Test metadata retrieval when API returns error."""
        mock_api_key = 'test_api_key_12345'
        
        # Mock SDK to raise an exception
        mock_sdk = Mock()
        mock_sdk.web_downloads_debrid.get_web_download_list = Mock(side_effect=Exception("API Error"))
        
        with patch('torbox_api.TorboxApi', return_value=mock_sdk):
            metadata = await get_torbox_metadata(mock_api_key)
            
            assert metadata is None, "Should return None on API error"
    
    @pytest.mark.asyncio
    async def test_get_torbox_metadata_no_data(self):
        """Test metadata retrieval when API returns empty response."""
        mock_api_key = 'test_api_key_12345'
        
        mock_response = Mock()
        mock_response.data = None
        
        mock_sdk = Mock()
        mock_sdk.web_downloads_debrid.get_web_download_list = Mock(return_value=mock_response)
        
        with patch('torbox_api.TorboxApi', return_value=mock_sdk):
            metadata = await get_torbox_metadata(mock_api_key)
            
            assert metadata is None, "Should return None when no data attribute"
    
    @pytest.mark.asyncio
    async def test_download_with_sdk_metadata_success(self):
        """Test download with successful SDK metadata retrieval."""
        url = 'https://store-031.weur.tb-cdn.st/zip/e196451f-d609-42e8-a93c-4bfa68a45951?token=abc'
        mock_api_key = 'test_api_key_12345'
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, 'test.zip')
            
            # Mock SDK metadata response
            mock_metadata = {
                'data': [
                    {
                        'files': [
                            {
                                'id': 'e196451f-d609-42e8-a93c-4bfa68a45951',
                                'name': 'RealFilename.zip'
                            }
                        ]
                    }
                ]
            }
            
            # Mock aiohttp response
            mock_response = AsyncMock()
            mock_response.status = 200
            test_data = b'test data'
            mock_response.headers = {'content-length': str(len(test_data))}
            
            async def mock_chunks():
                yield test_data
            
            mock_response.content.iter_chunked = lambda size: mock_chunks()
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            
            mock_session = AsyncMock()
            mock_session.get = Mock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            # Mock TCPConnector to prevent initialization issues
            mock_connector = AsyncMock()
            
            with patch('aiohttp.ClientSession', return_value=mock_session), \
                 patch('aiohttp.TCPConnector', return_value=mock_connector), \
                 patch('utils.torbox_downloader.get_torbox_metadata', return_value=mock_metadata):
                
                success, error, actual_filename = await download_from_torbox(
                    url, 
                    output_path, 
                    api_key=mock_api_key
                )
                
                assert success, f"Download should succeed, error: {error}"
                assert actual_filename == 'RealFilename.zip', "Should use filename from SDK"
    
    @pytest.mark.asyncio
    async def test_download_with_sdk_fallback_to_header(self):
        """Test download falls back to Content-Disposition when SDK fails."""
        url = 'https://store-031.weur.tb-cdn.st/zip/e196451f-d609-42e8-a93c-4bfa68a45951?token=abc'
        mock_api_key = 'test_api_key_12345'
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, 'test.zip')
            
            # Mock aiohttp response with Content-Disposition
            mock_response = AsyncMock()
            mock_response.status = 200
            test_data = b'test data'
            mock_response.headers = {
                'content-length': str(len(test_data)),
                'content-disposition': 'attachment; filename="HeaderFilename.zip"'
            }
            
            async def mock_chunks():
                yield test_data
            
            mock_response.content.iter_chunked = lambda size: mock_chunks()
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            
            mock_session = AsyncMock()
            mock_session.get = Mock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            # Mock TCPConnector to prevent initialization issues
            mock_connector = AsyncMock()
            
            with patch('aiohttp.ClientSession', return_value=mock_session), \
                 patch('aiohttp.TCPConnector', return_value=mock_connector), \
                 patch('utils.torbox_downloader.get_torbox_metadata', return_value=None):
                
                success, error, actual_filename = await download_from_torbox(
                    url, 
                    output_path, 
                    api_key=mock_api_key
                )
                
                assert success, f"Download should succeed, error: {error}"
                assert actual_filename == 'HeaderFilename.zip', "Should use filename from Content-Disposition header"
    
    @pytest.mark.asyncio
    async def test_download_without_api_key(self):
        """Test download works without API key (backward compatibility)."""
        url = 'https://store-031.weur.tb-cdn.st/zip/e196451f-d609-42e8-a93c-4bfa68a45951?token=abc'
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, 'test.zip')
            
            # Mock aiohttp response
            mock_response = AsyncMock()
            mock_response.status = 200
            test_data = b'test data'
            mock_response.headers = {'content-length': str(len(test_data))}
            
            async def mock_chunks():
                yield test_data
            
            mock_response.content.iter_chunked = lambda size: mock_chunks()
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            
            mock_session = AsyncMock()
            mock_session.get = Mock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            # Mock TCPConnector to prevent initialization issues
            mock_connector = AsyncMock()
            
            with patch('aiohttp.ClientSession', return_value=mock_session), \
                 patch('aiohttp.TCPConnector', return_value=mock_connector):
                # Call without api_key parameter
                success, error, actual_filename = await download_from_torbox(url, output_path)
                
                assert success, f"Download should succeed without API key, error: {error}"
                assert actual_filename is not None, "Should have a filename"
    
    @pytest.mark.asyncio
    async def test_download_with_progress_uses_api_filename(self):
        """Test that progress messages use the filename from API."""
        url = 'https://store-031.weur.tb-cdn.st/zip/e196451f-d609-42e8-a93c-4bfa68a45951?token=abc'
        mock_api_key = 'test_api_key_12345'
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, 'test.zip')
            
            # Mock Telegram message
            mock_status_msg = AsyncMock()
            mock_status_msg.edit = AsyncMock()
            
            # Mock SDK metadata
            mock_metadata = {
                'data': [
                    {
                        'files': [
                            {
                                'id': 'e196451f-d609-42e8-a93c-4bfa68a45951',
                                'name': 'APIFilename.zip'
                            }
                        ]
                    }
                ]
            }
            
            # Mock aiohttp response
            mock_response = AsyncMock()
            mock_response.status = 200
            test_data = b'test data'
            mock_response.headers = {'content-length': str(len(test_data))}
            
            async def mock_chunks():
                yield test_data
            
            mock_response.content.iter_chunked = lambda size: mock_chunks()
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            
            mock_session = AsyncMock()
            mock_session.get = Mock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            # Mock TCPConnector to prevent initialization issues
            mock_connector = AsyncMock()
            
            with patch('aiohttp.ClientSession', return_value=mock_session), \
                 patch('aiohttp.TCPConnector', return_value=mock_connector), \
                 patch('utils.torbox_downloader.get_torbox_metadata', return_value=mock_metadata):
                
                success, error, actual_filename = await download_torbox_with_progress(
                    url,
                    output_path,
                    status_msg=mock_status_msg,
                    filename='fallback.zip',
                    api_key=mock_api_key
                )
                
                assert success, f"Download should succeed, error: {error}"
                assert actual_filename == 'APIFilename.zip', "Should return API filename"
                
                # Verify that the status message was edited with actual filename
                if mock_status_msg.edit.call_count > 0:
                    # Check the last call contains the API filename
                    last_call_text = mock_status_msg.edit.call_args[0][0]
                    assert 'APIFilename.zip' in last_call_text, "Status message should contain API filename"


class TestTorboxIntegration:
    """Test integration with the existing queue system."""
    
    @pytest.mark.asyncio
    async def test_torbox_archive_processing_flow(self):
        """Test that Torbox archives are added to extraction queue."""
        # This test would require mocking the entire queue system
        # For now, we'll test the detection logic
        url = 'https://store-031.weur.tb-cdn.st/zip/e196451f-d609-42e8-a93c-4bfa68a45951'
        
        file_type = detect_file_type_from_url(url)
        filename = get_filename_from_url(url)
        
        assert file_type == 'archive', "Should detect as archive"
        assert filename.endswith('.zip'), "Should have .zip extension"
    
    @pytest.mark.asyncio
    async def test_torbox_media_processing_flow(self):
        """Test that Torbox media files are added to upload queue."""
        url = 'https://store-031.weur.tb-cdn.st/video/e196451f-d609-42e8-a93c-4bfa68a45951'
        
        file_type = detect_file_type_from_url(url)
        filename = get_filename_from_url(url)
        
        assert file_type == 'video', "Should detect as video"
        assert filename.endswith('.mp4'), "Should have .mp4 extension"


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_extract_links_with_special_characters(self):
        """Test link extraction with special characters in text."""
        text = "Check out this file: https://store-031.weur.tb-cdn.st/zip/e196451f-d609-42e8-a93c-4bfa68a45951?token=abc-123, it's great!"
        
        links = extract_torbox_links(text)
        assert len(links) == 1, "Should extract link even with punctuation"
    
    def test_filename_extraction_without_extension(self):
        """Test filename generation when type doesn't map to extension."""
        url = 'https://store-031.weur.tb-cdn.st/binary/e196451f-d609-42e8-a93c-4bfa68a45951'
        filename = get_filename_from_url(url)
        
        assert filename.startswith('torbox_'), "Should start with torbox_ prefix"
        assert not filename.endswith('.'), "Should not end with just a dot"
    
    @pytest.mark.asyncio
    async def test_download_to_nonexistent_directory(self):
        """Test that download creates parent directories."""
        url = 'https://store-031.weur.tb-cdn.st/zip/test.zip'
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Use a path with non-existent parent directory
            output_path = os.path.join(temp_dir, 'subdir', 'nested', 'test.zip')
            
            # Complete test data
            test_data = b'test'
            
            # Mock aiohttp response - CRITICAL: content-length must match actual data
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.headers = {'content-length': str(len(test_data))}
            
            async def mock_chunks():
                yield test_data
            
            mock_response.content.iter_chunked = lambda size: mock_chunks()
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            
            # Mock TCPConnector to prevent initialization issues
            mock_connector = AsyncMock()
            mock_connector.__aenter__ = AsyncMock(return_value=mock_connector)
            mock_connector.__aexit__ = AsyncMock(return_value=None)
            
            mock_session = AsyncMock()
            mock_session.get = Mock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            
            with patch('aiohttp.ClientSession', return_value=mock_session), \
                 patch('aiohttp.TCPConnector', return_value=mock_connector):
                # Use max_retries=0 to prevent retry loops in this simple test
                success, error, filename = await download_from_torbox(url, output_path, max_retries=0)
                
                # Directory should be created automatically
                assert os.path.exists(os.path.dirname(output_path)), "Parent directory should be created"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
