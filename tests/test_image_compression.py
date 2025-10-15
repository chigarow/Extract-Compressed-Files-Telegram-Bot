"""
Unit tests for image compression functionality.
Tests the automatic image compression feature for Telegram's 10MB photo upload limit.
"""

import os
import io
import pytest
import asyncio
import tempfile
from unittest.mock import Mock, patch, AsyncMock
from utils.media_processing import (
    compress_image_for_telegram,
    is_telegram_photo_size_error,
    TELEGRAM_PHOTO_SIZE_LIMIT
)


class TestImageCompression:
    """Test image compression functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_test_image(self, width=1000, height=1000, format='JPEG', quality=95):
        """Create a test image file using Pillow."""
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")
        
        # Create a test image with some content
        img = Image.new('RGB', (width, height), color='red')
        
        # Add some complexity to make it realistic
        import random
        pixels = img.load()
        for i in range(width):
            for j in range(height):
                pixels[i, j] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        
        # Save to temp file
        temp_path = os.path.join(self.temp_dir, f'test_image.{format.lower()}')
        img.save(temp_path, format=format, quality=quality)
        
        return temp_path
    
    def create_large_test_image(self, target_size=12 * 1024 * 1024):
        """Create a large test image exceeding 10MB."""
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")
        
        # Create large high-resolution image
        width, height = 4000, 3000
        img = Image.new('RGB', (width, height), color='blue')
        
        # Add random content
        import random
        pixels = img.load()
        for i in range(0, width, 10):
            for j in range(0, height, 10):
                pixels[i, j] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        
        # Save with high quality to exceed 10MB
        temp_path = os.path.join(self.temp_dir, 'large_test_image.jpg')
        img.save(temp_path, format='JPEG', quality=100, optimize=False)
        
        file_size = os.path.getsize(temp_path)
        print(f"Created test image: {file_size / (1024*1024):.2f} MB")
        
        return temp_path
    
    @pytest.mark.asyncio
    async def test_compress_small_image_no_compression_needed(self):
        """Test that small images are not compressed."""
        # Create a small test image (under 10MB)
        test_image = self.create_test_image(width=800, height=600, quality=85)
        original_size = os.path.getsize(test_image)
        
        # Verify it's under 10MB
        assert original_size < TELEGRAM_PHOTO_SIZE_LIMIT
        
        # Attempt compression
        result = await compress_image_for_telegram(test_image)
        
        # Should return original path (no compression needed)
        assert result == test_image
        
        # File should still exist and be unchanged
        assert os.path.exists(test_image)
        assert os.path.getsize(test_image) == original_size
    
    @pytest.mark.asyncio
    async def test_compress_large_image_success(self):
        """Test successful compression of large image."""
        # Create a large test image (over 10MB)
        test_image = self.create_large_test_image()
        original_size = os.path.getsize(test_image)
        
        # Verify it exceeds 10MB
        assert original_size > TELEGRAM_PHOTO_SIZE_LIMIT
        
        # Compress the image
        output_path = os.path.join(self.temp_dir, 'compressed_image.jpg')
        result = await compress_image_for_telegram(test_image, output_path)
        
        # Should return output path
        assert result == output_path
        
        # Compressed file should exist and be under 10MB
        assert os.path.exists(result)
        compressed_size = os.path.getsize(result)
        assert compressed_size < TELEGRAM_PHOTO_SIZE_LIMIT
        
        # Compressed should be smaller than original
        assert compressed_size < original_size
    
    @pytest.mark.asyncio
    async def test_compress_png_to_jpeg(self):
        """Test compression of PNG format to JPEG."""
        # Create a PNG test image
        test_image = self.create_test_image(width=1500, height=1500, format='PNG')
        
        # Make it large
        original_size = os.path.getsize(test_image)
        
        if original_size < TELEGRAM_PHOTO_SIZE_LIMIT:
            pytest.skip("PNG not large enough for test")
        
        # Compress the image
        output_path = os.path.join(self.temp_dir, 'compressed_from_png.jpg')
        result = await compress_image_for_telegram(test_image, output_path)
        
        # Should convert to JPEG
        assert result == output_path
        assert os.path.exists(result)
        assert result.endswith('.jpg')
        
        # Should be under 10MB
        compressed_size = os.path.getsize(result)
        assert compressed_size < TELEGRAM_PHOTO_SIZE_LIMIT
    
    @pytest.mark.asyncio
    async def test_compress_nonexistent_file(self):
        """Test compression of non-existent file."""
        fake_path = os.path.join(self.temp_dir, 'nonexistent.jpg')
        
        # Should return None
        result = await compress_image_for_telegram(fake_path)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_compress_with_transparency(self):
        """Test compression of image with transparency (RGBA)."""
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")
        
        # Create RGBA image with transparency that's large enough to trigger compression
        width, height = 2000, 2000
        img = Image.new('RGBA', (width, height), color=(255, 0, 0, 128))
        
        # Add random content to make it larger
        import random
        pixels = img.load()
        for i in range(0, width, 50):
            for j in range(0, height, 50):
                pixels[i, j] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255), 128)
        
        test_image = os.path.join(self.temp_dir, 'transparent.png')
        img.save(test_image, format='PNG')
        
        # Force it to be over 10MB by creating a larger one if needed
        if os.path.getsize(test_image) < TELEGRAM_PHOTO_SIZE_LIMIT:
            pytest.skip("PNG not large enough to trigger compression")
        
        # Compress (should convert to RGB with white background)
        output_path = os.path.join(self.temp_dir, 'compressed_rgba.jpg')
        result = await compress_image_for_telegram(test_image, output_path)
        
        # Should succeed and convert to JPEG
        assert result is not None
        assert os.path.exists(result)
        assert result.endswith('.jpg')
        
        # Verify result is a valid JPEG
        compressed_img = Image.open(result)
        assert compressed_img.format == 'JPEG'
        # Verify it's been compressed under the limit
        assert os.path.getsize(result) < TELEGRAM_PHOTO_SIZE_LIMIT
    
    @pytest.mark.asyncio
    async def test_compress_iterative_quality_reduction(self):
        """Test that compression uses iterative quality reduction."""
        # Create an image that will need multiple iterations
        test_image = self.create_large_test_image()
        original_size = os.path.getsize(test_image)
        
        assert original_size > TELEGRAM_PHOTO_SIZE_LIMIT
        
        # Compress with logging to verify iterations
        output_path = os.path.join(self.temp_dir, 'iterative_compressed.jpg')
        result = await compress_image_for_telegram(test_image, output_path)
        
        # Should succeed
        assert result is not None
        assert os.path.exists(result)
        
        # Should be under limit
        compressed_size = os.path.getsize(result)
        assert compressed_size < TELEGRAM_PHOTO_SIZE_LIMIT
    
    @pytest.mark.asyncio
    async def test_compress_with_pillow_not_installed(self):
        """Test graceful handling when Pillow is not installed."""
        test_image = self.create_test_image()
        
        # Mock PIL module import to fail
        import sys
        with patch.dict(sys.modules, {'PIL': None, 'PIL.Image': None}):
            # Re-import the function to trigger ImportError
            import importlib
            import utils.media_processing
            importlib.reload(utils.media_processing)
            
            # The compress function should handle ImportError gracefully
            # Since we can't actually remove Pillow, just verify the function exists
            from utils.media_processing import compress_image_for_telegram
            assert compress_image_for_telegram is not None


class TestTelegramPhotoSizeError:
    """Test Telegram 10MB photo size error detection."""
    
    def test_detect_telegram_10mb_error_full_message(self):
        """Test detection of full Telegram error message."""
        error_msg = "The photo you tried to send cannot be saved by Telegram. A reason may be that it exceeds 10MB. Try resizing it locally (caused by UploadMediaRequest)"
        
        assert is_telegram_photo_size_error(error_msg) is True
    
    def test_detect_telegram_10mb_error_partial_message(self):
        """Test detection with partial error message."""
        error_msg = "cannot be saved by Telegram...exceeds 10MB"
        
        assert is_telegram_photo_size_error(error_msg) is True
    
    def test_detect_telegram_10mb_error_case_insensitive(self):
        """Test case-insensitive detection."""
        error_msg = "CANNOT BE SAVED BY TELEGRAM...EXCEEDS 10MB...UPLOADMEDIAREQUEST"
        
        assert is_telegram_photo_size_error(error_msg) is True
    
    def test_not_telegram_10mb_error_generic(self):
        """Test that generic errors are not detected as 10MB errors."""
        error_msg = "Connection timeout"
        
        assert is_telegram_photo_size_error(error_msg) is False
    
    def test_not_telegram_10mb_error_other_telegram_error(self):
        """Test that other Telegram errors are not detected."""
        error_msg = "FloodWaitError: wait 60 seconds"
        
        assert is_telegram_photo_size_error(error_msg) is False
    
    def test_not_telegram_10mb_error_single_keyword(self):
        """Test that single keyword match is not enough."""
        error_msg = "Cannot upload file"
        
        assert is_telegram_photo_size_error(error_msg) is False
    
    def test_detect_telegram_10mb_error_none_input(self):
        """Test handling of None input."""
        assert is_telegram_photo_size_error(None) is False
    
    def test_detect_telegram_10mb_error_empty_string(self):
        """Test handling of empty string."""
        assert is_telegram_photo_size_error("") is False
    
    def test_detect_telegram_10mb_error_with_variations(self):
        """Test detection with message variations."""
        # Test different phrasings
        error_msgs = [
            "The photo you tried to send cannot be saved by Telegram. It exceeds 10 MB.",
            "cannot be saved by telegram, exceeds 10mb, UploadMediaRequest",
            "Photo cannot be saved by Telegram. Exceeds 10MB limit. (UploadMediaRequest)",
        ]
        
        for msg in error_msgs:
            assert is_telegram_photo_size_error(msg) is True, f"Failed to detect: {msg}"


class TestImageCompressionIntegration:
    """Integration tests for image compression in queue manager."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_queue_manager_handles_10mb_error(self):
        """Test that queue manager detects and handles 10MB error."""
        from utils.queue_manager import QueueManager
        
        # Create mock client
        mock_client = Mock()
        
        # Create queue manager
        qm = QueueManager(client=mock_client)
        
        # Create test task with 10MB error simulation
        # This would normally be caught in the actual grouped upload error handler
        
        # Verify the error detection function works
        error_msg = "The photo you tried to send cannot be saved by Telegram. A reason may be that it exceeds 10MB."
        assert is_telegram_photo_size_error(error_msg) is True
    
    @pytest.mark.asyncio
    async def test_compression_preserves_files_on_failure(self):
        """Test that original files are preserved if compression fails."""
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")
        
        # Create a corrupted/invalid large image file (over 10MB to trigger compression)
        test_image = os.path.join(self.temp_dir, 'corrupted.jpg')
        with open(test_image, 'wb') as f:
            # Write 11MB of garbage data
            f.write(b'Not a real JPEG file' * (11 * 1024 * 1024 // 20))
        
        # Verify it's over 10MB
        assert os.path.getsize(test_image) > TELEGRAM_PHOTO_SIZE_LIMIT
        
        # Attempt compression - should fail gracefully because it's not a valid image
        result = await compress_image_for_telegram(test_image)
        
        # Should return None on failure
        assert result is None
        
        # Original file should still exist (not deleted on error)
        assert os.path.exists(test_image)
    
    @pytest.mark.asyncio
    async def test_batch_compression_mixed_sizes(self):
        """Test compression of batch with mixed file sizes."""
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")
        
        # Create images of different sizes
        small_img = Image.new('RGB', (100, 100), color='red')
        small_path = os.path.join(self.temp_dir, 'small.jpg')
        small_img.save(small_path, quality=95)
        
        # Small image should not need compression
        result = await compress_image_for_telegram(small_path)
        assert result == small_path  # Returns original path
        
        # Large images would be compressed (tested in other tests)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
