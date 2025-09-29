#!/usr/bin/env python3
"""
Test for video compression timeout cleanup functionality.
"""

import os
import tempfile
import asyncio
import time
from unittest.mock import patch, MagicMock
import subprocess
import sys

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_compression_timeout_cleanup():
    """Test that incomplete compressed files are cleaned up on timeout"""
    print("🧪 Testing video compression timeout cleanup...")
    
    try:
        from utils.media_processing import compress_video_for_telegram
        
        # Create temporary files
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as input_file:
            input_path = input_file.name
            # Write some dummy data
            input_file.write(b'dummy video data')
        
        output_path = input_path.replace('.mp4', '_compressed.mp4')
        
        # Mock subprocess.run to simulate timeout
        def mock_timeout_run(*args, **kwargs):
            # Create a partial output file to simulate ffmpeg starting
            with open(output_path, 'w') as f:
                f.write('partial compressed data')
            raise subprocess.TimeoutExpired(['ffmpeg'], 1)
        
        # Test timeout scenario
        with patch('subprocess.run', side_effect=mock_timeout_run):
            with patch('asyncio.get_running_loop') as mock_loop:
                # Mock the executor to directly call our mock function
                mock_loop.return_value.run_in_executor.side_effect = lambda executor, func: asyncio.coroutine(lambda: func())()
                
                # Verify file doesn't exist before
                assert not os.path.exists(output_path), "Output file should not exist initially"
                
                # Run compression (should timeout and clean up)
                result = await compress_video_for_telegram(input_path, output_path)
                
                # Check results
                assert result is False, "Compression should return False on timeout"
                assert not os.path.exists(output_path), "Compressed file should be cleaned up after timeout"
                
        print("✅ Timeout cleanup test passed!")
        
        # Test failure scenario
        def mock_failure_run(*args, **kwargs):
            # Create a partial output file to simulate ffmpeg starting
            with open(output_path, 'w') as f:
                f.write('partial compressed data')
            # Return failed result
            result = MagicMock()
            result.returncode = 1
            result.stderr = "Mock compression error"
            return result
        
        with patch('subprocess.run', side_effect=mock_failure_run):
            with patch('asyncio.get_running_loop') as mock_loop:
                mock_loop.return_value.run_in_executor.side_effect = lambda executor, func: asyncio.coroutine(lambda: func())()
                
                # Run compression (should fail and clean up)
                result = await compress_video_for_telegram(input_path, output_path)
                
                # Check results
                assert result is False, "Compression should return False on failure"
                assert not os.path.exists(output_path), "Compressed file should be cleaned up after failure"
        
        print("✅ Failure cleanup test passed!")
        
        # Cleanup test files
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_successful_compression_no_cleanup():
    """Test that successful compression doesn't remove the output file"""
    print("🧪 Testing successful compression (no cleanup)...")
    
    try:
        from utils.media_processing import compress_video_for_telegram
        
        # Create temporary files
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as input_file:
            input_path = input_file.name
            input_file.write(b'dummy video data')
        
        output_path = input_path.replace('.mp4', '_compressed.mp4')
        
        # Mock successful compression
        def mock_success_run(*args, **kwargs):
            # Create successful output file
            with open(output_path, 'w') as f:
                f.write('successfully compressed data')
            # Return success result
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            return result
        
        with patch('subprocess.run', side_effect=mock_success_run):
            with patch('asyncio.get_running_loop') as mock_loop:
                mock_loop.return_value.run_in_executor.side_effect = lambda executor, func: asyncio.coroutine(lambda: func())()
                
                # Run compression (should succeed)
                result = await compress_video_for_telegram(input_path, output_path)
                
                # Check results
                assert result is True, "Compression should return True on success"
                assert os.path.exists(output_path), "Compressed file should exist after successful compression"
        
        print("✅ Successful compression test passed!")
        
        # Cleanup test files
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

async def main():
    """Run compression cleanup tests"""
    print("🚀 Video Compression Timeout Cleanup Tests")
    print("=" * 50)
    
    tests = [
        ("Timeout Cleanup", test_compression_timeout_cleanup()),
        ("Success No Cleanup", test_successful_compression_no_cleanup())
    ]
    
    results = []
    for test_name, test_coro in tests:
        print(f"\n📋 Running: {test_name}")
        try:
            result = await test_coro
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results:")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {test_name}")
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Video compression timeout cleanup is working correctly.")
        print("\n💡 Benefits:")
        print("  - Incomplete _compressed.mp4 files are automatically removed on timeout")
        print("  - Failed compression files are cleaned up")
        print("  - Prevents disk space accumulation from failed compressions")
        return True
    else:
        print(f"\n❌ {total - passed} test(s) failed.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)