"""
Tests for utils.telegram_operations module

Tests Telegram client operations, file uploads/downloads, and message handling.
"""

import asyncio
import os
import tempfile
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.telegram_operations import TelegramOperations
from utils.constants import *

class TestTelegramOperations:
    """Test suite for TelegramOperations class"""
    
    @pytest.fixture
    def telegram_ops(self, mock_client):
        """Create TelegramOperations instance for testing"""
        return TelegramOperations(mock_client)
    
    @pytest.mark.asyncio
    async def test_initialization(self, telegram_ops, mock_client):
        """Test TelegramOperations initialization"""
        assert telegram_ops.client == mock_client
        assert telegram_ops.progress_tracker is not None
    
    @pytest.mark.asyncio
    async def test_download_file_standard(self, telegram_ops, mock_document, file_manager):
        """Test standard file download"""
        output_path = file_manager.create_test_file("output.pdf", b"")
        
        # Mock the client download_media method
        async def mock_download_media(document, file, progress_callback=None):
            # Simulate progress callbacks
            if progress_callback:
                progress_callback(512, 1024)  # 50%
                progress_callback(1024, 1024)  # 100%
            
            # Write test content to file
            with open(file, 'wb') as f:
                f.write(b"Mock downloaded content")
            return file
        
        telegram_ops.client.download_media = mock_download_media
        
        # Test download
        result_path = await telegram_ops.download_file(
            mock_document, 
            output_path,
            use_fast_download=False
        )
        
        assert result_path == output_path
        assert os.path.exists(output_path)
        
        # Verify content
        with open(output_path, 'rb') as f:
            content = f.read()
            assert content == b"Mock downloaded content"
    
    @pytest.mark.asyncio
    async def test_download_file_with_fast_download(self, telegram_ops, mock_document, file_manager):
        """Test fast download with fallback"""
        output_path = file_manager.create_test_file("output.pdf", b"")
        
        # Mock fast download to fail, then standard download succeeds
        with patch('utils.telegram_operations.fast_download_to_file') as mock_fast_download:
            mock_fast_download.side_effect = Exception("Fast download failed")
            
            # Mock standard download
            async def mock_download_media(document, file, progress_callback=None):
                with open(file, 'wb') as f:
                    f.write(b"Standard download content")
                return file
            
            telegram_ops.client.download_media = mock_download_media
            
            # Test download with fast download enabled
            result_path = await telegram_ops.download_file(
                mock_document,
                output_path,
                use_fast_download=True
            )
            
            assert result_path == output_path
            
            # Verify fallback was used
            with open(output_path, 'rb') as f:
                content = f.read()
                assert content == b"Standard download content"
    
    @pytest.mark.asyncio
    async def test_upload_file(self, telegram_ops, file_manager):
        """Test file upload functionality"""
        # Create test file
        test_file = file_manager.create_test_file("upload_test.txt", b"Test upload content")
        chat_id = 123456
        
        # Mock send_file method
        mock_message = Mock()
        mock_message.id = 98765
        telegram_ops.client.send_file = AsyncMock(return_value=mock_message)
        
        # Test upload
        message = await telegram_ops.upload_file(
            test_file,
            chat_id,
            caption="Test caption",
            progress_callback=Mock()
        )
        
        assert message.id == 98765
        
        # Verify send_file was called with correct parameters
        telegram_ops.client.send_file.assert_called_once()
        call_args = telegram_ops.client.send_file.call_args
        assert call_args[0][0] == chat_id  # entity
        assert call_args[0][1] == test_file  # file
        assert call_args[1]['caption'] == "Test caption"
    
    @pytest.mark.asyncio 
    async def test_upload_file_with_progress(self, telegram_ops, file_manager, mock_progress_callback):
        """Test file upload with progress tracking"""
        test_file = file_manager.create_test_file("upload_test.txt", b"Test upload content")
        chat_id = 123456
        
        # Mock send_file to call progress callback
        async def mock_send_file(entity, file, progress_callback=None, **kwargs):
            if progress_callback:
                progress_callback(256, 1024)  # 25%
                progress_callback(512, 1024)  # 50%
                progress_callback(1024, 1024)  # 100%
            
            mock_message = Mock()
            mock_message.id = 98765
            return mock_message
        
        telegram_ops.client.send_file = mock_send_file
        
        # Test upload with progress
        message = await telegram_ops.upload_file(
            test_file,
            chat_id,
            progress_callback=mock_progress_callback
        )
        
        # Verify progress was tracked
        progress_history = mock_progress_callback.get_progress_history()
        assert len(progress_history) >= 3
        assert progress_history[-1]['progress'] == 100.0
    
    @pytest.mark.asyncio
    async def test_send_message(self, telegram_ops):
        """Test sending text message"""
        chat_id = 123456
        message_text = "Test message"
        
        # Mock send_message method
        mock_message = Mock()
        mock_message.id = 11111
        telegram_ops.client.send_message = AsyncMock(return_value=mock_message)
        
        # Test send message
        message = await telegram_ops.send_message(chat_id, message_text)
        
        assert message.id == 11111
        
        # Verify send_message was called
        telegram_ops.client.send_message.assert_called_once_with(
            chat_id, message_text
        )
    
    @pytest.mark.asyncio
    async def test_send_message_with_reply(self, telegram_ops):
        """Test sending message with reply"""
        chat_id = 123456
        message_text = "Reply message"
        reply_to = 99999
        
        # Mock send_message method
        mock_message = Mock()
        mock_message.id = 22222
        telegram_ops.client.send_message = AsyncMock(return_value=mock_message)
        
        # Test send message with reply
        message = await telegram_ops.send_message(
            chat_id, 
            message_text, 
            reply_to_msg_id=reply_to
        )
        
        assert message.id == 22222
        
        # Verify send_message was called with reply_to
        telegram_ops.client.send_message.assert_called_once_with(
            chat_id, message_text, reply_to=reply_to
        )
    
    @pytest.mark.asyncio
    async def test_delete_message(self, telegram_ops):
        """Test message deletion"""
        chat_id = 123456
        message_id = 98765
        
        # Mock delete_messages method
        telegram_ops.client.delete_messages = AsyncMock(return_value=True)
        
        # Test delete message
        result = await telegram_ops.delete_message(chat_id, message_id)
        
        assert result is True
        
        # Verify delete_messages was called
        telegram_ops.client.delete_messages.assert_called_once_with(
            chat_id, message_id
        )
    
    @pytest.mark.asyncio
    async def test_edit_message(self, telegram_ops):
        """Test message editing"""
        chat_id = 123456
        message_id = 98765
        new_text = "Edited message"
        
        # Mock edit_message method
        mock_message = Mock()
        mock_message.id = message_id
        mock_message.message = new_text
        telegram_ops.client.edit_message = AsyncMock(return_value=mock_message)
        
        # Test edit message
        message = await telegram_ops.edit_message(chat_id, message_id, new_text)
        
        assert message.id == message_id
        assert message.message == new_text
        
        # Verify edit_message was called
        telegram_ops.client.edit_message.assert_called_once_with(
            chat_id, message_id, new_text
        )
    
    @pytest.mark.asyncio
    async def test_get_file_info(self, telegram_ops, mock_document):
        """Test getting file information from document"""
        file_info = await telegram_ops.get_file_info(mock_document)
        
        assert file_info['name'] == mock_document.file_name
        assert file_info['size'] == mock_document.size
        assert file_info['mime_type'] == mock_document.mime_type
        assert file_info['id'] == mock_document.id
    
    @pytest.mark.asyncio
    async def test_download_retry_mechanism(self, telegram_ops, mock_document, file_manager):
        """Test download retry on failure"""
        output_path = file_manager.create_test_file("output.pdf", b"")
        
        call_count = 0
        async def mock_failing_download(document, file, progress_callback=None):
            nonlocal call_count
            call_count += 1
            if call_count < 3:  # Fail first 2 attempts
                raise Exception("Connection error")
            
            # Success on 3rd attempt
            with open(file, 'wb') as f:
                f.write(b"Success after retry")
            return file
        
        telegram_ops.client.download_media = mock_failing_download
        
        # Test download with retries
        result_path = await telegram_ops.download_file(
            mock_document,
            output_path,
            use_fast_download=False,
            max_retries=3
        )
        
        assert result_path == output_path
        assert call_count == 3  # Should have retried 3 times
        
        # Verify successful content
        with open(output_path, 'rb') as f:
            content = f.read()
            assert content == b"Success after retry"
    
    @pytest.mark.asyncio
    async def test_upload_retry_mechanism(self, telegram_ops, file_manager):
        """Test upload retry on failure"""
        test_file = file_manager.create_test_file("upload_test.txt", b"Test content")
        chat_id = 123456
        
        call_count = 0
        async def mock_failing_upload(entity, file, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:  # Fail first 2 attempts
                raise Exception("Upload error")
            
            # Success on 3rd attempt
            mock_message = Mock()
            mock_message.id = 98765
            return mock_message
        
        telegram_ops.client.send_file = mock_failing_upload
        
        # Test upload with retries
        message = await telegram_ops.upload_file(
            test_file,
            chat_id,
            max_retries=3
        )
        
        assert message.id == 98765
        assert call_count == 3  # Should have retried 3 times
    
    @pytest.mark.asyncio
    async def test_progress_rate_limiting(self, telegram_ops, mock_document, file_manager):
        """Test progress callback rate limiting"""
        output_path = file_manager.create_test_file("output.pdf", b"")
        progress_calls = []
        
        def progress_callback(current, total):
            progress_calls.append((current, total))
        
        # Mock download with many progress updates
        async def mock_download_with_frequent_progress(document, file, progress_callback=None):
            if progress_callback:
                # Simulate many rapid progress updates
                for i in range(100):
                    progress_callback(i * 10, 1000)
                    await asyncio.sleep(0.001)  # Very frequent updates
            
            with open(file, 'wb') as f:
                f.write(b"Downloaded content")
            return file
        
        telegram_ops.client.download_media = mock_download_with_frequent_progress
        
        # Test download with rate-limited progress
        await telegram_ops.download_file(
            mock_document,
            output_path,
            progress_callback=progress_callback,
            use_fast_download=False
        )
        
        # Should have fewer progress calls than the 100 updates due to rate limiting
        assert len(progress_calls) < 100
        assert len(progress_calls) > 0  # But not zero
    
    @pytest.mark.asyncio
    async def test_connection_handling(self, telegram_ops):
        """Test connection management"""
        # Mock client connection methods
        telegram_ops.client.connect = AsyncMock()
        telegram_ops.client.disconnect = AsyncMock()
        telegram_ops.client.is_connected = Mock(return_value=False)
        
        # Test ensuring connection
        await telegram_ops.ensure_connected()
        
        # Should have called connect since is_connected returned False
        telegram_ops.client.connect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_file_validation(self, telegram_ops, file_manager):
        """Test file validation before upload"""
        # Create files for testing
        valid_file = file_manager.create_test_file("valid.txt", b"Valid content")
        empty_file = file_manager.create_test_file("empty.txt", b"")
        
        chat_id = 123456
        
        # Mock send_file
        telegram_ops.client.send_file = AsyncMock(return_value=Mock(id=1))
        
        # Test valid file upload
        message = await telegram_ops.upload_file(valid_file, chat_id)
        assert message is not None
        
        # Test empty file (should handle gracefully)
        with pytest.raises(Exception):
            await telegram_ops.upload_file("/nonexistent/file.txt", chat_id)

class TestTelegramOperationsIntegration:
    """Integration tests for TelegramOperations"""
    
    @pytest.mark.asyncio
    async def test_full_download_upload_cycle(self, mock_client, file_manager, mock_document):
        """Test complete download -> process -> upload workflow"""
        telegram_ops = TelegramOperations(mock_client)
        
        # Setup paths
        download_path = file_manager.create_test_file("downloaded.pdf", b"")
        upload_path = file_manager.create_test_file("processed.txt", b"Processed content")
        
        # Mock download
        async def mock_download(document, file, progress_callback=None):
            with open(file, 'wb') as f:
                f.write(b"Original downloaded content")
            return file
        
        # Mock upload
        async def mock_upload(entity, file, **kwargs):
            mock_message = Mock()
            mock_message.id = 12345
            return mock_message
        
        telegram_ops.client.download_media = mock_download
        telegram_ops.client.send_file = mock_upload
        
        # Execute download
        downloaded_file = await telegram_ops.download_file(
            mock_document,
            download_path,
            use_fast_download=False
        )
        
        # Verify download
        assert os.path.exists(downloaded_file)
        
        # Execute upload
        uploaded_message = await telegram_ops.upload_file(
            upload_path,
            123456,
            caption="Processed file"
        )
        
        # Verify upload
        assert uploaded_message.id == 12345
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, mock_client, file_manager, mock_document):
        """Test concurrent download/upload operations"""
        telegram_ops = TelegramOperations(mock_client)
        
        # Create multiple test files
        files = [
            file_manager.create_test_file(f"file{i}.txt", f"Content {i}".encode())
            for i in range(3)
        ]
        
        # Mock operations
        async def mock_download(document, file, progress_callback=None):
            await asyncio.sleep(0.1)  # Simulate work
            with open(file, 'wb') as f:
                f.write(f"Downloaded {file}".encode())
            return file
        
        async def mock_upload(entity, file, **kwargs):
            await asyncio.sleep(0.1)  # Simulate work
            mock_message = Mock()
            mock_message.id = hash(file) % 100000
            return mock_message
        
        telegram_ops.client.download_media = mock_download
        telegram_ops.client.send_file = mock_upload
        
        # Execute concurrent downloads
        download_tasks = [
            telegram_ops.download_file(mock_document, f, use_fast_download=False)
            for f in files
        ]
        
        downloaded_files = await asyncio.gather(*download_tasks)
        assert len(downloaded_files) == 3
        
        # Execute concurrent uploads
        upload_tasks = [
            telegram_ops.upload_file(f, 123456)
            for f in files
        ]
        
        uploaded_messages = await asyncio.gather(*upload_tasks)
        assert len(uploaded_messages) == 3
        assert all(msg.id for msg in uploaded_messages)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])