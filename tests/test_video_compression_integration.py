#!/usr/bin/env python3
"""
Integration test for video compression timeout cleanup functionality.
Tests the actual compression function with timeout scenarios.
"""

import pytest
import os
import tempfile
import asyncio
from unittest.mock import patch
import subprocess
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.mark.asyncio
async def test_video_compression_timeout_cleanup():
    """Test that video compression cleans up files on timeout"""
    
    from utils.media_processing import compress_video_for_telegram
    
    # Create temporary input file
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as input_file:
        input_path = input_file.name
        input_file.write(b'dummy video data for testing')
    
    output_path = input_path.replace('.mp4', '_compressed.mp4')
    
    try:
        # Test 1: Timeout scenario
        def mock_timeout_process(*args, **kwargs):
            # Create a partial output file to simulate ffmpeg starting
            with open(output_path, 'w') as f:
                f.write('partial compressed data')
            
            # Simulate timeout
            raise subprocess.TimeoutExpired(cmd=['ffmpeg'], timeout=1)
        
        with patch('subprocess.run', side_effect=mock_timeout_process):
            # Run compression - should timeout and clean up
            result = await compress_video_for_telegram(input_path, output_path)
            
            # Check result is a string path or None
            assert result is None or isinstance(result, str), "Result should be None or string path"
            
            if result:
                assert result == output_path, "Result should be the output path"
            assert not os.path.exists(output_path), f"Output file {output_path} should be cleaned up after timeout"
        
        # Test 2: Process failure scenario  
        def mock_failed_process(*args, **kwargs):
            # Create a partial output file to simulate ffmpeg starting
            with open(output_path, 'w') as f:
                f.write('partial compressed data')
            
            # Mock failed subprocess result
            class MockResult:
                returncode = 1
                stderr = "Mock ffmpeg error"
            
            return MockResult()
        
        with patch('subprocess.run', side_effect=mock_failed_process):
            # Run compression - should fail and clean up
            result = await compress_video_for_telegram(input_path, output_path)
            
            # Verify results
            assert result is None, "Compression should return None on process error"
            assert not os.path.exists(output_path), f"Output file {output_path} should be cleaned up after failure"
        
        # Test 3: Success scenario (no cleanup)
        def mock_success_process(*args, **kwargs):
            # Create successful output file
            with open(output_path, 'w') as f:
                f.write('successfully compressed data')
            
            # Mock successful subprocess result
            class MockResult:
                returncode = 0
                stderr = ""
            
            return MockResult()
        
        with patch('subprocess.run', side_effect=mock_success_process):
            # Run compression - should succeed and keep file
            result = await compress_video_for_telegram(input_path, output_path)
            
            # Verify results
            assert result == output_path, "Compression should return output path on success"
            assert os.path.exists(output_path), f"Output file {output_path} should exist after successful compression"
    
    finally:
        # Cleanup test files
        for path in [input_path, output_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass

def test_compression_timeout_import():
    """Test that the compression function can be imported correctly"""
    from utils.media_processing import compress_video_for_telegram
    assert callable(compress_video_for_telegram), "compress_video_for_telegram should be callable"

def test_timeout_configuration():
    """Test that compression timeout configuration is available"""
    from utils.constants import COMPRESSION_TIMEOUT_SECONDS
    assert isinstance(COMPRESSION_TIMEOUT_SECONDS, int), "COMPRESSION_TIMEOUT_SECONDS should be an integer"
    assert COMPRESSION_TIMEOUT_SECONDS > 0, "COMPRESSION_TIMEOUT_SECONDS should be positive"

if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])