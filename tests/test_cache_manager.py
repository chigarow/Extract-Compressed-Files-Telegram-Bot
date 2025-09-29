"""
Tests for utils.cache_manager module

Tests file processing cache, process tracking, and persistent storage.
"""

import os
import json
import tempfile
import pytest
from unittest.mock import Mock, patch
from pathlib import Path

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.cache_manager import ProcessManager
from utils.constants import *

class TestProcessManager:
    """Test suite for ProcessManager class"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        import shutil
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def process_manager(self, temp_dir):
        """Create ProcessManager instance for testing"""
        # Patch the file paths to use temporary directory
        with patch('utils.cache_manager.PROCESSED_ARCHIVES_FILE', 
                  os.path.join(temp_dir, 'processed_archives.json')):
            with patch('utils.cache_manager.CURRENT_PROCESS_FILE',
                      os.path.join(temp_dir, 'current_process.json')):
                manager = ProcessManager()
                yield manager
    
    def test_initialization(self, process_manager):
        """Test ProcessManager initialization"""
        assert isinstance(process_manager.processed_archives, set)
        assert process_manager.current_download_process is None
        assert process_manager.current_upload_process is None
    
    def test_add_processed_archive(self, process_manager):
        """Test adding processed archive to cache"""
        file_hash = "test_hash_123"
        
        # Add archive
        process_manager.add_processed_archive(file_hash)
        
        # Check if added
        assert file_hash in process_manager.processed_archives
        assert process_manager.is_already_processed(file_hash) is True
    
    def test_is_already_processed(self, process_manager):
        """Test checking if archive is already processed"""
        file_hash = "test_hash_456"
        
        # Should not be processed initially
        assert process_manager.is_already_processed(file_hash) is False
        
        # Add to processed
        process_manager.add_processed_archive(file_hash)
        
        # Should now be processed
        assert process_manager.is_already_processed(file_hash) is True
    
    def test_remove_processed_archive(self, process_manager):
        """Test removing processed archive from cache"""
        file_hash = "test_hash_789"
        
        # Add then remove
        process_manager.add_processed_archive(file_hash)
        assert process_manager.is_already_processed(file_hash) is True
        
        process_manager.remove_processed_archive(file_hash)
        assert process_manager.is_already_processed(file_hash) is False
    
    def test_clear_processed_archives(self, process_manager):
        """Test clearing all processed archives"""
        # Add multiple archives
        hashes = ["hash1", "hash2", "hash3"]
        for hash_val in hashes:
            process_manager.add_processed_archive(hash_val)
        
        assert len(process_manager.processed_archives) == 3
        
        # Clear all
        process_manager.clear_processed_archives()
        assert len(process_manager.processed_archives) == 0
    
    def test_save_and_load_processed_archives(self, process_manager, temp_dir):
        """Test saving and loading processed archives"""
        # Add some archives
        hashes = ["hash_a", "hash_b", "hash_c"]
        for hash_val in hashes:
            process_manager.add_processed_archive(hash_val)
        
        # Save to file
        process_manager.save_processed_archives()
        
        # Verify file exists
        archive_file = os.path.join(temp_dir, 'processed_archives.json')
        assert os.path.exists(archive_file)
        
        # Load with new instance
        with patch('utils.cache_manager.PROCESSED_ARCHIVES_FILE', archive_file):
            new_manager = ProcessManager()
            new_manager.load_processed_archives()
        
        # Verify loaded data
        assert len(new_manager.processed_archives) == 3
        for hash_val in hashes:
            assert new_manager.is_already_processed(hash_val)
    
    def test_save_processed_archives_error_handling(self, process_manager):
        """Test error handling when saving processed archives"""
        # Mock file operations to raise exception
        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            # Should not raise exception, just log error
            process_manager.save_processed_archives()
    
    def test_load_processed_archives_error_handling(self, process_manager):
        """Test error handling when loading processed archives"""
        # Mock file operations to raise exception
        with patch('builtins.open', side_effect=FileNotFoundError("File not found")):
            # Should not raise exception, just log error
            process_manager.load_processed_archives()
            # Should have empty set
            assert len(process_manager.processed_archives) == 0
    
    def test_load_processed_archives_invalid_json(self, process_manager, temp_dir):
        """Test loading invalid JSON file"""
        # Create invalid JSON file
        archive_file = os.path.join(temp_dir, 'processed_archives.json')
        with open(archive_file, 'w') as f:
            f.write("invalid json content")
        
        with patch('utils.cache_manager.PROCESSED_ARCHIVES_FILE', archive_file):
            new_manager = ProcessManager()
            new_manager.load_processed_archives()
        
        # Should handle gracefully and have empty set
        assert len(new_manager.processed_archives) == 0
    
    @pytest.mark.asyncio
    async def test_update_download_process(self, process_manager):
        """Test updating download process"""
        process_info = {
            'file_name': 'test.pdf',
            'progress': 50,
            'status': 'downloading'
        }
        
        await process_manager.update_download_process(process_info)
        
        assert process_manager.current_download_process == process_info
    
    @pytest.mark.asyncio
    async def test_update_upload_process(self, process_manager):
        """Test updating upload process"""
        process_info = {
            'file_name': 'test.txt',
            'progress': 75,
            'status': 'uploading'
        }
        
        await process_manager.update_upload_process(process_info)
        
        assert process_manager.current_upload_process == process_info
    
    @pytest.mark.asyncio
    async def test_clear_download_process(self, process_manager):
        """Test clearing download process"""
        # Set a download process
        await process_manager.update_download_process({'status': 'active'})
        assert process_manager.current_download_process is not None
        
        # Clear it
        await process_manager.clear_download_process()
        assert process_manager.current_download_process is None
    
    @pytest.mark.asyncio
    async def test_clear_upload_process(self, process_manager):
        """Test clearing upload process"""
        # Set an upload process
        await process_manager.update_upload_process({'status': 'active'})
        assert process_manager.current_upload_process is not None
        
        # Clear it
        await process_manager.clear_upload_process()
        assert process_manager.current_upload_process is None
    
    def test_get_current_processes(self, process_manager):
        """Test getting current processes"""
        # Set some processes
        download_info = {'file': 'download.pdf', 'progress': 30}
        upload_info = {'file': 'upload.txt', 'progress': 80}
        
        process_manager.current_download_process = download_info
        process_manager.current_upload_process = upload_info
        
        processes = process_manager.get_current_processes()
        
        assert processes['download'] == download_info
        assert processes['upload'] == upload_info
    
    def test_save_and_load_current_processes(self, process_manager, temp_dir):
        """Test saving and loading current processes"""
        # Set current processes
        download_info = {'file': 'test_download.mp4', 'progress': 45}
        upload_info = {'file': 'test_upload.zip', 'progress': 90}
        
        process_manager.current_download_process = download_info
        process_manager.current_upload_process = upload_info
        
        # Save processes
        process_manager.save_current_processes()
        
        # Verify file exists
        process_file = os.path.join(temp_dir, 'current_process.json')
        assert os.path.exists(process_file)
        
        # Load with new instance
        with patch('utils.cache_manager.CURRENT_PROCESS_FILE', process_file):
            new_manager = ProcessManager()
            new_manager.load_current_processes()
        
        # Verify loaded data
        assert new_manager.current_download_process == download_info
        assert new_manager.current_upload_process == upload_info
    
    def test_save_current_processes_error_handling(self, process_manager):
        """Test error handling when saving current processes"""
        # Mock file operations to raise exception
        with patch('builtins.open', side_effect=OSError("Disk full")):
            # Should not raise exception, just log error
            process_manager.save_current_processes()
    
    def test_load_current_processes_error_handling(self, process_manager):
        """Test error handling when loading current processes"""
        # Mock file operations to raise exception
        with patch('builtins.open', side_effect=FileNotFoundError("File not found")):
            # Should not raise exception, just log error
            process_manager.load_current_processes()
    
    def test_processed_archives_file_format(self, process_manager, temp_dir):
        """Test the format of saved processed archives file"""
        # Add some archives
        hashes = ["abc123", "def456", "ghi789"]
        for hash_val in hashes:
            process_manager.add_processed_archive(hash_val)
        
        # Save to file
        process_manager.save_processed_archives()
        
        # Read and verify file format
        archive_file = os.path.join(temp_dir, 'processed_archives.json')
        with open(archive_file, 'r') as f:
            data = json.load(f)
        
        assert 'processed_archives' in data
        assert isinstance(data['processed_archives'], list)
        assert set(data['processed_archives']) == set(hashes)
        assert 'last_updated' in data
    
    def test_current_processes_file_format(self, process_manager, temp_dir):
        """Test the format of saved current processes file"""
        # Set current processes
        download_info = {'file': 'test.pdf', 'progress': 60}
        upload_info = {'file': 'test.txt', 'progress': 40}
        
        process_manager.current_download_process = download_info
        process_manager.current_upload_process = upload_info
        
        # Save processes
        process_manager.save_current_processes()
        
        # Read and verify file format
        process_file = os.path.join(temp_dir, 'current_process.json')
        with open(process_file, 'r') as f:
            data = json.load(f)
        
        assert 'download_process' in data
        assert 'upload_process' in data
        assert data['download_process'] == download_info
        assert data['upload_process'] == upload_info

class TestProcessManagerIntegration:
    """Integration tests for ProcessManager"""
    
    def test_full_workflow_simulation(self, temp_dir):
        """Test complete workflow simulation"""
        # Create ProcessManager with temporary files
        with patch('utils.cache_manager.PROCESSED_ARCHIVES_FILE',
                  os.path.join(temp_dir, 'processed_archives.json')):
            with patch('utils.cache_manager.CURRENT_PROCESS_FILE',
                      os.path.join(temp_dir, 'current_process.json')):
                
                manager = ProcessManager()
                
                # Simulate processing workflow
                file_hash = "workflow_test_hash"
                
                # 1. Check if already processed (should be False)
                assert not manager.is_already_processed(file_hash)
                
                # 2. Start download process
                download_info = {'file': 'test.zip', 'status': 'downloading', 'progress': 0}
                manager.current_download_process = download_info
                manager.save_current_processes()
                
                # 3. Update download progress
                download_info['progress'] = 50
                manager.current_download_process = download_info
                manager.save_current_processes()
                
                # 4. Complete download, start upload
                manager.current_download_process = None
                upload_info = {'file': 'extracted.txt', 'status': 'uploading', 'progress': 0}
                manager.current_upload_process = upload_info
                manager.save_current_processes()
                
                # 5. Complete upload
                manager.current_upload_process = None
                manager.save_current_processes()
                
                # 6. Mark as processed
                manager.add_processed_archive(file_hash)
                manager.save_processed_archives()
                
                # 7. Verify final state
                assert manager.is_already_processed(file_hash)
                assert manager.current_download_process is None
                assert manager.current_upload_process is None
    
    def test_persistence_across_restarts(self, temp_dir):
        """Test data persistence across application restarts"""
        processed_file = os.path.join(temp_dir, 'processed_archives.json')
        process_file = os.path.join(temp_dir, 'current_process.json')
        
        # First session
        with patch('utils.cache_manager.PROCESSED_ARCHIVES_FILE', processed_file):
            with patch('utils.cache_manager.CURRENT_PROCESS_FILE', process_file):
                manager1 = ProcessManager()
                
                # Add some data
                manager1.add_processed_archive("session1_hash")
                manager1.current_download_process = {'file': 'interrupted.zip', 'progress': 30}
                
                # Save data
                manager1.save_processed_archives()
                manager1.save_current_processes()
        
        # Second session (simulating restart)
        with patch('utils.cache_manager.PROCESSED_ARCHIVES_FILE', processed_file):
            with patch('utils.cache_manager.CURRENT_PROCESS_FILE', process_file):
                manager2 = ProcessManager()
                
                # Load data
                manager2.load_processed_archives()
                manager2.load_current_processes()
                
                # Verify data persistence
                assert manager2.is_already_processed("session1_hash")
                assert manager2.current_download_process['file'] == 'interrupted.zip'
                assert manager2.current_download_process['progress'] == 30
    
    def test_concurrent_access_safety(self, temp_dir):
        """Test safe concurrent access to files"""
        import threading
        import time
        
        processed_file = os.path.join(temp_dir, 'processed_archives.json')
        
        with patch('utils.cache_manager.PROCESSED_ARCHIVES_FILE', processed_file):
            manager = ProcessManager()
            
            # Function to add archives concurrently
            def add_archives(start_idx, count):
                for i in range(start_idx, start_idx + count):
                    manager.add_processed_archive(f"hash_{i}")
                    manager.save_processed_archives()
                    time.sleep(0.001)  # Small delay
            
            # Create multiple threads
            threads = []
            for i in range(3):
                thread = threading.Thread(target=add_archives, args=(i * 10, 5))
                threads.append(thread)
                thread.start()
            
            # Wait for all threads
            for thread in threads:
                thread.join()
            
            # Verify all hashes were added
            assert len(manager.processed_archives) == 15
            
            # Verify file integrity
            manager.load_processed_archives()
            assert len(manager.processed_archives) == 15

if __name__ == "__main__":
    pytest.main([__file__, "-v"])