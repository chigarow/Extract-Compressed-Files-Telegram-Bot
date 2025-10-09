"""
Comprehensive unit tests for Torbox SDK integration.

Tests the enhanced functionality including:
1. SDK-based filename retrieval from Torbox API
2. Fallback mechanisms when SDK is unavailable
3. Integration with existing download functions
4. Error handling and edge cases
"""

import pytest
import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from utils.torbox_downloader import (
    extract_file_id_from_url,
    get_torbox_metadata,
    download_from_torbox,
    download_torbox_with_progress
)


class TestFileIDExtraction:
    """Test file UUID extraction from CDN URLs."""
    
    def test_extract_file_id_success(self):
        """Test successful file ID extraction."""
        test_cases = [
            ('https://store-031.weur.tb-cdn.st/zip/e196451f-d609-42e8-a93c-4bfa68a45951', 
             'e196451f-d609-42e8-a93c-4bfa68a45951'),
            ('https://store-001.us.tb-cdn.st/video/abc12345-6789-0123-4567-890abcdef012?token=xyz', 
             'abc12345-6789-0123-4567-890abcdef012'),
            ('https://store-002.eu.tb-cdn.st/rar/fedcba98-7654-3210-fedc-ba9876543210?token=abc-123', 
             'fedcba98-7654-3210-fedc-ba9876543210')
        ]
        
        for url, expected_id in test_cases:
            file_id = extract_file_id_from_url(url)
            assert file_id == expected_id, f"Expected {expected_id}, got {file_id}"
    
    def test_extract_file_id_invalid_urls(self):
        """Test file ID extraction from invalid URLs."""
        invalid_urls = [
            'https://www.google.com',
            'not a url',
            '',
        ]
        
        for url in invalid_urls:
            file_id = extract_file_id_from_url(url)
            assert file_id is None, f"Should return None for invalid URL: {url}"


class TestSDKMetadataRetrieval:
    """Test Torbox SDK metadata retrieval."""
    
    @pytest.mark.asyncio
    async def test_get_metadata_success(self):
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
        
        with patch('torbox_api.TorboxApi', return_value=mock_sdk):
            metadata = await get_torbox_metadata(mock_api_key)
            
            assert metadata is not None, "Should return metadata"
            assert 'data' in metadata, "Should contain data key"
            assert len(metadata['data']) > 0, "Should have downloads in data"
    
    @pytest.mark.asyncio
    async def test_get_metadata_with_web_id(self):
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
    async def test_get_metadata_api_error(self):
        """Test metadata retrieval when API returns error."""
        mock_api_key = 'test_api_key_12345'
        
        # Mock SDK to raise an exception
        mock_sdk = Mock()
        mock_sdk.web_downloads_debrid.get_web_download_list = Mock(side_effect=Exception("API Error"))
        
        with patch('torbox_api.TorboxApi', return_value=mock_sdk):
            metadata = await get_torbox_metadata(mock_api_key)
            
            assert metadata is None, "Should return None on API error"
    
    @pytest.mark.asyncio
    async def test_get_metadata_empty_response(self):
        """Test metadata retrieval when API returns empty response."""
        mock_api_key = 'test_api_key_12345'
        
        mock_response = Mock()
        mock_response.data = None
        
        mock_sdk = Mock()
        mock_sdk.web_downloads_debrid.get_web_download_list = Mock(return_value=mock_response)
        
        with patch('torbox_api.TorboxApi', return_value=mock_sdk):
            metadata = await get_torbox_metadata(mock_api_key)
            
            assert metadata is None, "Should return None when no data attribute"


class TestSDKDownloadIntegration:
    """Test download integration with SDK metadata."""
    
    @pytest.mark.asyncio
    async def test_download_with_sdk_filename(self):
        """Test download uses filename from SDK metadata."""
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
            
            with patch('aiohttp.ClientSession', return_value=mock_session), \
                 patch('utils.torbox_downloader.get_torbox_metadata', return_value=mock_metadata):
                
                success, error, actual_filename = await download_from_torbox(
                    url, 
                    output_path, 
                    api_key=mock_api_key
                )
                
                assert success, f"Download should succeed, error: {error}"
                assert actual_filename == 'RealFilename.zip', f"Should use SDK filename, got: {actual_filename}"
    
    @pytest.mark.asyncio
    async def test_download_fallback_to_content_disposition(self):
        """Test download falls back to Content-Disposition header when SDK fails."""
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
            
            with patch('aiohttp.ClientSession', return_value=mock_session), \
                 patch('utils.torbox_downloader.get_torbox_metadata', return_value=None):
                
                success, error, actual_filename = await download_from_torbox(
                    url, 
                    output_path, 
                    api_key=mock_api_key
                )
                
                assert success, f"Download should succeed, error: {error}"
                assert actual_filename == 'HeaderFilename.zip', f"Should use header filename, got: {actual_filename}"
    
    @pytest.mark.asyncio
    async def test_download_without_api_key(self):
        """Test backward compatibility - download works without API key."""
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
            
            with patch('aiohttp.ClientSession', return_value=mock_session):
                # Call without api_key parameter
                success, error, actual_filename = await download_from_torbox(url, output_path)
                
                assert success, f"Download should succeed without API key, error: {error}"
                assert actual_filename is not None, "Should have a filename"
                assert isinstance(actual_filename, str), "Filename should be a string"
    
    @pytest.mark.asyncio
    async def test_download_with_progress_sdk_filename(self):
        """Test progress messages use filename from SDK."""
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
            
            with patch('aiohttp.ClientSession', return_value=mock_session), \
                 patch('utils.torbox_downloader.get_torbox_metadata', return_value=mock_metadata):
                
                success, error, actual_filename = await download_torbox_with_progress(
                    url,
                    output_path,
                    status_msg=mock_status_msg,
                    filename='fallback.zip',
                    api_key=mock_api_key
                )
                
                assert success, f"Download should succeed, error: {error}"
                assert actual_filename == 'APIFilename.zip', f"Should return API filename, got: {actual_filename}"
                
                # Verify that the status message was edited
                if mock_status_msg.edit.call_count > 0:
                    # Check the last call contains the API filename
                    last_call_text = mock_status_msg.edit.call_args[0][0]
                    assert 'APIFilename.zip' in last_call_text, "Status message should contain API filename"


class TestEdgeCases:
    """Test edge cases and error scenarios."""
    
    @pytest.mark.asyncio
    async def test_metadata_with_multiple_downloads(self):
        """Test metadata retrieval when API returns multiple downloads."""
        mock_api_key = 'test_api_key_12345'
        
        mock_response = Mock()
        mock_response.data = {
            'data': [
                {
                    'id': 123,
                    'files': [{'id': 'file-1', 'name': 'File1.zip'}]
                },
                {
                    'id': 456,
                    'files': [{'id': 'file-2', 'name': 'File2.zip'}]
                }
            ]
        }
        
        mock_sdk = Mock()
        mock_sdk.web_downloads_debrid.get_web_download_list = Mock(return_value=mock_response)
        
        with patch('torbox_api.TorboxApi', return_value=mock_sdk):
            metadata = await get_torbox_metadata(mock_api_key)
            
            assert len(metadata['data']) == 2, "Should return all downloads"
    
    @pytest.mark.asyncio
    async def test_download_filename_matching(self):
        """Test that filename matching works with partial ID matches."""
        url = 'https://store-031.weur.tb-cdn.st/zip/abc-123-def?token=xyz'
        mock_api_key = 'test_key'
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, 'test.zip')
            
            # Mock metadata with file that contains the ID
            mock_metadata = {
                'data': [
                    {
                        'files': [
                            {
                                'id': 'abc-123-def',
                                'name': 'MatchedFile.zip'
                            }
                        ]
                    }
                ]
            }
            
            mock_response = AsyncMock()
            mock_response.status = 200
            test_data = b'test'
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
            
            with patch('aiohttp.ClientSession', return_value=mock_session), \
                 patch('utils.torbox_downloader.get_torbox_metadata', return_value=mock_metadata):
                
                success, error, actual_filename = await download_from_torbox(
                    url, 
                    output_path, 
                    api_key=mock_api_key
                )
                
                assert success, f"Download should succeed"
                assert actual_filename == 'MatchedFile.zip', "Should match file by ID"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
