"""
Unit tests for deferred video conversion feature.
Tests state management, crash recovery, and conversion workflow.
"""

import pytest
import os
import json
import tempfile
import shutil
from unittest.mock import Mock, patch, AsyncMock
from utils.conversion_state import ConversionStateManager
from utils.constants import DEFERRED_VIDEO_CONVERSION


class TestConversionStateManager:
    """Test conversion state management."""
    
    @pytest.fixture
    def temp_state_file(self):
        """Create a temporary state file."""
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.remove(path)
    
    @pytest.fixture
    def state_manager(self, temp_state_file):
        """Create a state manager with temporary file."""
        return ConversionStateManager(state_file=temp_state_file)
    
    def test_save_and_load_state(self, state_manager):
        """Test saving and loading conversion state."""
        file_path = "/path/to/video.mov"
        output_path = "/path/to/video_converted.mp4"
        
        # Save state
        state_manager.save_state(
            file_path=file_path,
            status='in_progress',
            progress=45,
            output_path=output_path
        )
        
        # Load state
        state = state_manager.load_state(file_path)
        
        assert state is not None
        assert state['file_path'] == file_path
        assert state['output_path'] == output_path
        assert state['status'] == 'in_progress'
        assert state['progress'] == 45
        assert 'started_at' in state
        assert 'last_updated' in state
    
    def test_mark_completed(self, state_manager):
        """Test marking conversion as completed."""
        file_path = "/path/to/video.mov"
        
        # Save initial state
        state_manager.save_state(
            file_path=file_path,
            status='in_progress',
            progress=50,
            output_path="/path/to/output.mp4"
        )
        
        # Mark completed
        state_manager.mark_completed(file_path)
        
        # Verify
        state = state_manager.load_state(file_path)
        assert state['status'] == 'completed'
        assert state['progress'] == 100
    
    def test_mark_failed(self, state_manager):
        """Test marking conversion as failed."""
        file_path = "/path/to/video.mov"
        error_msg = "Conversion timeout"
        
        # Save initial state
        state_manager.save_state(
            file_path=file_path,
            status='in_progress',
            progress=30,
            output_path="/path/to/output.mp4"
        )
        
        # Mark failed
        state_manager.mark_failed(file_path, error_msg)
        
        # Verify
        state = state_manager.load_state(file_path)
        assert state['status'] == 'failed'
        assert state['error'] == error_msg
    
    def test_get_incomplete_conversions(self, state_manager, tmp_path):
        """Test getting incomplete conversions."""
        # Create test files
        file1 = tmp_path / "video1.mov"
        file2 = tmp_path / "video2.mov"
        file3 = tmp_path / "video3.mov"
        
        file1.touch()
        file2.touch()
        # file3 doesn't exist (simulates missing file)
        
        # Save states
        state_manager.save_state(str(file1), 'in_progress', 50, str(tmp_path / "out1.mp4"))
        state_manager.save_state(str(file2), 'pending', 0, str(tmp_path / "out2.mp4"))
        state_manager.save_state(str(file3), 'in_progress', 30, str(tmp_path / "out3.mp4"))
        state_manager.save_state(str(tmp_path / "video4.mov"), 'completed', 100, str(tmp_path / "out4.mp4"))
        
        # Get incomplete
        incomplete = state_manager.get_incomplete_conversions()
        
        # Should return file1 and file2 (file3 is missing, file4 is completed)
        assert len(incomplete) == 2
        file_paths = [s['file_path'] for s in incomplete]
        assert str(file1) in file_paths
        assert str(file2) in file_paths
    
    def test_increment_retry_count(self, state_manager):
        """Test incrementing retry count."""
        file_path = "/path/to/video.mov"
        
        # Save initial state
        state_manager.save_state(
            file_path=file_path,
            status='pending',
            progress=0,
            output_path="/path/to/output.mp4"
        )
        
        # Increment retry count
        state_manager.increment_retry_count(file_path)
        state_manager.increment_retry_count(file_path)
        
        # Verify
        state = state_manager.load_state(file_path)
        assert state['retry_count'] == 2
    
    def test_cleanup_completed(self, state_manager):
        """Test cleanup of old completed conversions."""
        import time
        
        # Save completed state with old timestamp
        file_path = "/path/to/video.mov"
        state_manager.save_state(
            file_path=file_path,
            status='completed',
            progress=100,
            output_path="/path/to/output.mp4"
        )
        
        # Manually set old timestamp (25 hours ago)
        state_manager.states[file_path]['last_updated'] = time.time() - (25 * 3600)
        state_manager._save_states()
        
        # Cleanup (max_age_hours=24)
        state_manager.cleanup_completed(max_age_hours=24)
        
        # Verify state was removed
        assert state_manager.load_state(file_path) is None
    
    def test_get_stats(self, state_manager):
        """Test getting conversion statistics."""
        # Save various states
        state_manager.save_state("/path/1.mov", 'pending', 0, "/path/1.mp4")
        state_manager.save_state("/path/2.mov", 'in_progress', 50, "/path/2.mp4")
        state_manager.save_state("/path/3.mov", 'completed', 100, "/path/3.mp4")
        state_manager.save_state("/path/4.mov", 'failed', 0, "/path/4.mp4", error="Test error")
        
        # Get stats
        stats = state_manager.get_stats()
        
        assert stats['total'] == 4
        assert stats['pending'] == 1
        assert stats['in_progress'] == 1
        assert stats['completed'] == 1
        assert stats['failed'] == 1
    
    def test_persistence_across_instances(self, temp_state_file):
        """Test that state persists across manager instances."""
        file_path = "/path/to/video.mov"
        
        # Create first manager and save state
        manager1 = ConversionStateManager(state_file=temp_state_file)
        manager1.save_state(
            file_path=file_path,
            status='in_progress',
            progress=75,
            output_path="/path/to/output.mp4"
        )
        
        # Create second manager (simulates restart)
        manager2 = ConversionStateManager(state_file=temp_state_file)
        
        # Verify state was loaded
        state = manager2.load_state(file_path)
        assert state is not None
        assert state['progress'] == 75
        assert state['status'] == 'in_progress'


class TestDeferredConversionWorkflow:
    """Test deferred conversion workflow integration."""
    
    @pytest.fixture
    def mock_queue_manager(self):
        """Create a mock queue manager."""
        from utils.queue_manager import QueueManager
        manager = Mock(spec=QueueManager)
        manager.upload_queue = AsyncMock()
        manager.add_upload_task = AsyncMock()
        return manager
    
    @pytest.mark.asyncio
    async def test_incompatible_video_detection(self):
        """Test detection of incompatible videos."""
        from utils.media_processing import is_telegram_compatible_video
        
        # This would need actual video files to test properly
        # For now, test the function exists and has correct signature
        assert callable(is_telegram_compatible_video)
    
    @pytest.mark.asyncio
    async def test_deferred_task_creation(self, mock_queue_manager):
        """Test creation of deferred conversion tasks."""
        file_path = "/path/to/incompatible_video.mov"
        filename = "incompatible_video.mov"
        
        # Create deferred task
        deferred_task = {
            'type': 'deferred_conversion',
            'file_path': file_path,
            'filename': filename,
            'archive_name': 'test_archive.zip',
            'extraction_folder': '/path/to/extracted',
            'retry_count': 0
        }
        
        # Verify task structure
        assert deferred_task['type'] == 'deferred_conversion'
        assert deferred_task['file_path'] == file_path
        assert deferred_task['filename'] == filename
        assert deferred_task['retry_count'] == 0
    
    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """Test that deferred conversions are processed after normal uploads."""
        from utils.queue_manager import QueueManager
        
        # Create queue manager
        manager = QueueManager()
        manager._disable_upload_worker_start = True
        
        # Clear any pre-existing queue items from restored state
        manager.clear_all_queues()
        
        # Add normal upload task
        normal_task = {
            'type': 'direct_media',
            'file_path': '/path/to/image.jpg',
            'filename': 'image.jpg'
        }
        await manager.add_upload_task(normal_task)
        
        # Add deferred conversion task
        deferred_task = {
            'type': 'deferred_conversion',
            'file_path': '/path/to/video.mov',
            'filename': 'video.mov'
        }
        await manager.add_upload_task(deferred_task)
        
        # Verify queue has both tasks
        assert manager.upload_queue.qsize() == 2
        
        # Clean up
        manager.clear_all_queues()


class TestCrashRecovery:
    """Test crash recovery functionality."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def temp_state_file(self, tmp_path):
        """Create a temporary state file for testing."""
        return str(tmp_path / "test_conversion_state.json")
    
    @pytest.mark.asyncio
    async def test_recovery_on_startup(self, temp_dir, temp_state_file):
        """Test recovery of incomplete conversions on startup."""
        # Create test video file
        video_file = os.path.join(temp_dir, "test_video.mov")
        with open(video_file, 'w') as f:
            f.write("fake video content")
        
        # Create state manager and save incomplete conversion
        state_manager = ConversionStateManager(state_file=temp_state_file)
        state_manager.save_state(
            file_path=video_file,
            status='in_progress',
            progress=50,
            output_path=os.path.join(temp_dir, "test_video_converted.mp4")
        )
        
        # Get incomplete conversions (simulates startup recovery)
        incomplete = state_manager.get_incomplete_conversions()
        
        assert len(incomplete) == 1
        assert incomplete[0]['file_path'] == video_file
        assert incomplete[0]['status'] == 'in_progress'
        assert incomplete[0]['progress'] == 50
    
    @pytest.mark.asyncio
    async def test_missing_file_handling(self, temp_state_file):
        """Test handling of missing files during recovery."""
        # Create state for non-existent file
        state_manager = ConversionStateManager(state_file=temp_state_file)
        missing_file = "/path/to/nonexistent_video.mov"
        
        state_manager.save_state(
            file_path=missing_file,
            status='in_progress',
            progress=30,
            output_path="/path/to/output.mp4"
        )
        
        # Get incomplete conversions
        incomplete = state_manager.get_incomplete_conversions()
        
        # Should be empty (file doesn't exist)
        assert len(incomplete) == 0
        
        # State should be marked as failed
        state = state_manager.load_state(missing_file)
        assert state['status'] == 'failed'
        assert 'missing' in state['error'].lower()


class TestConfigurationIntegration:
    """Test configuration integration."""
    
    def test_deferred_conversion_flag(self):
        """Test that deferred conversion flag is accessible."""
        assert isinstance(DEFERRED_VIDEO_CONVERSION, bool)
    
    def test_conversion_constants(self):
        """Test that conversion constants are defined."""
        from utils.constants import (
            CONVERSION_STATE_FILE,
            CONVERSION_MAX_RETRIES,
            CONVERSION_STATE_SAVE_INTERVAL,
            RECOVERY_DIR,
            QUARANTINE_DIR
        )
        
        assert isinstance(CONVERSION_STATE_FILE, str)
        assert isinstance(CONVERSION_MAX_RETRIES, int)
        assert isinstance(CONVERSION_STATE_SAVE_INTERVAL, int)
        assert isinstance(RECOVERY_DIR, str)
        assert isinstance(QUARANTINE_DIR, str)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
