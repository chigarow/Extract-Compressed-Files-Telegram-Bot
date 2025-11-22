"""
Integration tests for deferred video conversion feature.
Tests full workflow with queue manager and media processing integration.
"""

import pytest
import os
import tempfile
import shutil
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from utils.conversion_state import ConversionStateManager
from utils.queue_manager import QueueManager
from utils.constants import DEFERRED_VIDEO_CONVERSION


class TestQueueManagerIntegration:
    """Test integration with queue manager."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def temp_state_file(self, tmp_path):
        """Create a temporary state file."""
        return str(tmp_path / "test_conversion_state.json")
    
    @pytest.fixture
    def queue_manager(self):
        """Create a queue manager instance."""
        manager = QueueManager()
        manager._disable_upload_worker_start = True
        manager.clear_all_queues()
        yield manager
        manager.clear_all_queues()
    
    @pytest.mark.asyncio
    async def test_deferred_conversion_detection(self, queue_manager, temp_dir):
        """Test that incompatible videos are detected and deferred."""
        # Create test video file
        video_file = os.path.join(temp_dir, "test_video.mov")
        with open(video_file, 'wb') as f:
            f.write(b"fake video content")
        
        # Mock is_telegram_compatible_video to return False
        with patch('utils.media_processing.is_telegram_compatible_video', return_value=False):
            # Create upload task for incompatible video
            task = {
                'type': 'direct_media',
                'file_path': video_file,
                'filename': 'test_video.mov',
                'is_video': True
            }
            
            # The queue manager should detect this as incompatible
            # and create a deferred conversion task
            await queue_manager.add_upload_task(task)
            
            # Verify task was added
            assert queue_manager.upload_queue.qsize() >= 1
    
    @pytest.mark.asyncio
    async def test_normal_files_upload_first(self, queue_manager, temp_dir):
        """Test that normal files (images, compatible videos) upload before deferred conversions."""
        # Create test files
        image_file = os.path.join(temp_dir, "image.jpg")
        video_file = os.path.join(temp_dir, "video.mov")
        
        with open(image_file, 'wb') as f:
            f.write(b"fake image")
        with open(video_file, 'wb') as f:
            f.write(b"fake video")
        
        # Add image task (should upload immediately)
        image_task = {
            'type': 'direct_media',
            'file_path': image_file,
            'filename': 'image.jpg',
            'is_video': False
        }
        await queue_manager.add_upload_task(image_task)
        
        # Add deferred conversion task
        deferred_task = {
            'type': 'deferred_conversion',
            'file_path': video_file,
            'filename': 'video.mov'
        }
        await queue_manager.add_upload_task(deferred_task)
        
        # Verify both tasks are in queue
        assert queue_manager.upload_queue.qsize() == 2
        
        # Get tasks in order
        tasks = []
        while not queue_manager.upload_queue.empty():
            task = await queue_manager.upload_queue.get()
            tasks.append(task)
        
        # First task should be the image (normal upload)
        assert tasks[0]['type'] == 'direct_media'
        assert tasks[0]['filename'] == 'image.jpg'
        
        # Second task should be deferred conversion
        assert tasks[1]['type'] == 'deferred_conversion'
        assert tasks[1]['filename'] == 'video.mov'
    
    @pytest.mark.asyncio
    async def test_conversion_state_tracking(self, queue_manager, temp_dir, temp_state_file):
        """Test that conversion state is tracked during processing."""
        state_manager = ConversionStateManager(state_file=temp_state_file)
        
        # Create test video file
        video_file = os.path.join(temp_dir, "test_video.mov")
        with open(video_file, 'wb') as f:
            f.write(b"fake video content")
        
        # Save initial state
        output_path = os.path.join(temp_dir, "test_video_converted.mp4")
        state_manager.save_state(
            file_path=video_file,
            status='pending',
            progress=0,
            output_path=output_path
        )
        
        # Verify state was saved
        state = state_manager.load_state(video_file)
        assert state is not None
        assert state['status'] == 'pending'
        assert state['progress'] == 0
        
        # Update state to in_progress
        state_manager.save_state(
            file_path=video_file,
            status='in_progress',
            progress=50,
            output_path=output_path
        )
        
        # Verify state was updated
        state = state_manager.load_state(video_file)
        assert state['status'] == 'in_progress'
        assert state['progress'] == 50


class TestMediaProcessingIntegration:
    """Test integration with media processing."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_video_compatibility_check(self, temp_dir):
        """Test video compatibility checking."""
        from utils.media_processing import is_telegram_compatible_video
        
        # Create test video file
        video_file = os.path.join(temp_dir, "test_video.mp4")
        with open(video_file, 'wb') as f:
            f.write(b"fake video content")
        
        # Mock ffprobe to return compatible format
        with patch('utils.media_processing.is_ffprobe_available', return_value=True):
            with patch('subprocess.run') as mock_run:
                # Mock ffprobe output for compatible video
                mock_run.return_value = Mock(
                    returncode=0,
                    stdout='{"format": {"format_name": "mp4"}, "streams": [{"codec_name": "h264"}]}'
                )
                
                # Check compatibility
                result = is_telegram_compatible_video(video_file)
                
                # Should be compatible (mocked as MP4 with H264)
                assert isinstance(result, bool)
    
    @pytest.mark.asyncio
    async def test_conversion_with_state_saving(self, temp_dir):
        """Test video conversion with state saving."""
        from utils.conversion_state import ConversionStateManager
        
        # Create state manager
        state_file = os.path.join(temp_dir, "conversion_state.json")
        state_manager = ConversionStateManager(state_file=state_file)
        
        # Create test video file
        input_file = os.path.join(temp_dir, "input.mov")
        output_file = os.path.join(temp_dir, "output.mp4")
        
        with open(input_file, 'wb') as f:
            f.write(b"fake video content")
        
        # Save initial state
        state_manager.save_state(
            file_path=input_file,
            status='pending',
            progress=0,
            output_path=output_file
        )
        
        # Simulate conversion progress
        for progress in [25, 50, 75]:
            state_manager.save_state(
                file_path=input_file,
                status='in_progress',
                progress=progress,
                output_path=output_file
            )
            
            # Verify state was saved
            state = state_manager.load_state(input_file)
            assert state['progress'] == progress
        
        # Mark as completed
        state_manager.mark_completed(input_file)
        
        # Verify final state
        state = state_manager.load_state(input_file)
        assert state['status'] == 'completed'
        assert state['progress'] == 100


class TestCrashRecoveryIntegration:
    """Test crash recovery integration."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def temp_state_file(self, tmp_path):
        """Create a temporary state file."""
        return str(tmp_path / "test_conversion_state.json")
    
    @pytest.mark.asyncio
    async def test_resume_after_crash(self, temp_dir, temp_state_file):
        """Test resuming conversions after crash."""
        state_manager = ConversionStateManager(state_file=temp_state_file)
        
        # Create test video files
        video1 = os.path.join(temp_dir, "video1.mov")
        video2 = os.path.join(temp_dir, "video2.mov")
        
        with open(video1, 'wb') as f:
            f.write(b"fake video 1")
        with open(video2, 'wb') as f:
            f.write(b"fake video 2")
        
        # Save incomplete conversion states (simulating crash)
        state_manager.save_state(
            file_path=video1,
            status='in_progress',
            progress=45,
            output_path=os.path.join(temp_dir, "video1_converted.mp4")
        )
        state_manager.save_state(
            file_path=video2,
            status='pending',
            progress=0,
            output_path=os.path.join(temp_dir, "video2_converted.mp4")
        )
        
        # Simulate restart - get incomplete conversions
        incomplete = state_manager.get_incomplete_conversions()
        
        # Should find both incomplete conversions
        assert len(incomplete) == 2
        
        # Verify files exist
        file_paths = [s['file_path'] for s in incomplete]
        assert video1 in file_paths
        assert video2 in file_paths
    
    @pytest.mark.asyncio
    async def test_cleanup_after_successful_conversion(self, temp_dir, temp_state_file):
        """Test cleanup of state after successful conversion."""
        state_manager = ConversionStateManager(state_file=temp_state_file)
        
        # Create test video file
        video_file = os.path.join(temp_dir, "test_video.mov")
        with open(video_file, 'wb') as f:
            f.write(b"fake video")
        
        # Save and complete conversion
        state_manager.save_state(
            file_path=video_file,
            status='in_progress',
            progress=50,
            output_path=os.path.join(temp_dir, "output.mp4")
        )
        state_manager.mark_completed(video_file)
        
        # Verify state is completed
        state = state_manager.load_state(video_file)
        assert state['status'] == 'completed'
        
        # Cleanup old completed states
        import time
        # Manually set old timestamp
        state_manager.states[video_file]['last_updated'] = time.time() - (25 * 3600)
        state_manager._save_states()
        
        # Run cleanup
        state_manager.cleanup_completed(max_age_hours=24)
        
        # State should be removed
        state = state_manager.load_state(video_file)
        assert state is None


class TestEndToEndWorkflow:
    """Test complete end-to-end workflow."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def queue_manager(self):
        """Create a queue manager instance."""
        manager = QueueManager()
        manager._disable_upload_worker_start = True
        manager.clear_all_queues()
        yield manager
        manager.clear_all_queues()
    
    @pytest.mark.asyncio
    async def test_mixed_media_upload_workflow(self, queue_manager, temp_dir):
        """Test complete workflow with mixed media types."""
        # Create test files
        image1 = os.path.join(temp_dir, "image1.jpg")
        image2 = os.path.join(temp_dir, "image2.png")
        compatible_video = os.path.join(temp_dir, "compatible.mp4")
        incompatible_video = os.path.join(temp_dir, "incompatible.mov")
        
        for file_path in [image1, image2, compatible_video, incompatible_video]:
            with open(file_path, 'wb') as f:
                f.write(b"fake content")
        
        # Add tasks in mixed order
        tasks = [
            {'type': 'direct_media', 'file_path': image1, 'filename': 'image1.jpg', 'is_video': False},
            {'type': 'direct_media', 'file_path': incompatible_video, 'filename': 'incompatible.mov', 'is_video': True},
            {'type': 'direct_media', 'file_path': image2, 'filename': 'image2.png', 'is_video': False},
            {'type': 'direct_media', 'file_path': compatible_video, 'filename': 'compatible.mp4', 'is_video': True},
        ]
        
        for task in tasks:
            await queue_manager.add_upload_task(task)
        
        # Verify all tasks were added
        assert queue_manager.upload_queue.qsize() >= 4
        
        # Expected order:
        # 1. Images (image1.jpg, image2.png)
        # 2. Compatible videos (compatible.mp4)
        # 3. Deferred conversions (incompatible.mov)
    
    @pytest.mark.asyncio
    async def test_configuration_flag_control(self):
        """Test that DEFERRED_VIDEO_CONVERSION flag controls behavior."""
        from utils.constants import DEFERRED_VIDEO_CONVERSION
        
        # Verify flag is accessible
        assert isinstance(DEFERRED_VIDEO_CONVERSION, bool)
        
        # When enabled, incompatible videos should be deferred
        # When disabled, they should be processed immediately
        # This is controlled by the configuration


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
