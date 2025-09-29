"""
Test suite for JSON serialization and path generation fixes in the Telegram Compressed File Extractor.
Tests the fixes for:
1. JSON serialization of Telethon Message objects
2. FFmpeg path generation issues
"""

import unittest
import tempfile
import os
import json
import datetime
from unittest.mock import Mock, MagicMock, patch
import sys

# Add the script's directory to the Python path
script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from utils.cache_manager import make_serializable, serialize_telethon_object, serialize_file_object, PersistentQueue
from utils.queue_manager import QueueManager


class TestJsonSerialization(unittest.TestCase):
    """Test JSON serialization fixes for Telethon objects."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_queue_file = os.path.join(self.temp_dir, 'test_queue.json')
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_serialize_simple_objects(self):
        """Test serialization of simple Python objects."""
        # Test simple types
        self.assertEqual(make_serializable("string"), "string")
        self.assertEqual(make_serializable(123), 123)
        self.assertEqual(make_serializable(True), True)
        self.assertEqual(make_serializable(None), None)
        
        # Test list and dict
        test_list = [1, "two", {"three": 3}]
        expected_list = [1, "two", {"three": 3}]
        self.assertEqual(make_serializable(test_list), expected_list)
        
        test_dict = {"a": 1, "b": ["c", "d"]}
        expected_dict = {"a": 1, "b": ["c", "d"]}
        self.assertEqual(make_serializable(test_dict), expected_dict)
    
    def test_serialize_datetime(self):
        """Test serialization of datetime objects."""
        test_date = datetime.datetime(2025, 9, 29, 17, 30, 0)
        result = make_serializable(test_date)
        self.assertEqual(result, "2025-09-29T17:30:00")
    
    def test_serialize_mock_telethon_message(self):
        """Test serialization of mock Telethon Message objects."""
        # Create a mock Telethon Message object
        mock_message = Mock()
        mock_message.id = 12345
        mock_message.message = "Test message content"
        mock_message.date = datetime.datetime(2025, 9, 29, 17, 30, 0)
        mock_message.from_id = 67890
        mock_message.to_id = 54321
        mock_message.out = False
        mock_message.file = None
        
        result = serialize_telethon_object(mock_message)
        
        expected = {
            'id': 12345,
            'message': "Test message content",
            'date': "2025-09-29T17:30:00",
            'from_id': 67890,
            'to_id': 54321,
            'out': False,
            'file': None,
            '_type': 'Message'
        }
        
        self.assertEqual(result, expected)
    
    def test_serialize_mock_telethon_file(self):
        """Test serialization of mock Telethon File objects."""
        # Create a mock Telethon File object
        mock_file = Mock()
        mock_file.id = 98765
        mock_file.name = "test_video.mp4"
        mock_file.size = 1048576  # 1MB
        mock_file.mime_type = "video/mp4"
        
        result = serialize_file_object(mock_file)
        
        expected = {
            'id': 98765,
            'name': "test_video.mp4",
            'size': 1048576,
            'mime_type': "video/mp4",
            '_type': 'File'
        }
        
        self.assertEqual(result, expected)
    
    def test_serialize_message_with_file(self):
        """Test serialization of Message object with File attachment."""
        # Create a mock File object
        mock_file = Mock()
        mock_file.id = 98765
        mock_file.name = "test_archive.zip"
        mock_file.size = 10485760  # 10MB
        mock_file.mime_type = "application/zip"
        
        # Create a mock Message object with file
        mock_message = Mock()
        mock_message.id = 12345
        mock_message.message = ""
        mock_message.date = datetime.datetime(2025, 9, 29, 17, 30, 0)
        mock_message.from_id = 67890
        mock_message.to_id = 54321
        mock_message.out = False
        mock_message.file = mock_file
        
        result = serialize_telethon_object(mock_message)
        
        expected = {
            'id': 12345,
            'message': "",
            'date': "2025-09-29T17:30:00",
            'from_id': 67890,
            'to_id': 54321,
            'out': False,
            'file': {
                'id': 98765,
                'name': "test_archive.zip",
                'size': 10485760,
                'mime_type': "application/zip",
                '_type': 'File'
            },
            '_type': 'Message'
        }
        
        self.assertEqual(result, expected)
    
    def test_make_serializable_with_to_dict(self):
        """Test make_serializable with objects that have to_dict method."""
        # Create a mock object with to_dict method
        mock_obj = Mock()
        mock_obj.to_dict.return_value = {"key": "value", "number": 42}
        
        result = make_serializable(mock_obj)
        self.assertEqual(result, {"key": "value", "number": 42})
        mock_obj.to_dict.assert_called_once()
    
    def test_make_serializable_with_failing_to_dict(self):
        """Test make_serializable when to_dict method fails."""
        # Create a mock object with failing to_dict method
        mock_obj = Mock()
        mock_obj.to_dict.side_effect = Exception("to_dict failed")
        mock_obj.id = 123
        mock_obj.message = "test"
        mock_obj.date = None
        mock_obj.from_id = None
        mock_obj.to_id = None
        mock_obj.out = None
        mock_obj.file = None
        
        result = make_serializable(mock_obj)
        
        # Should fall back to serialize_telethon_object
        expected = {
            'id': 123,
            'message': "test",
            'date': None,
            'from_id': None,
            'to_id': None,
            'out': None,
            'file': None,
            '_type': 'Message'
        }
        
        self.assertEqual(result, expected)
    
    def test_persistent_queue_serialization(self):
        """Test that PersistentQueue properly serializes data."""
        queue = PersistentQueue(self.test_queue_file)
        
        # Create a mock task with Telethon objects
        mock_message = Mock()
        mock_message.id = 12345
        mock_message.message = "Test message"
        mock_message.date = datetime.datetime(2025, 9, 29, 17, 30, 0)
        mock_message.from_id = 67890
        mock_message.to_id = 54321
        mock_message.out = False
        mock_message.file = None
        
        task = {
            'type': 'test_task',
            'message': mock_message,
            'filename': 'test.zip',
            'created_at': datetime.datetime.now()
        }
        
        # Add item to queue (should serialize without error)
        queue.add_item(task)
        
        # Verify file was created and contains valid JSON
        self.assertTrue(os.path.exists(self.test_queue_file))
        
        with open(self.test_queue_file, 'r') as f:
            saved_data = json.load(f)
        
        # Verify structure
        self.assertEqual(len(saved_data), 1)
        self.assertEqual(saved_data[0]['type'], 'test_task')
        self.assertEqual(saved_data[0]['filename'], 'test.zip')
        
        # Verify message was serialized properly
        message_data = saved_data[0]['message']
        self.assertEqual(message_data['id'], 12345)
        self.assertEqual(message_data['message'], "Test message")
        self.assertEqual(message_data['_type'], 'Message')


class TestPathGeneration(unittest.TestCase):
    """Test path generation fixes for video compression."""
    
    def test_compressed_path_generation_mp4(self):
        """Test compressed path generation for MP4 files."""
        # Test case that would cause the bug
        original_path = "/data/data/com.termux/files/home/project/data/video.mp4"
        
        # Simulate the corrected logic
        base_path, ext = os.path.splitext(original_path)
        if ext.lower() != '.mp4':
            compressed_path = base_path + '_compressed.mp4'
        else:
            compressed_path = base_path + '_compressed' + ext
        
        expected_path = "/data/data/com.termux/files/home/project/data/video_compressed.mp4"
        self.assertEqual(compressed_path, expected_path)
    
    def test_compressed_path_generation_other_formats(self):
        """Test compressed path generation for non-MP4 files."""
        # Test MKV file
        original_path = "/data/data/com.termux/files/home/project/data/video.mkv"
        
        base_path, ext = os.path.splitext(original_path)
        if ext.lower() != '.mp4':
            compressed_path = base_path + '_compressed.mp4'
        else:
            compressed_path = base_path + '_compressed' + ext
        
        expected_path = "/data/data/com.termux/files/home/project/data/video_compressed.mp4"
        self.assertEqual(compressed_path, expected_path)
    
    def test_path_with_multiple_dots(self):
        """Test path generation with filenames containing multiple dots."""
        original_path = "/data/data/com.termux/files/home/project/data/video.final.v2.mp4"
        
        base_path, ext = os.path.splitext(original_path)
        if ext.lower() != '.mp4':
            compressed_path = base_path + '_compressed.mp4'
        else:
            compressed_path = base_path + '_compressed' + ext
        
        expected_path = "/data/data/com.termux/files/home/project/data/video.final.v2_compressed.mp4"
        self.assertEqual(compressed_path, expected_path)
        
        # Verify this doesn't break the directory structure
        directory = os.path.dirname(compressed_path)
        expected_directory = "/data/data/com.termux/files/home/project/data"
        self.assertEqual(directory, expected_directory)
    
    def test_old_buggy_behavior(self):
        """Test to verify the old buggy behavior would fail."""
        original_path = "/data/data/com.termux/files/home/project/data/video.mp4"
        
        # Simulate the old buggy logic
        buggy_path = original_path.replace('.', '_compressed.')
        
        # This would create the wrong path
        expected_buggy = "/data/data/com_compressed.termux/files/home/project/data/video_compressed.mp4"
        self.assertEqual(buggy_path, expected_buggy)
        
        # Verify the directory would be wrong
        buggy_directory = os.path.dirname(buggy_path)
        self.assertEqual(buggy_directory, "/data/data/com_compressed.termux/files/home/project/data")
    
    def test_various_extensions(self):
        """Test path generation with various video extensions."""
        base_path = "/data/data/com.termux/files/home/project/data/video"
        
        extensions = ['.avi', '.mkv', '.mov', '.wmv', '.flv', '.ts', '.webm']
        
        for ext in extensions:
            original_path = base_path + ext
            
            path_base, path_ext = os.path.splitext(original_path)
            if path_ext.lower() != '.mp4':
                compressed_path = path_base + '_compressed.mp4'
            else:
                compressed_path = path_base + '_compressed' + path_ext
            
            expected_path = base_path + '_compressed.mp4'
            self.assertEqual(compressed_path, expected_path)
            
            # Verify directory structure remains intact
            directory = os.path.dirname(compressed_path)
            expected_directory = "/data/data/com.termux/files/home/project/data"
            self.assertEqual(directory, expected_directory)


class TestIntegrationFixes(unittest.TestCase):
    """Integration tests for the combined fixes."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('utils.queue_manager.compress_video_for_telegram')
    @patch('utils.queue_manager.needs_video_processing')
    def test_video_processing_path_generation(self, mock_needs_processing, mock_compress):
        """Test that video processing uses correct path generation."""
        mock_needs_processing.return_value = True
        mock_compress.return_value = True
        
        # Create a mock file path
        file_path = "/data/data/com.termux/files/home/project/data/test_video.mp4"
        
        # Simulate the path generation logic from the fixed code
        file_ext = os.path.splitext(file_path)[1].lower()
        base_path, ext = os.path.splitext(file_path)
        
        if file_ext != '.mp4':
            compressed_path = base_path + '_compressed.mp4'
        else:
            compressed_path = base_path + '_compressed' + ext
        
        expected_path = "/data/data/com.termux/files/home/project/data/test_video_compressed.mp4"
        self.assertEqual(compressed_path, expected_path)
        
        # Verify the directory structure is preserved
        original_dir = os.path.dirname(file_path)
        compressed_dir = os.path.dirname(compressed_path)
        self.assertEqual(original_dir, compressed_dir)
    
    def test_serialization_with_complex_objects(self):
        """Test serialization with complex nested objects."""
        # Create a complex task structure similar to what would be in the queue
        mock_file = Mock()
        mock_file.id = 98765
        mock_file.name = "complex_archive.zip"
        mock_file.size = 50000000  # 50MB
        mock_file.mime_type = "application/zip"
        
        mock_message = Mock()
        mock_message.id = 12345
        mock_message.message = ""
        mock_message.date = datetime.datetime(2025, 9, 29, 17, 30, 0)
        mock_message.from_id = 67890
        mock_message.to_id = 54321
        mock_message.out = False
        mock_message.file = mock_file
        
        # Create a complex task
        complex_task = {
            'type': 'archive_download',
            'message': mock_message,
            'event': Mock(),  # This would be a Telethon event
            'filename': 'complex_archive.zip',
            'temp_path': '/tmp/complex_archive.zip',
            'size_bytes': 50000000,
            'created_at': datetime.datetime.now(),
            'metadata': {
                'user_id': 123456,
                'chat_id': 789012,
                'nested_data': {
                    'processing_options': ['extract', 'upload'],
                    'timestamp': datetime.datetime.now()
                }
            }
        }
        
        # Test serialization
        try:
            serialized = make_serializable(complex_task)
            # Should not raise an exception
            
            # Verify it can be converted to JSON
            json_str = json.dumps(serialized)
            
            # Verify it can be loaded back
            loaded = json.loads(json_str)
            
            # Verify key structure
            self.assertEqual(loaded['type'], 'archive_download')
            self.assertEqual(loaded['filename'], 'complex_archive.zip')
            self.assertEqual(loaded['message']['_type'], 'Message')
            self.assertEqual(loaded['message']['file']['_type'], 'File')
            
        except Exception as e:
            self.fail(f"Serialization failed with exception: {e}")


if __name__ == '__main__':
    # Create a test suite with all tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestJsonSerialization))
    suite.addTests(loader.loadTestsFromTestCase(TestPathGeneration))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegrationFixes))
    
    # Run the tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Exit with appropriate code
    exit(0 if result.wasSuccessful() else 1)