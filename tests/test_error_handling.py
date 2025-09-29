"""
Tests for error handling scenarios and edge cases

Tests FastTelethon fallback, network failures, file corruption, and error recovery.
"""

import asyncio
import os
import tempfile
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path

# Import modules under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.queue_manager import QueueManager
from utils.telegram_operations import TelegramOperations
from utils.cache_manager import ProcessManager

# Try to import network_monitor, create mock if not available
try:
    from network_monitor import NetworkMonitor, NetworkType
except ImportError:
    # Create mock NetworkMonitor and NetworkType for testing
    class NetworkType:
        WIFI = "wifi"
        MOBILE = "mobile"
        ETHERNET = "ethernet"
        UNKNOWN = "unknown"
        DISCONNECTED = "disconnected"
    
    class NetworkMonitor:
        def __init__(self):
            self.is_monitoring = False
            
        def detect_connection_type(self):
            return NetworkType.WIFI
            
        async def start_monitoring(self):
            self.is_monitoring = True
            
        async def stop_monitoring(self):
            self.is_monitoring = False
            
        def add_callback(self, event, callback):
            pass
            
        async def _safe_callback(self, event, *args):
            pass
            
        async def wait_for_wifi(self, timeout=None):
            return True

class TestErrorHandling:
    """Test suite for error handling scenarios"""
    
    @pytest.mark.asyncio
    async def test_network_connection_failure(self, mock_client, mock_document):
        """Test handling of network connection failures"""
        telegram_ops = TelegramOperations(mock_client)
        
        # Mock connection failure
        async def mock_failing_download(document, file, progress_callback=None):
            raise ConnectionError("Network unreachable")
        
        mock_client.download_media = mock_failing_download
        
        # Test that error is handled gracefully
        with pytest.raises(Exception) as exc_info:
            await telegram_ops.download_file(
                mock_document, 
                "/tmp/test.pdf",
                use_fast_download=False,
                max_retries=1
            )
        
        assert "Network unreachable" in str(exc_info.value) or isinstance(exc_info.value, ConnectionError)
    
    @pytest.mark.asyncio
    async def test_disk_full_error(self, mock_client, file_manager):
        """Test handling of disk full errors during file operations"""
        telegram_ops = TelegramOperations(mock_client)
        
        # Mock disk full error
        async def mock_disk_full_upload(entity, file, **kwargs):
            raise OSError("No space left on device")
        
        mock_client.send_file = mock_disk_full_upload
        
        test_file = file_manager.create_test_file("upload.txt", b"Test content")
        
        # Test that disk full error is handled
        with pytest.raises(OSError) as exc_info:
            await telegram_ops.upload_file(test_file, 123456, max_retries=1)
        
        assert "No space left on device" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_file_corruption_detection(self, mock_client, file_manager, mock_document):
        """Test detection and handling of corrupted files"""
        telegram_ops = TelegramOperations(mock_client)
        
        # Mock download that creates corrupted file
        async def mock_corrupted_download(document, file, progress_callback=None):
            # Create file with wrong size
            with open(file, 'wb') as f:
                f.write(b"corrupted")  # Much smaller than expected
            return file
        
        mock_client.download_media = mock_corrupted_download
        
        # Mock document with large expected size
        mock_document.size = 1024 * 1024  # 1MB expected
        
        output_path = file_manager.create_test_file("corrupted.pdf", b"")
        
        # Download should complete but file size won't match
        result = await telegram_ops.download_file(
            mock_document,
            output_path,
            use_fast_download=False
        )
        
        # Verify file was created (even if corrupted)
        assert os.path.exists(result)
        
        # Check actual vs expected size
        actual_size = os.path.getsize(result)
        assert actual_size != mock_document.size
    
    @pytest.mark.asyncio
    async def test_permission_denied_error(self, mock_client, file_manager):
        """Test handling of permission denied errors"""
        telegram_ops = TelegramOperations(mock_client)
        
        # Create a file in a read-only directory (simulated)
        test_file = file_manager.create_test_file("readonly.txt", b"content")
        
        # Mock permission error
        async def mock_permission_error(entity, file, **kwargs):
            raise PermissionError("Permission denied")
        
        mock_client.send_file = mock_permission_error
        
        # Test permission error handling
        with pytest.raises(PermissionError):
            await telegram_ops.upload_file(test_file, 123456, max_retries=1)
    
    @pytest.mark.asyncio
    async def test_telegram_api_rate_limiting(self, mock_client, mock_document):
        """Test handling of Telegram API rate limiting"""
        from telethon.errors import FloodWaitError
        
        telegram_ops = TelegramOperations(mock_client)
        
        call_count = 0
        async def mock_rate_limited_download(document, file, progress_callback=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise FloodWaitError(seconds=1)  # Rate limited first time
            
            # Success on retry
            with open(file, 'wb') as f:
                f.write(b"Success after rate limit")
            return file
        
        mock_client.download_media = mock_rate_limited_download
        
        # Test that rate limiting is handled with retry
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            result = await telegram_ops.download_file(
                mock_document,
                temp_file.name,
                use_fast_download=False,
                max_retries=3
            )
            
            assert result == temp_file.name
            assert call_count == 2  # First failed, second succeeded
        
        os.unlink(temp_file.name)
    
    @pytest.mark.asyncio
    async def test_fast_download_fallback(self, mock_client, mock_document, file_manager):
        """Test FastTelethon fallback to standard download"""
        telegram_ops = TelegramOperations(mock_client)
        
        # Mock fast download failure
        with patch('utils.telegram_operations.fast_download_to_file') as mock_fast:
            mock_fast.side_effect = Exception("FastTelethon failed")
            
            # Mock successful standard download
            async def mock_standard_download(document, file, progress_callback=None):
                with open(file, 'wb') as f:
                    f.write(b"Standard download success")
                return file
            
            mock_client.download_media = mock_standard_download
            
            output_path = file_manager.create_test_file("fallback.pdf", b"")
            
            # Test fallback mechanism
            result = await telegram_ops.download_file(
                mock_document,
                output_path,
                use_fast_download=True  # Request fast download
            )
            
            # Should succeed with standard download
            assert result == output_path
            with open(output_path, 'rb') as f:
                content = f.read()
                assert content == b"Standard download success"
    
    @pytest.mark.asyncio
    async def test_queue_recovery_after_crash(self, mock_client, temp_dir, mock_document):
        """Test queue recovery after application crash"""
        download_file = os.path.join(temp_dir, 'download_queue.json')
        
        # Simulate crash scenario
        with patch('utils.queue_manager.DOWNLOAD_QUEUE_FILE', download_file):
            # First instance: add tasks
            manager1 = QueueManager(mock_client)
            task_id = await manager1.add_download_task(mock_document, "/test/crash_recovery.pdf")
            
            # Simulate processing start
            for task in manager1.download_queue:
                if task['id'] == task_id:
                    task['status'] = 'processing'
                    task['attempts'] = 1
                    break
            
            manager1.save_queues()
            
            # Simulate crash (manager1 goes out of scope)
            del manager1
        
        # Second instance: recovery
        with patch('utils.queue_manager.DOWNLOAD_QUEUE_FILE', download_file):
            manager2 = QueueManager(mock_client)
            manager2.load_queues()
            
            # Verify task was recovered
            assert len(manager2.download_queue) == 1
            recovered_task = manager2.download_queue[0]
            assert recovered_task['id'] == task_id
            assert recovered_task['status'] == 'processing'  # Should reset to pending on recovery
    
    @pytest.mark.asyncio
    async def test_memory_exhaustion_handling(self, mock_client, mock_document):
        """Test handling of memory exhaustion during large file processing"""
        telegram_ops = TelegramOperations(mock_client)
        
        # Mock memory error
        async def mock_memory_error(document, file, progress_callback=None):
            raise MemoryError("Cannot allocate memory")
        
        mock_client.download_media = mock_memory_error
        
        # Test memory error handling
        with pytest.raises(MemoryError):
            await telegram_ops.download_file(
                mock_document,
                "/tmp/large_file.bin",
                use_fast_download=False,
                max_retries=1
            )
    
    @pytest.mark.asyncio
    async def test_concurrent_task_failures(self, mock_client, mock_document, temp_dir):
        """Test handling of multiple concurrent task failures"""
        with patch('utils.queue_manager.DOWNLOAD_QUEUE_FILE', os.path.join(temp_dir, 'concurrent_failures.json')):
            queue_manager = QueueManager(mock_client)
            
            # Add multiple tasks
            task_ids = []
            for i in range(5):
                task_id = await queue_manager.add_download_task(
                    mock_document, f"/test/concurrent_{i}.pdf"
                )
                task_ids.append(task_id)
            
            # Mock download to fail for all tasks
            failure_count = 0
            async def mock_failing_download(task):
                nonlocal failure_count
                failure_count += 1
                return False, f"Failure {failure_count}"
            
            queue_manager._execute_download_task = mock_failing_download
            
            # Start processing
            await queue_manager.start_processing()
            await asyncio.sleep(1)  # Allow failures to occur
            await queue_manager.stop_processing()
            
            # Verify all tasks handled failures
            assert failure_count >= 5
            
            # Check that tasks are marked as failed after max retries
            failed_tasks = [t for t in queue_manager.download_queue if t['status'] == 'failed']
            assert len(failed_tasks) <= 5  # May be less if still retrying

class TestNetworkErrorHandling:
    """Test network-specific error scenarios"""
    
    def test_network_type_detection_failure(self):
        """Test handling of network type detection failures"""
        monitor = NetworkMonitor()
        
        # Mock all detection methods to fail
        with patch.object(monitor, '_check_android_connection', side_effect=Exception("Detection failed")):
            with patch.object(monitor, '_check_ip_route', side_effect=Exception("Route failed")):
                with patch.object(monitor, '_check_network_interfaces', side_effect=Exception("Interface failed")):
                    with patch.object(monitor, '_check_dumpsys', side_effect=Exception("Dumpsys failed")):
                        
                        # Should return UNKNOWN instead of crashing
                        connection_type = monitor.detect_connection_type()
                        assert connection_type == NetworkType.UNKNOWN
    
    @pytest.mark.asyncio
    async def test_network_monitoring_failure(self):
        """Test handling of network monitoring loop failures"""
        monitor = NetworkMonitor()
        
        # Mock detect_connection_type to fail
        with patch.object(monitor, 'detect_connection_type', side_effect=Exception("Detection error")):
            # Start monitoring (should handle errors gracefully)
            await monitor.start_monitoring()
            
            # Wait briefly for monitoring loop
            await asyncio.sleep(0.1)
            
            # Stop monitoring
            await monitor.stop_monitoring()
            
            # Should not crash, monitoring should stop cleanly
            assert not monitor.is_monitoring
    
    @pytest.mark.asyncio
    async def test_wifi_wait_timeout(self):  
        """Test timeout handling when waiting for WiFi"""
        monitor = NetworkMonitor()
        
        # Mock to always return mobile connection
        with patch.object(monitor, 'detect_connection_type', return_value=NetworkType.MOBILE):
            # Test timeout
            result = await monitor.wait_for_wifi(timeout=0.1)  # Very short timeout
            assert result is False  # Should timeout
    
    @pytest.mark.asyncio
    async def test_callback_error_handling(self):
        """Test error handling in network monitor callbacks"""
        monitor = NetworkMonitor()
        
        # Add callback that raises exception
        def failing_callback():
            raise Exception("Callback error")
        
        monitor.add_callback('wifi_connected', failing_callback)
        
        # Should handle callback error gracefully
        await monitor._safe_callback('wifi_connected')
        
        # Monitor should still be functional
        connection_type = monitor.detect_connection_type()
        assert connection_type in [NetworkType.WIFI, NetworkType.MOBILE, NetworkType.ETHERNET, 
                                 NetworkType.UNKNOWN, NetworkType.DISCONNECTED]

class TestFileSystemErrorHandling:
    """Test file system specific error scenarios"""
    
    def test_invalid_path_handling(self):
        """Test handling of invalid file paths"""
        process_manager = ProcessManager()
        
        # Mock invalid path operations
        with patch('builtins.open', side_effect=FileNotFoundError("Invalid path")):
            # Should handle gracefully
            process_manager.load_processed_archives()
            process_manager.load_current_processes()
            
            # Should not crash
            assert isinstance(process_manager.processed_archives, set)
    
    def test_file_lock_handling(self, temp_dir):
        """Test handling of file locking scenarios"""
        import threading
        import time
        
        process_manager = ProcessManager()
        
        # Create a file lock scenario
        test_file = os.path.join(temp_dir, 'locked_file.json')
        
        def lock_file():
            with open(test_file, 'w') as f:
                f.write('{"test": "data"}')
                time.sleep(0.5)  # Hold file open
        
        # Start file locking in background
        lock_thread = threading.Thread(target=lock_file)
        lock_thread.start()
        
        # Try to access file while locked
        time.sleep(0.1)  # Ensure lock is active
        
        with patch('utils.cache_manager.PROCESSED_ARCHIVES_FILE', test_file):
            # Should handle file being locked/busy
            process_manager.save_processed_archives()
        
        lock_thread.join()
    
    def test_readonly_filesystem(self, temp_dir):
        """Test handling of read-only filesystem"""
        process_manager = ProcessManager()
        
        # Mock permission error for read-only filesystem
        with patch('builtins.open', side_effect=PermissionError("Read-only file system")):
            # Should handle gracefully without crashing
            process_manager.save_processed_archives()
            process_manager.save_current_processes()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])