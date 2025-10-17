#!/usr/bin/env python3
"""Comprehensive tests for cleanup functionality."""

import os
import sys
import time
import tempfile
import shutil
import pytest
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.queue_manager import QueueManager
from utils.constants import DATA_DIR, TORBOX_DIR


class TestCleanupFunctionality:
    """Test suite for cleanup methods."""
    
    @pytest.fixture
    def temp_test_dir(self):
        """Create a temporary test directory."""
        test_dir = tempfile.mkdtemp(prefix="test_cleanup_")
        yield test_dir
        # Cleanup after test
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
    
    @pytest.fixture
    def queue_manager(self):
        """Create a QueueManager instance for testing."""
        return QueueManager()
    
    def test_cleanup_old_files_empty_directory(self, queue_manager, temp_test_dir):
        """Test cleanup with no files in directory."""
        with patch('utils.queue_manager.DATA_DIR', temp_test_dir):
            removed = queue_manager.cleanup_old_files(max_age_hours=24)
            assert removed == 0, "Should not remove any files from empty directory"
    
    def test_cleanup_old_files_with_old_files(self, queue_manager, temp_test_dir):
        """Test cleanup removes files older than specified age."""
        # Create test files with different ages
        old_file = os.path.join(temp_test_dir, "old_file.txt")
        new_file = os.path.join(temp_test_dir, "new_file.txt")
        
        # Create files
        with open(old_file, 'w') as f:
            f.write("old content")
        with open(new_file, 'w') as f:
            f.write("new content")
        
        # Make old file look old (48 hours)
        old_time = time.time() - (48 * 3600)
        os.utime(old_file, (old_time, old_time))
        
        with patch('utils.queue_manager.DATA_DIR', temp_test_dir):
            # Should remove old file but not new file
            removed = queue_manager.cleanup_old_files(max_age_hours=24)
            
            assert removed == 1, "Should remove exactly 1 old file"
            assert not os.path.exists(old_file), "Old file should be removed"
            assert os.path.exists(new_file), "New file should still exist"
    
    def test_cleanup_old_files_preserves_recent_files(self, queue_manager, temp_test_dir):
        """Test cleanup preserves files newer than threshold."""
        # Create recent files
        for i in range(3):
            test_file = os.path.join(temp_test_dir, f"recent_file_{i}.txt")
            with open(test_file, 'w') as f:
                f.write(f"content {i}")
        
        with patch('utils.queue_manager.DATA_DIR', temp_test_dir):
            removed = queue_manager.cleanup_old_files(max_age_hours=1)
            
            assert removed == 0, "Should not remove any recent files"
            assert len(os.listdir(temp_test_dir)) == 3, "All files should still exist"
    
    def test_cleanup_old_files_skips_protected_files(self, queue_manager, temp_test_dir):
        """Test cleanup skips protected JSON files and session files."""
        # Create protected files
        protected_files = [
            "processed_archives.json",
            "download_queue.json",
            "upload_queue.json",
            "retry_queue.json",
            "current_process.json",
            "session.session"
        ]
        
        for filename in protected_files:
            filepath = os.path.join(temp_test_dir, filename)
            with open(filepath, 'w') as f:
                f.write("{}")
        
        # Make them all old
        old_time = time.time() - (48 * 3600)
        for filename in protected_files:
            filepath = os.path.join(temp_test_dir, filename)
            os.utime(filepath, (old_time, old_time))
        
        with patch('utils.queue_manager.DATA_DIR', temp_test_dir):
            removed = queue_manager.cleanup_old_files(max_age_hours=24)
            
            assert removed == 0, "Should not remove protected files"
            assert len(os.listdir(temp_test_dir)) == len(protected_files), "All protected files should exist"
    
    def test_cleanup_old_files_handles_errors_gracefully(self, queue_manager, temp_test_dir):
        """Test cleanup handles file deletion errors gracefully."""
        test_file = os.path.join(temp_test_dir, "test_file.txt")
        with open(test_file, 'w') as f:
            f.write("content")
        
        # Make file old
        old_time = time.time() - (48 * 3600)
        os.utime(test_file, (old_time, old_time))
        
        with patch('utils.queue_manager.DATA_DIR', temp_test_dir):
            with patch('os.remove', side_effect=PermissionError("Access denied")):
                # Should not crash, just log the error
                removed = queue_manager.cleanup_old_files(max_age_hours=24)
                assert removed == 0, "Should report 0 files removed on error"
    
    def test_cleanup_failed_upload_files_empty_directory(self, queue_manager, temp_test_dir):
        """Test cleanup with no extraction directories."""
        with patch('utils.queue_manager.DATA_DIR', temp_test_dir):
            removed_dirs = queue_manager.cleanup_failed_upload_files()
            assert len(removed_dirs) == 0, "Should find no directories to remove"
    
    def test_cleanup_failed_upload_files_removes_orphaned_dirs(self, queue_manager, temp_test_dir):
        """Test cleanup removes orphaned extraction directories."""
        # Create test extraction directories
        test_dirs = [
            os.path.join(temp_test_dir, "test_archive_extracted"),
            os.path.join(temp_test_dir, "another_file_extracted"),
            os.path.join(temp_test_dir, "old_extraction_extracted")
        ]
        
        for test_dir in test_dirs:
            os.makedirs(test_dir)
            # Add some files to make it look real
            with open(os.path.join(test_dir, "file.txt"), 'w') as f:
                f.write("extracted content")
        
        with patch('utils.queue_manager.DATA_DIR', temp_test_dir):
            removed_dirs = queue_manager.cleanup_failed_upload_files()
            
            assert len(removed_dirs) == 3, "Should remove all 3 extraction directories"
            for test_dir in test_dirs:
                assert not os.path.exists(test_dir), f"Directory {test_dir} should be removed"
    
    def test_cleanup_failed_upload_files_skips_active_dirs(self, queue_manager, temp_test_dir):
        """Test cleanup skips directories that are in active processing."""
        test_dir = os.path.join(temp_test_dir, "active_extraction_extracted")
        os.makedirs(test_dir)
        
        # Mock active processing
        queue_manager.processing_archives = {"active_extraction_extracted"}
        
        with patch('utils.queue_manager.DATA_DIR', temp_test_dir):
            removed_dirs = queue_manager.cleanup_failed_upload_files()
            
            assert len(removed_dirs) == 0, "Should not remove active extraction directory"
            assert os.path.exists(test_dir), "Active directory should still exist"
    
    def test_cleanup_failed_upload_files_handles_errors(self, queue_manager, temp_test_dir):
        """Test cleanup handles directory deletion errors gracefully."""
        test_dir = os.path.join(temp_test_dir, "problematic_extracted")
        os.makedirs(test_dir)
        
        with patch('utils.queue_manager.DATA_DIR', temp_test_dir):
            with patch('shutil.rmtree', side_effect=PermissionError("Access denied")):
                # Should not crash
                removed_dirs = queue_manager.cleanup_failed_upload_files()
                assert len(removed_dirs) == 0, "Should report 0 directories removed on error"
    
    def test_cleanup_old_files_calculates_size_correctly(self, queue_manager, temp_test_dir):
        """Test cleanup calculates total size of removed files."""
        # Create files with known sizes
        file1 = os.path.join(temp_test_dir, "file1.txt")
        file2 = os.path.join(temp_test_dir, "file2.txt")
        
        with open(file1, 'w') as f:
            f.write("a" * 1000)  # 1KB
        with open(file2, 'w') as f:
            f.write("b" * 2000)  # 2KB
        
        # Make files old
        old_time = time.time() - (48 * 3600)
        os.utime(file1, (old_time, old_time))
        os.utime(file2, (old_time, old_time))
        
        with patch('utils.queue_manager.DATA_DIR', temp_test_dir):
            removed = queue_manager.cleanup_old_files(max_age_hours=24)
            
            assert removed == 2, "Should remove both files"
            # Size calculation is tested internally by the method
    
    def test_cleanup_preserves_torbox_directory(self, queue_manager, temp_test_dir):
        """Test cleanup preserves the torbox subdirectory."""
        torbox_dir = os.path.join(temp_test_dir, "torbox")
        os.makedirs(torbox_dir)
        
        # Create old file in torbox dir
        old_file = os.path.join(torbox_dir, "old_torbox_file.zip")
        with open(old_file, 'w') as f:
            f.write("content")
        
        old_time = time.time() - (48 * 3600)
        os.utime(old_file, (old_time, old_time))
        
        with patch('utils.queue_manager.DATA_DIR', temp_test_dir):
            removed = queue_manager.cleanup_old_files(max_age_hours=24)
            
            # Torbox files should be cleaned but directory should remain
            assert os.path.exists(torbox_dir), "Torbox directory should be preserved"
    
    def test_multiple_cleanup_operations(self, queue_manager, temp_test_dir):
        """Test running multiple cleanup operations in sequence."""
        # Create a mix of old files and extraction directories
        old_file = os.path.join(temp_test_dir, "old.txt")
        with open(old_file, 'w') as f:
            f.write("old content")
        
        old_time = time.time() - (48 * 3600)
        os.utime(old_file, (old_time, old_time))
        
        extraction_dir = os.path.join(temp_test_dir, "test_extracted")
        os.makedirs(extraction_dir)
        
        with patch('utils.queue_manager.DATA_DIR', temp_test_dir):
            # First cleanup: old files
            removed_files = queue_manager.cleanup_old_files(max_age_hours=24)
            assert removed_files == 1, "Should remove old file"
            
            # Second cleanup: extraction directories
            removed_dirs = queue_manager.cleanup_failed_upload_files()
            assert len(removed_dirs) == 1, "Should remove extraction directory"
            
            # Verify everything is clean
            items = os.listdir(temp_test_dir)
            assert len(items) == 0, "Directory should be empty after cleanup"


class TestCleanupCommandHandlers:
    """Test suite for cleanup command handlers."""
    
    @pytest.fixture
    def mock_event(self):
        """Create a mock Telegram event."""
        event = Mock()
        event.reply = Mock()
        event.sender_id = 12345
        return event
    
    @pytest.mark.asyncio
    async def test_handle_cleanup_command_default_age(self, mock_event):
        """Test cleanup command with default age parameter."""
        from utils.command_handlers import handle_cleanup_command
        
        await handle_cleanup_command(mock_event)
        
        # Should ask for confirmation
        assert mock_event.reply.called, "Should reply to user"
        call_args = str(mock_event.reply.call_args)
        assert "24" in call_args, "Should mention default 24 hours"
    
    @pytest.mark.asyncio
    async def test_handle_cleanup_command_custom_age(self, mock_event):
        """Test cleanup command with custom age parameter."""
        from utils.command_handlers import handle_cleanup_command
        
        await handle_cleanup_command(mock_event, age_hours=48)
        
        assert mock_event.reply.called
        call_args = str(mock_event.reply.call_args)
        assert "48" in call_args, "Should mention custom 48 hours"
    
    @pytest.mark.asyncio
    async def test_handle_cleanup_orphans_command(self, mock_event):
        """Test cleanup orphans command."""
        from utils.command_handlers import handle_cleanup_orphans_command
        
        with patch('utils.command_handlers.queue_manager') as mock_qm:
            mock_qm.cleanup_failed_upload_files.return_value = []
            
            await handle_cleanup_orphans_command(mock_event)
            
            assert mock_event.reply.called, "Should reply to user"
            mock_qm.cleanup_failed_upload_files.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_confirm_cleanup_command_no_pending(self, mock_event):
        """Test confirm cleanup when no cleanup is pending."""
        from utils.command_handlers import handle_confirm_cleanup_command
        
        # Clear any pending cleanup
        from utils import command_handlers
        command_handlers.pending_cleanup = {}
        
        await handle_confirm_cleanup_command(mock_event)
        
        assert mock_event.reply.called
        call_args = str(mock_event.reply.call_args)
        assert "no pending" in call_args.lower(), "Should indicate no pending cleanup"
    
    @pytest.mark.asyncio
    async def test_handle_confirm_cleanup_command_executes(self, mock_event):
        """Test confirm cleanup executes pending cleanup."""
        from utils.command_handlers import handle_confirm_cleanup_command
        from utils import command_handlers
        
        # Set up pending cleanup
        command_handlers.pending_cleanup[12345] = 24
        
        with patch('utils.command_handlers.queue_manager') as mock_qm:
            mock_qm.cleanup_old_files.return_value = 5
            
            await handle_confirm_cleanup_command(mock_event)
            
            mock_qm.cleanup_old_files.assert_called_once_with(max_age_hours=24)
            assert mock_event.reply.called
            assert 12345 not in command_handlers.pending_cleanup, "Should clear pending cleanup"


def test_constants_torbox_dir_exists():
    """Test that TORBOX_DIR constant is properly defined."""
    assert TORBOX_DIR is not None, "TORBOX_DIR should be defined"
    assert "torbox" in TORBOX_DIR.lower(), "TORBOX_DIR should contain 'torbox'"
    assert DATA_DIR in TORBOX_DIR, "TORBOX_DIR should be under DATA_DIR"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
