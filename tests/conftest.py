"""
Test utilities and fixtures for the test suite
"""

import asyncio
import json
import tempfile
import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from unittest.mock import Mock, AsyncMock
import pytest

# Test data directory
TEST_DATA_DIR = Path(__file__).parent / "test_data"
TEST_DATA_DIR.mkdir(exist_ok=True)

# Sample file data for testing
SAMPLE_FILES = {
    "test.txt": b"Hello, this is a test file content.",
    "test.pdf": b"%PDF-1.4\n%Test PDF content",
    "test.mp4": b"\x00\x00\x00\x20ftypmp41",  # Minimal MP4 header
    "test.zip": b"PK\x03\x04",  # ZIP file signature
    "test.rar": b"Rar!\x1a\x07\x00",  # RAR file signature
    "test.7z": b"7z\xbc\xaf'\x1c",  # 7z file signature
}

class MockTelegramClient:
    """Mock Telegram client for testing"""
    
    def __init__(self):
        self.connected = False
        self.session = Mock()
        self.session.dc_id = 1
        self.session.auth_key = Mock()
        self.loop = asyncio.get_event_loop()
        self._log = Mock()
        self._proxy = None
        self._init_request = Mock()
        self._init_request.query = Mock()
        
    async def connect(self):
        self.connected = True
        
    async def disconnect(self):
        self.connected = False
        
    async def download_media(self, message, file=None, progress_callback=None):
        """Mock download that creates a test file"""
        if file:
            # Create test content
            content = SAMPLE_FILES.get("test.txt", b"Mock file content")
            if isinstance(file, str):
                with open(file, 'wb') as f:
                    f.write(content)
                return file
            else:
                file.write(content)
                return file
        return b"Mock file content"
        
    async def send_message(self, entity, message, **kwargs):
        """Mock send message"""
        mock_message = Mock()
        mock_message.id = 12345
        return mock_message
        
    async def send_file(self, entity, file, **kwargs):
        """Mock send file"""
        mock_message = Mock()
        mock_message.id = 12346
        return mock_message
        
    def __call__(self, request):
        """Mock for calling Telegram methods"""
        if hasattr(request, '__class__'):
            if 'ExportAuthorizationRequest' in str(request.__class__):
                mock_auth = Mock()
                mock_auth.id = 123
                mock_auth.bytes = b"mock_auth_bytes"
                return mock_auth
        return AsyncMock()
    
    async def _get_dc(self, dc_id=None):
        """Mock get data center"""
        mock_dc = Mock()
        mock_dc.ip_address = "149.154.167.50"
        mock_dc.port = 443
        mock_dc.id = dc_id or 1
        return mock_dc
        
    def _connection(self, ip, port, dc_id, **kwargs):
        """Mock connection"""
        return Mock()
        
    async def _call(self, sender, request):
        """Mock call method"""
        mock_result = Mock()
        mock_result.bytes = b"Mock download chunk"
        return mock_result

class MockDocument:
    """Mock Telegram document for testing"""
    
    def __init__(self, filename="test.pdf", size=1024*1024, mime_type="application/pdf"):
        self.file_name = filename
        self.size = size
        self.mime_type = mime_type
        self.id = 123456
        self.access_hash = 789012
        self.date = 1640995200  # 2022-01-01
        
class MockMessage:
    """Mock Telegram message for testing"""
    
    def __init__(self, text="", document=None, media=None):
        self.message = text
        self.text = text
        self.document = document
        self.media = media or document
        self.id = 98765
        self.date = 1640995200
        self.chat_id = 12345
        self.sender_id = 67890

class TestFileManager:
    """Manages test files and cleanup"""
    
    def __init__(self):
        self.temp_dir = None
        self.created_files = []
        
    def setup(self):
        """Setup temporary directory for tests"""
        self.temp_dir = tempfile.mkdtemp(prefix="extract_test_")
        return self.temp_dir
        
    def create_test_file(self, filename: str, content: bytes = None) -> str:
        """Create a test file with given content"""
        if not self.temp_dir:
            self.setup()
            
        filepath = os.path.join(self.temp_dir, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        if content is None:
            content = SAMPLE_FILES.get(filename, b"Default test content")
            
        with open(filepath, 'wb') as f:
            f.write(content)
            
        self.created_files.append(filepath)
        return filepath
        
    def create_test_archive(self, archive_type: str = "zip") -> str:
        """Create a test archive file"""
        if archive_type == "zip":
            import zipfile
            archive_path = self.create_test_file("test.zip", b"")
            with zipfile.ZipFile(archive_path, 'w') as zf:
                for name, content in SAMPLE_FILES.items():
                    if name != "test.zip":
                        zf.writestr(name, content)
            return archive_path
        elif archive_type == "rar":
            # Create a mock RAR file (actual RAR creation requires rarfile library)
            return self.create_test_file("test.rar", SAMPLE_FILES["test.rar"])
        else:
            return self.create_test_file(f"test.{archive_type}", b"Mock archive content")
            
    def cleanup(self):
        """Clean up all test files"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        self.created_files.clear()

class MockProgressCallback:
    """Mock progress callback for testing progress tracking"""
    
    def __init__(self):
        self.calls = []
        self.last_progress = 0
        
    def __call__(self, current: int, total: int):
        progress = (current / total) * 100 if total > 0 else 0
        self.calls.append({
            'current': current,
            'total': total,
            'progress': progress,
            'timestamp': asyncio.get_event_loop().time()
        })
        self.last_progress = progress
        
    def get_progress_history(self):
        """Get list of all progress updates"""
        return self.calls
        
    def get_last_progress(self) -> float:
        """Get last progress percentage"""
        return self.last_progress

def create_mock_config() -> Dict[str, Any]:
    """Create mock configuration for testing"""
    return {
        "max_download_workers": 2,
        "max_upload_workers": 2,
        "max_retry_attempts": 3,
        "retry_delay_base": 1,
        "retry_delay_max": 30,
        "progress_update_interval": 1,
        "queue_save_interval": 60,
        "supported_formats": [
            ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"
        ],
        "video_formats": [".mp4", ".avi", ".mkv", ".mov", ".wmv"],
        "image_formats": [".jpg", ".jpeg", ".png", ".gif", ".bmp"],
        "document_formats": [".pdf", ".doc", ".docx", ".txt", ".rtf"]
    }

# Pytest fixtures
@pytest.fixture
def mock_client():
    """Fixture providing a mock Telegram client"""
    return MockTelegramClient()

@pytest.fixture
def mock_document():
    """Fixture providing a mock document"""
    return MockDocument()

@pytest.fixture
def mock_message():
    """Fixture providing a mock message"""
    return MockMessage()

@pytest.fixture
def file_manager():
    """Fixture providing a test file manager"""
    manager = TestFileManager()
    manager.setup()
    yield manager
    manager.cleanup()

@pytest.fixture
def mock_progress_callback():
    """Fixture providing a mock progress callback"""
    return MockProgressCallback()

@pytest.fixture
def mock_config():
    """Fixture providing mock configuration"""
    return create_mock_config()

@pytest.fixture
def event_loop():
    """Fixture providing an event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# Shared temp_dir fixture for tests that expect it in multiple classes
@pytest.fixture
def temp_dir():
    """Provide a temporary directory path and clean it up after use."""
    import tempfile, shutil
    d = tempfile.mkdtemp(prefix="suite_tmp_")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)