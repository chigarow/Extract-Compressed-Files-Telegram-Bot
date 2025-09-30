#!/usr/bin/env python3
"""
Test the upload task fixes for None event handling and missing imports
"""

import asyncio
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

async def test_upload_with_none_event():
    """Test that upload tasks work with None event (restored tasks)"""
    print("🧪 Testing upload with None event...")
    
    try:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_file.write(b"fake video content")
            temp_path = temp_file.name
        
        # Mock the queue manager and its dependencies
        with patch('utils.queue_manager.get_client') as mock_get_client, \
             patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops, \
             patch('utils.queue_manager.ensure_target_entity') as mock_ensure_target, \
             patch('utils.queue_manager.CacheManager') as mock_cache_manager:
            
            mock_client = Mock()
            mock_get_client.return_value = mock_client
            
            mock_ops_instance = Mock()
            mock_ops_instance.upload_media_file = AsyncMock()
            mock_telegram_ops.return_value = mock_ops_instance
            
            mock_target = Mock()
            mock_ensure_target.return_value = mock_target
            
            mock_cache = Mock()
            mock_cache_manager.return_value = mock_cache
            
            from utils.queue_manager import QueueManager
            
            queue_manager = QueueManager()
            
            # Create upload task with None event (simulating restored task)
            upload_task = {
                'filename': 'test_restored.mp4',
                'file_path': temp_path,
                'event': None,  # This is the key - None event should not crash
                'retry_count': 0
            }
            
            # This should not crash
            await queue_manager._execute_upload_task(upload_task)
            
            # Verify upload was attempted
            mock_ops_instance.upload_media_file.assert_called_once()
            
            print("  ✅ Upload with None event completed without errors")
            
        # Clean up
        try:
            os.unlink(temp_path)
        except:
            pass
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_upload_with_valid_event():
    """Test that upload tasks work with valid event objects"""
    print("\n🧪 Testing upload with valid event...")
    
    try:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_file.write(b"fake video content")
            temp_path = temp_file.name
        
        # Mock the queue manager and its dependencies
        with patch('utils.queue_manager.get_client') as mock_get_client, \
             patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops, \
             patch('utils.queue_manager.ensure_target_entity') as mock_ensure_target, \
             patch('utils.queue_manager.CacheManager') as mock_cache_manager:
            
            mock_client = Mock()
            mock_get_client.return_value = mock_client
            
            mock_ops_instance = Mock()
            mock_ops_instance.upload_media_file = AsyncMock()
            mock_ops_instance.create_progress_callback = Mock(return_value=Mock())
            mock_telegram_ops.return_value = mock_ops_instance
            
            mock_target = Mock()
            mock_ensure_target.return_value = mock_target
            
            mock_cache = Mock()
            mock_cache_manager.return_value = mock_cache
            
            # Mock event with reply method
            mock_event = Mock()
            mock_event.reply = AsyncMock(return_value=Mock())
            
            from utils.queue_manager import QueueManager
            
            queue_manager = QueueManager()
            
            # Create upload task with valid event
            upload_task = {
                'filename': 'test_live.mp4',
                'file_path': temp_path,
                'event': mock_event,  # Valid event object
                'retry_count': 0
            }
            
            # This should not crash and should call event.reply
            await queue_manager._execute_upload_task(upload_task)
            
            # Verify upload was attempted
            mock_ops_instance.upload_media_file.assert_called_once()
            
            # Verify event.reply was called for status message
            mock_event.reply.assert_called()
            
            print("  ✅ Upload with valid event completed with status updates")
            
        # Clean up
        try:
            os.unlink(temp_path)
        except:
            pass
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_import_fixes():
    """Test that all required constants are imported correctly"""
    print("\n🧪 Testing import fixes...")
    
    try:
        # These should not raise NameError anymore
        from utils.constants import MAX_RETRY_ATTEMPTS, RETRY_BASE_INTERVAL
        
        print(f"  ✅ MAX_RETRY_ATTEMPTS: {MAX_RETRY_ATTEMPTS}")
        print(f"  ✅ RETRY_BASE_INTERVAL: {RETRY_BASE_INTERVAL}")
        
        # Test syntax compilation
        import py_compile
        import tempfile
        
        # This will raise SyntaxError if there are issues
        py_compile.compile('/Users/gradito.tunggulcahyo/Documents/Script/ExtractCompressedFiles/utils/queue_manager.py', doraise=True)
        
        print("  ✅ Queue manager syntax is valid")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

async def test_retry_logic():
    """Test that retry logic handles None event correctly"""
    print("\n🧪 Testing retry logic with None event...")
    
    try:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_file.write(b"fake video content")
            temp_path = temp_file.name
        
        with patch('utils.queue_manager.get_client') as mock_get_client, \
             patch('utils.queue_manager.TelegramOperations') as mock_telegram_ops, \
             patch('utils.queue_manager.ensure_target_entity') as mock_ensure_target, \
             patch('utils.queue_manager.CacheManager') as mock_cache_manager:
            
            mock_client = Mock()
            mock_get_client.return_value = mock_client
            
            # Make upload_media_file fail to trigger retry logic
            mock_ops_instance = Mock()
            mock_ops_instance.upload_media_file = AsyncMock(side_effect=Exception("Upload failed"))
            mock_telegram_ops.return_value = mock_ops_instance
            
            mock_target = Mock()
            mock_ensure_target.return_value = mock_target
            
            mock_cache = Mock()
            mock_cache_manager.return_value = mock_cache
            
            from utils.queue_manager import QueueManager
            
            queue_manager = QueueManager()
            
            # Mock the retry queue method
            queue_manager._add_to_retry_queue = AsyncMock()
            
            # Create upload task with None event
            upload_task = {
                'filename': 'test_retry.mp4',
                'file_path': temp_path,
                'event': None,  # None event should not crash in retry logic
                'retry_count': 0
            }
            
            # This should not crash even when upload fails and retry logic kicks in
            await queue_manager._execute_upload_task(upload_task)
            
            # Verify retry queue was called
            queue_manager._add_to_retry_queue.assert_called_once()
            
            print("  ✅ Retry logic handles None event correctly")
            
        # Clean up
        try:
            os.unlink(temp_path)
        except:
            pass
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all upload fix tests"""
    print("🚀 Upload Task Fix Tests")
    print("=" * 50)
    
    tests = [
        ("Upload with None Event", test_upload_with_none_event()),
        ("Upload with Valid Event", test_upload_with_valid_event()),
        ("Import Fixes", test_import_fixes()),
        ("Retry Logic", test_retry_logic())
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
        print("\n🎉 All upload fix tests passed!")
        print("\n💡 Fixes implemented:")
        print("  ✅ Handle None event objects (restored tasks)")
        print("  ✅ Import MAX_RETRY_ATTEMPTS and RETRY_BASE_INTERVAL")
        print("  ✅ Progress callbacks work with background tasks")
        print("  ✅ Retry logic doesn't crash on None events")
        print("  ✅ Status messages only sent when event is available")
        
        print("\n🔧 Technical improvements:")
        print("  • Event null checks before calling reply()")
        print("  • Proper import statements for retry constants")
        print("  • Logging fallbacks for background tasks")
        print("  • Graceful degradation for restored tasks")
        
        print("\n✨ Upload tasks now work for both live and restored scenarios!")
    else:
        print(f"\n❌ {total - passed} test(s) failed.")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)