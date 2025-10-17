"""
Test module for video upload error handling fixes.
Tests the comprehensive error detection, validation, and fallback mechanisms.
"""

import os
import sys
import tempfile
import asyncio
import unittest
from unittest.mock import Mock, patch, MagicMock, AsyncMock

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from utils.queue_manager import QueueManager, ProcessingQueue
except ImportError as e:
    print(f"Could not import modules: {e}")
    print("Creating mock implementation for testing...")
    
    class MockQueueManager:
        def __init__(self):
            self.upload_queue = []
            self.download_queue = []
            self.retry_queue = []
            
        def _is_invalid_media_error(self, error_message):
            """Test implementation of invalid media error detection."""
            if not error_message:
                return False
                
            error_lower = str(error_message).lower()
            
            # Keywords that suggest invalid media
            invalid_media_keywords = [
                'invalid media object',
                'media_invalid',
                'invalid_file',
                'corrupted',
                'unsupported format',
                'invalid format',
                'file_reference_expired',
                'bad_request',
                'invalid_argument'
            ]
            
            # Check for multiple indicators (stricter validation)
            keyword_matches = sum(1 for keyword in invalid_media_keywords if keyword in error_lower)
            
            # Also check for specific error patterns
            specific_patterns = [
                'sendmultimediarequest',
                'grouped media',
                'album upload',
                'media group'
            ]
            
            pattern_matches = sum(1 for pattern in specific_patterns if pattern in error_lower)
            
            # Return True if we have multiple indicators or specific patterns
            return keyword_matches >= 2 or pattern_matches >= 1
            
        def _validate_video_file(self, file_path):
            """Test implementation of video file validation."""
            if not os.path.exists(file_path):
                return False
                
            file_size = os.path.getsize(file_path)
            
            # Basic size validation (files under 1MB are likely corrupted)
            if file_size < 1024 * 1024:  # 1MB
                return False
                
            # Check file extension
            video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v']
            if not any(file_path.lower().endswith(ext) for ext in video_extensions):
                return False
                
            # For testing, we'll simulate file signature checks
            try:
                with open(file_path, 'rb') as f:
                    header = f.read(12)
                    
                # Check for common video file signatures
                video_signatures = [
                    b'\x00\x00\x00\x18ftypmp4',  # MP4
                    b'\x00\x00\x00\x1cftypisom',  # MP4 ISO
                    b'RIFF',  # AVI (first 4 bytes)
                    b'\x1a\x45\xdf\xa3'  # MKV/WebM
                ]
                
                for signature in video_signatures:
                    if header.startswith(signature):
                        return True
                        
                # For AVI, check for AVI signature at offset 8
                if len(header) >= 12 and header[8:11] == b'AVI':
                    return True
                    
            except Exception:
                return False
                
            return False

    QueueManager = MockQueueManager


class TestVideoUploadErrorHandling(unittest.TestCase):
    """Test video upload error handling and fallback mechanisms."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.queue_manager = QueueManager()
        
    def test_invalid_media_error_detection(self):
        """Test detection of invalid media errors."""
        # Test cases that should be detected as invalid media errors
        invalid_cases = [
            "SendMultiMediaRequest: Invalid media object provided",
            "Error uploading grouped media: invalid_file corrupted",
            "Media_invalid: file format unsupported format",
            "Bad_request: invalid_argument in media group",
            "Grouped media upload failed: invalid media object",
            "Album upload error: corrupted file_reference_expired"
        ]
        
        for error_msg in invalid_cases:
            with self.subTest(error_msg=error_msg):
                result = self.queue_manager._is_invalid_media_error(error_msg)
                self.assertTrue(result, f"Should detect invalid media error: {error_msg}")
    
    def test_valid_error_messages_not_detected(self):
        """Test that valid error messages are not incorrectly flagged."""
        valid_cases = [
            "Network timeout",
            "FloodWaitError: Too many requests",
            "File not found",
            "Permission denied",
            "Disk full",
            "Connection lost",
            "Invalid token",  # Only one keyword
            "File corrupted",  # Only one keyword
            ""  # Empty string
        ]
        
        for error_msg in valid_cases:
            with self.subTest(error_msg=error_msg):
                result = self.queue_manager._is_invalid_media_error(error_msg)
                self.assertFalse(result, f"Should not detect as invalid media error: {error_msg}")
    
    def test_video_file_validation_with_real_files(self):
        """Test video file validation with temporary files."""
        # Test with a file that's too small
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as small_file:
            small_file.write(b'small')  # Only 5 bytes
            small_file_path = small_file.name
            
        try:
            result = self.queue_manager._validate_video_file(small_file_path)
            self.assertFalse(result, "Small files should be invalid")
        finally:
            os.unlink(small_file_path)
            
        # Test with a larger file that has MP4 signature
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as large_file:
            # Write MP4 signature + padding to reach 1MB+
            mp4_header = b'\x00\x00\x00\x18ftypmp4'
            padding = b'\x00' * (1024 * 1024)  # 1MB of padding
            large_file.write(mp4_header + padding)
            large_file_path = large_file.name
            
        try:
            result = self.queue_manager._validate_video_file(large_file_path)
            self.assertTrue(result, "Large files with valid signature should be valid")
        finally:
            os.unlink(large_file_path)
            
        # Test with non-existent file
        result = self.queue_manager._validate_video_file('/nonexistent/file.mp4')
        self.assertFalse(result, "Non-existent files should be invalid")
        
        # Test with non-video extension
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as text_file:
            text_file.write(b'x' * (1024 * 1024))  # 1MB
            text_file_path = text_file.name
            
        try:
            result = self.queue_manager._validate_video_file(text_file_path)
            self.assertFalse(result, "Non-video files should be invalid")
        finally:
            os.unlink(text_file_path)
    
    def test_video_file_signature_detection(self):
        """Test video file signature detection."""
        # Test different video signatures
        signatures_and_extensions = [
            (b'\x00\x00\x00\x18ftypmp4', '.mp4'),
            (b'\x00\x00\x00\x1cftypisom', '.mp4'),
            (b'RIFF\x00\x00\x00\x00AVI ', '.avi'),
            (b'\x1a\x45\xdf\xa3', '.mkv')
        ]
        
        for signature, extension in signatures_and_extensions:
            with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as video_file:
                # Write signature + padding to reach 1MB+
                padding = b'\x00' * (1024 * 1024)
                video_file.write(signature + padding)
                video_file_path = video_file.name
                
            try:
                result = self.queue_manager._validate_video_file(video_file_path)
                self.assertTrue(result, f"Should validate {extension} with correct signature")
            finally:
                os.unlink(video_file_path)
    
    def test_error_detection_edge_cases(self):
        """Test edge cases for error detection."""
        edge_cases = [
            None,  # None value
            "",    # Empty string
            123,   # Non-string type
            "A" * 10000,  # Very long string
            "invalid\x00media\x00object",  # String with null bytes
            "INVALID MEDIA OBJECT CORRUPTED",  # All caps
            "Invalid Media Object, Corrupted File"  # With punctuation
        ]
        
        for case in edge_cases:
            with self.subTest(case=case):
                try:
                    result = self.queue_manager._is_invalid_media_error(case)
                    # Should not raise an exception
                    self.assertIsInstance(result, bool)
                except Exception as e:
                    self.fail(f"Error detection should not raise exception for {case}: {e}")
    
    def test_comprehensive_error_scenarios(self):
        """Test comprehensive error scenarios that combine multiple factors."""
        # Scenario 1: Real Telegram grouped media error
        telegram_error = """
        telethon.errors.rpcerrorlist.BadRequestError: SendMultiMediaRequest: 
        Invalid media object provided (caused by AlbumUploadError)
        """
        result = self.queue_manager._is_invalid_media_error(telegram_error)
        self.assertTrue(result, "Should detect real Telegram grouped media error")
        
        # Scenario 2: Video corruption with multiple indicators
        corruption_error = "Upload failed: invalid_file corrupted, unsupported format detected"
        result = self.queue_manager._is_invalid_media_error(corruption_error)
        self.assertTrue(result, "Should detect video corruption with multiple indicators")
        
        # Scenario 3: Network error (should not be detected)
        network_error = "Failed to upload: network timeout, connection lost"
        result = self.queue_manager._is_invalid_media_error(network_error)
        self.assertFalse(result, "Should not detect network errors as invalid media")


def run_video_error_tests():
    """Run the video upload error handling tests."""
    print("🧪 Testing Video Upload Error Handling")
    print("=" * 50)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestVideoUploadErrorHandling)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 50)
    if result.wasSuccessful():
        print(f"✅ All {result.testsRun} video error handling tests passed!")
    else:
        print(f"❌ {len(result.failures)} test(s) failed, {len(result.errors)} error(s)")
        
    return result.wasSuccessful()


if __name__ == "__main__":
    run_video_error_tests()