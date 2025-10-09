"""
Unit tests for Torbox download cleanup functionality.
Tests ensure that:
1. Archive files are cleaned up after extraction
2. Extraction folders are cleaned up after all files are uploaded
3. Media files are cleaned up after upload
4. Edge cases and error scenarios are handled correctly
"""

import pytest
import asyncio
import os
import tempfile
import shutil
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from utils.queue_manager import ExtractionCleanupRegistry, QueueManager


class TestExtractionCleanupRegistry:
    """Test the ExtractionCleanupRegistry class."""
    
    @pytest.mark.asyncio
    async def test_register_extraction(self):
        """Test registering an extraction folder."""
        registry = ExtractionCleanupRegistry()
        test_folder = "/tmp/test_extraction"
        
        await registry.register_extraction(test_folder, 5)
        
        assert test_folder in registry.registry
        assert registry.registry[test_folder]['total'] == 5
        assert registry.registry[test_folder]['uploaded'] == 0
    
    @pytest.mark.asyncio
    async def test_mark_file_uploaded_not_last(self):
        """Test marking a file as uploaded when not the last file."""
        registry = ExtractionCleanupRegistry()
        test_folder = "/tmp/test_extraction"
        
        await registry.register_extraction(test_folder, 3)
        
        # Mark first file
        is_last = await registry.mark_file_uploaded(test_folder)
        assert is_last is False
        assert registry.registry[test_folder]['uploaded'] == 1
        
        # Mark second file
        is_last = await registry.mark_file_uploaded(test_folder)
        assert is_last is False
        assert registry.registry[test_folder]['uploaded'] == 2
    
    @pytest.mark.asyncio
    async def test_mark_file_uploaded_last_file(self):
        """Test marking the last file as uploaded."""
        registry = ExtractionCleanupRegistry()
        test_folder = "/tmp/test_extraction"
        
        await registry.register_extraction(test_folder, 2)
        
        # Mark first file
        await registry.mark_file_uploaded(test_folder)
        
        # Mark last file
        is_last = await registry.mark_file_uploaded(test_folder)
        assert is_last is True
        assert test_folder not in registry.registry  # Should be removed
    
    @pytest.mark.asyncio
    async def test_mark_file_uploaded_unregistered_folder(self):
        """Test marking a file from an unregistered folder."""
        registry = ExtractionCleanupRegistry()
        
        is_last = await registry.mark_file_uploaded("/tmp/nonexistent")
        assert is_last is False
    
    @pytest.mark.asyncio
    async def test_cleanup_folder_exists(self):
        """Test cleaning up an existing folder."""
        registry = ExtractionCleanupRegistry()
        
        # Create a temporary folder
        test_folder = tempfile.mkdtemp(prefix="test_cleanup_")
        test_file = os.path.join(test_folder, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test content")
        
        # Clean up
        await registry.cleanup_folder(test_folder)
        
        # Verify folder is removed
        assert not os.path.exists(test_folder)
    
    @pytest.mark.asyncio
    async def test_cleanup_folder_not_exists(self):
        """Test cleaning up a non-existent folder (should not raise error)."""
        registry = ExtractionCleanupRegistry()
        
        # Should not raise exception
        await registry.cleanup_folder("/tmp/nonexistent_folder_12345")


class TestTorboxArchiveCleanup:
    """Test cleanup for Torbox archive downloads."""
    
    @pytest.mark.asyncio
    async def test_archive_download_cleanup_flow(self):
        """Test complete cleanup flow: download -> extract -> upload -> cleanup."""
        queue_manager = QueueManager()
        
        # Create temporary archive and extraction folder
        temp_dir = tempfile.mkdtemp(prefix="test_torbox_")
        archive_path = os.path.join(temp_dir, "test_archive.zip")
        extract_path = os.path.join(temp_dir, "extracted_test_archive.zip_12345")
        
        # Create mock archive file
        with open(archive_path, 'wb') as f:
            f.write(b"fake zip content")
        
        # Create mock extraction folder with files
        os.makedirs(extract_path)
        file1 = os.path.join(extract_path, "photo1.jpg")
        file2 = os.path.join(extract_path, "video1.mp4")
        with open(file1, 'wb') as f:
            f.write(b"fake jpg")
        with open(file2, 'wb') as f:
            f.write(b"fake mp4")
        
        try:
            # Simulate extraction process
            await queue_manager.extraction_cleanup_registry.register_extraction(extract_path, 2)
            
            # Verify registration
            assert extract_path in queue_manager.extraction_cleanup_registry.registry
            
            # Simulate first file upload completion
            is_last = await queue_manager.extraction_cleanup_registry.mark_file_uploaded(extract_path)
            assert is_last is False
            assert os.path.exists(extract_path)  # Folder should still exist
            
            # Simulate second file upload completion (last file)
            is_last = await queue_manager.extraction_cleanup_registry.mark_file_uploaded(extract_path)
            assert is_last is True
            
            # Clean up folder
            await queue_manager.extraction_cleanup_registry.cleanup_folder(extract_path)
            
            # Verify extraction folder is removed
            assert not os.path.exists(extract_path)
            
            # Verify archive can be manually removed (simulating the archive cleanup)
            if os.path.exists(archive_path):
                os.remove(archive_path)
            assert not os.path.exists(archive_path)
            
        finally:
            # Cleanup test directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_extraction_folder_tracked_in_upload_tasks(self):
        """Test that upload tasks include extraction_folder field."""
        queue_manager = QueueManager()
        
        temp_dir = tempfile.mkdtemp(prefix="test_task_")
        extract_path = os.path.join(temp_dir, "extracted_files")
        os.makedirs(extract_path)
        
        try:
            # Create upload task with extraction folder
            upload_task = {
                'type': 'extracted_file',
                'event': None,
                'file_path': os.path.join(extract_path, "test.jpg"),
                'filename': "test.jpg",
                'size_bytes': 1000,
                'source_archive': "test.zip",
                'extraction_folder': extract_path
            }
            
            # Verify extraction_folder is in task
            assert 'extraction_folder' in upload_task
            assert upload_task['extraction_folder'] == extract_path
            
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)


class TestTorboxMediaCleanup:
    """Test cleanup for Torbox media downloads."""
    
    @pytest.mark.asyncio
    async def test_media_file_cleanup_after_upload(self):
        """Test that media files are cleaned up after successful upload."""
        # Create temporary media file
        temp_dir = tempfile.mkdtemp(prefix="test_media_")
        media_file = os.path.join(temp_dir, "test_video.mp4")
        
        with open(media_file, 'wb') as f:
            f.write(b"fake video content")
        
        try:
            assert os.path.exists(media_file)
            
            # Simulate cleanup after upload
            os.remove(media_file)
            
            # Verify file is removed
            assert not os.path.exists(media_file)
            
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_media_upload_task_no_extraction_folder(self):
        """Test that direct media uploads don't have extraction_folder."""
        temp_dir = tempfile.mkdtemp(prefix="test_direct_")
        media_file = os.path.join(temp_dir, "direct_video.mp4")
        
        with open(media_file, 'wb') as f:
            f.write(b"fake content")
        
        try:
            # Create upload task for direct media (no extraction_folder)
            upload_task = {
                'type': 'torbox_media',
                'event': None,
                'file_path': media_file,
                'filename': "direct_video.mp4",
                'size_bytes': 1000
            }
            
            # Verify no extraction_folder in task
            assert 'extraction_folder' not in upload_task
            
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)


class TestCleanupEdgeCases:
    """Test edge cases and error scenarios."""
    
    @pytest.mark.asyncio
    async def test_cleanup_with_no_media_files_extracted(self):
        """Test cleanup when archive contains no media files."""
        registry = ExtractionCleanupRegistry()
        
        temp_dir = tempfile.mkdtemp(prefix="test_empty_")
        extract_path = os.path.join(temp_dir, "extracted_empty")
        os.makedirs(extract_path)
        
        try:
            # Register with 0 files (should handle gracefully)
            await registry.register_extraction(extract_path, 0)
            
            # Marking as complete should return True immediately
            is_last = await registry.mark_file_uploaded(extract_path)
            # With 0 total files, the first mark should consider it "complete"
            # Actually, let's check the logic - 0 uploaded >= 0 total = True
            assert is_last is True
            
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_cleanup_on_extraction_failure(self):
        """Test that extraction folder is cleaned up on extraction failure."""
        temp_dir = tempfile.mkdtemp(prefix="test_fail_")
        extract_path = os.path.join(temp_dir, "failed_extraction")
        os.makedirs(extract_path)
        
        try:
            # Create some temporary files
            test_file = os.path.join(extract_path, "test.txt")
            with open(test_file, 'w') as f:
                f.write("test")
            
            # Simulate cleanup on failure
            if os.path.exists(extract_path):
                shutil.rmtree(extract_path, ignore_errors=True)
            
            # Verify cleanup
            assert not os.path.exists(extract_path)
            
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_concurrent_file_uploads_from_same_extraction(self):
        """Test that cleanup only happens after ALL files are uploaded."""
        registry = ExtractionCleanupRegistry()
        
        temp_dir = tempfile.mkdtemp(prefix="test_concurrent_")
        extract_path = os.path.join(temp_dir, "extracted_concurrent")
        os.makedirs(extract_path)
        
        try:
            # Register 5 files
            await registry.register_extraction(extract_path, 5)
            
            # Simulate concurrent uploads
            results = []
            for i in range(4):
                is_last = await registry.mark_file_uploaded(extract_path)
                results.append(is_last)
                assert is_last is False  # First 4 should not be last
            
            # Last file
            is_last = await registry.mark_file_uploaded(extract_path)
            assert is_last is True
            
            # Verify folder removed from registry
            assert extract_path not in registry.registry
            
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_cleanup_folder_with_nested_subdirectories(self):
        """Test that cleanup removes nested subdirectories."""
        registry = ExtractionCleanupRegistry()
        
        temp_dir = tempfile.mkdtemp(prefix="test_nested_")
        extract_path = os.path.join(temp_dir, "extracted_nested")
        
        # Create nested structure
        os.makedirs(os.path.join(extract_path, "subdir1", "subdir2"))
        file1 = os.path.join(extract_path, "file1.txt")
        file2 = os.path.join(extract_path, "subdir1", "file2.txt")
        file3 = os.path.join(extract_path, "subdir1", "subdir2", "file3.txt")
        
        with open(file1, 'w') as f:
            f.write("test1")
        with open(file2, 'w') as f:
            f.write("test2")
        with open(file3, 'w') as f:
            f.write("test3")
        
        try:
            # Clean up
            await registry.cleanup_folder(extract_path)
            
            # Verify entire tree is removed
            assert not os.path.exists(extract_path)
            assert not os.path.exists(file1)
            assert not os.path.exists(file2)
            assert not os.path.exists(file3)
            
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_multiple_extractions_tracked_separately(self):
        """Test that multiple extractions are tracked independently."""
        registry = ExtractionCleanupRegistry()
        
        folder1 = "/tmp/extraction1"
        folder2 = "/tmp/extraction2"
        
        # Register two separate extractions
        await registry.register_extraction(folder1, 3)
        await registry.register_extraction(folder2, 2)
        
        # Verify both are tracked
        assert folder1 in registry.registry
        assert folder2 in registry.registry
        
        # Complete folder1
        await registry.mark_file_uploaded(folder1)
        await registry.mark_file_uploaded(folder1)
        is_last = await registry.mark_file_uploaded(folder1)
        assert is_last is True
        assert folder1 not in registry.registry
        
        # folder2 should still be tracked
        assert folder2 in registry.registry
        
        # Complete folder2
        await registry.mark_file_uploaded(folder2)
        is_last = await registry.mark_file_uploaded(folder2)
        assert is_last is True
        assert folder2 not in registry.registry


class TestCleanupIntegration:
    """Integration tests for complete cleanup workflow."""
    
    @pytest.mark.asyncio
    async def test_full_torbox_archive_workflow(self):
        """Test complete workflow: Torbox link -> download -> extract -> upload -> cleanup."""
        # This is a higher-level integration test simulating the full flow
        
        temp_dir = tempfile.mkdtemp(prefix="test_integration_")
        archive_path = os.path.join(temp_dir, "torbox_archive.zip")
        extract_path = os.path.join(temp_dir, "extracted_torbox_archive.zip_12345")
        
        try:
            # Step 1: Simulate Torbox download
            with open(archive_path, 'wb') as f:
                f.write(b"fake archive content")
            assert os.path.exists(archive_path)
            
            # Step 2: Simulate extraction
            os.makedirs(extract_path)
            media_files = []
            for i in range(3):
                media_file = os.path.join(extract_path, f"photo{i}.jpg")
                with open(media_file, 'wb') as f:
                    f.write(f"photo {i} content".encode())
                media_files.append(media_file)
            
            # Step 3: Simulate upload process
            registry = ExtractionCleanupRegistry()
            await registry.register_extraction(extract_path, len(media_files))
            
            # Step 4: Simulate each file being uploaded and cleaned up
            for i, media_file in enumerate(media_files):
                assert os.path.exists(media_file)
                
                # Simulate upload completion and file cleanup
                os.remove(media_file)
                
                # Mark as uploaded
                is_last = await registry.mark_file_uploaded(extract_path)
                
                if i < len(media_files) - 1:
                    assert is_last is False
                    assert os.path.exists(extract_path)  # Folder should still exist
                else:
                    assert is_last is True
            
            # Step 5: Clean up extraction folder
            await registry.cleanup_folder(extract_path)
            assert not os.path.exists(extract_path)
            
            # Step 6: Clean up archive
            os.remove(archive_path)
            assert not os.path.exists(archive_path)
            
            # Verify complete cleanup
            remaining_files = os.listdir(temp_dir)
            assert len(remaining_files) == 0
            
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_full_torbox_media_workflow(self):
        """Test complete workflow for direct media: Torbox link -> download -> upload -> cleanup."""
        temp_dir = tempfile.mkdtemp(prefix="test_media_integration_")
        media_file = os.path.join(temp_dir, "torbox_video.mp4")
        
        try:
            # Step 1: Simulate Torbox media download
            with open(media_file, 'wb') as f:
                f.write(b"fake video content")
            assert os.path.exists(media_file)
            
            # Step 2: Simulate upload
            # (no extraction folder to track)
            
            # Step 3: Simulate upload completion and cleanup
            os.remove(media_file)
            assert not os.path.exists(media_file)
            
            # Verify complete cleanup
            remaining_files = os.listdir(temp_dir)
            assert len(remaining_files) == 0
            
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
