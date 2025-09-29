#!/usr/bin/env python3
"""
Test that transcode_enabled setting is respected and .ts files are handled correctly
"""

import asyncio
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

async def test_transcode_enabled_true():
    """Test that compression happens when transcode_enabled=True"""
    print("🧪 Testing transcode_enabled=True...")
    
    try:
        # Mock TRANSCODE_ENABLED to True
        with patch('utils.media_processing.TRANSCODE_ENABLED', True):
            from utils.media_processing import needs_video_processing
            
            # Test different file types
            test_cases = [
                ('video.mp4', True, "MP4 should be processed when enabled"),
                ('video.avi', True, "AVI should be processed when enabled"),
                ('video.mkv', True, "MKV should be processed when enabled"),
                ('video.ts', False, ".ts should NOT be processed (streamable)"),
            ]
            
            for filename, expected, description in test_cases:
                with tempfile.NamedTemporaryFile(suffix=filename, delete=False) as temp_file:
                    temp_file.write(b"fake video content")
                    temp_path = temp_file.name
                
                try:
                    result = needs_video_processing(temp_path)
                    assert result == expected, f"{description} - got {result}, expected {expected}"
                    print(f"  ✅ {filename}: {result} (correct)")
                finally:
                    os.unlink(temp_path)
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_transcode_enabled_false():
    """Test that compression is skipped when transcode_enabled=False"""
    print("\n🧪 Testing transcode_enabled=False...")
    
    try:
        # Mock TRANSCODE_ENABLED to False
        with patch('utils.media_processing.TRANSCODE_ENABLED', False):
            from utils.media_processing import needs_video_processing
            
            # Test different file types - all should return False when disabled
            test_cases = [
                ('video.mp4', False, "MP4 should NOT be processed when disabled"),
                ('video.avi', False, "AVI should NOT be processed when disabled"),
                ('video.mkv', False, "MKV should NOT be processed when disabled"),
                ('video.ts', False, ".ts should NOT be processed (streamable)"),
            ]
            
            for filename, expected, description in test_cases:
                with tempfile.NamedTemporaryFile(suffix=filename, delete=False) as temp_file:
                    temp_file.write(b"fake video content")
                    temp_path = temp_file.name
                
                try:
                    result = needs_video_processing(temp_path)
                    assert result == expected, f"{description} - got {result}, expected {expected}"
                    print(f"  ✅ {filename}: {result} (correct)")
                finally:
                    os.unlink(temp_path)
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_ts_file_handling():
    """Test that .ts files are always skipped regardless of settings"""
    print("\n🧪 Testing .ts file handling...")
    
    try:
        from utils.media_processing import needs_video_processing
        
        # Test .ts files with both enabled and disabled settings
        for enabled_setting in [True, False]:
            with patch('utils.media_processing.TRANSCODE_ENABLED', enabled_setting):
                with tempfile.NamedTemporaryFile(suffix='.ts', delete=False) as temp_file:
                    temp_file.write(b"fake ts video content")
                    temp_path = temp_file.name
                
                try:
                    result = needs_video_processing(temp_path)
                    assert result == False, f".ts files should never be processed (transcode_enabled={enabled_setting})"
                    print(f"  ✅ .ts file with transcode_enabled={enabled_setting}: {result} (correct)")
                finally:
                    os.unlink(temp_path)
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_queue_manager_integration():
    """Test that queue manager respects the transcode settings"""
    print("\n🧪 Testing queue manager integration...")
    
    try:
        # Test with transcoding disabled
        with patch('utils.media_processing.TRANSCODE_ENABLED', False):
            from utils.queue_manager import QueueManager
            
            queue_manager = QueueManager()
            
            # Create a mock video file
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                temp_file.write(b"fake video content")
                temp_path = temp_file.name
            
            try:
                # Mock the compression function to track if it's called
                compression_called = False
                
                async def mock_compress_video(input_path, output_path=None):
                    nonlocal compression_called
                    compression_called = True
                    return None  # Simulate failure to avoid file operations
                
                # Test upload task processing
                upload_task = {
                    'filename': 'test.mp4',
                    'file_path': temp_path,
                    'event': None
                }
                
                with patch('utils.media_processing.compress_video_for_telegram', mock_compress_video):
                    await queue_manager._process_direct_media_upload(upload_task)
                
                # Should not have called compression when disabled
                assert not compression_called, "Compression should not be called when transcode_enabled=False"
                print("  ✅ Queue manager respects transcode_enabled=False")
                
            finally:
                os.unlink(temp_path)
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_configuration_loading():
    """Test that configuration is loaded correctly"""
    print("\n🧪 Testing configuration loading...")
    
    try:
        from utils.constants import TRANSCODE_ENABLED
        from config import config
        
        # Check that the constant is loaded from config
        assert TRANSCODE_ENABLED == config.transcode_enabled, "TRANSCODE_ENABLED should match config value"
        
        # Check the current value from secrets.properties
        print(f"  Current transcode_enabled setting: {TRANSCODE_ENABLED}")
        
        # Based on the user's secrets.properties, it should be True
        assert TRANSCODE_ENABLED == True, "transcode_enabled should be True according to secrets.properties"
        
        print("  ✅ Configuration loaded correctly from secrets.properties")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all transcode configuration tests"""
    print("🚀 Transcode Configuration Tests")
    print("=" * 50)
    
    tests = [
        ("Transcode Enabled=True", test_transcode_enabled_true()),
        ("Transcode Enabled=False", test_transcode_enabled_false()),
        (".ts File Handling", test_ts_file_handling()),
        ("Queue Manager Integration", test_queue_manager_integration()),
        ("Configuration Loading", test_configuration_loading())
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
        print("\n🎉 All transcode configuration tests passed!")
        print("\n💡 Configuration behavior:")
        print("  ✅ transcode_enabled=true → Videos get compressed (except .ts)")
        print("  ✅ transcode_enabled=false → No video compression")
        print("  ✅ .ts files → Never compressed (streamable in Telegram)")
        print("  ✅ Queue manager respects transcode settings")
        print("  ✅ Configuration loaded from secrets.properties")
        
        print("\n🔧 Implementation details:")
        print("  • needs_video_processing() checks TRANSCODE_ENABLED setting")
        print("  • .ts files always return False (streamable format)")
        print("  • Queue manager uses needs_video_processing() for decisions")
        print("  • compress_video_for_telegram() only called when needed")
        
        print("\n✨ Ready to use with current setting: transcode_enabled=true")
    else:
        print(f"\n❌ {total - passed} test(s) failed.")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)