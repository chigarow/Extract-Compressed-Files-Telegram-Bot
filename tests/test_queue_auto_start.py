#!/usr/bin/env python3
"""
Test script to verify queue processing starts correctly when restored from persistent storage.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

async def test_queue_restoration():
    """Test that queue processing starts when items are restored from storage"""
    print("🧪 Testing queue restoration and auto-start functionality...")
    
    try:
        from utils.queue_manager import QueueManager
        from utils.cache_manager import PersistentQueue
        
        # Create a temporary directory for test files
        with tempfile.TemporaryDirectory() as temp_dir:
            download_queue_file = os.path.join(temp_dir, 'test_download_queue.json')
            
            # Create a mock download task
            test_task = {
                'type': 'direct_media_download',
                'filename': 'test.mp4',
                'temp_path': '/tmp/test.mp4'
            }
            
            # Manually create a persistent queue file with a task
            test_persistent_queue = PersistentQueue(download_queue_file)
            test_persistent_queue.add_item(test_task)
            
            print(f"✅ Created test queue file with 1 task")
            
            # Patch the queue manager to use our test file
            original_download_file = None
            try:
                from utils import constants
                original_download_file = constants.DOWNLOAD_QUEUE_FILE
                constants.DOWNLOAD_QUEUE_FILE = download_queue_file
                
                # Create a new queue manager - this should restore and start processing
                queue_manager = QueueManager()
                
                # Check if the download task was created (indicating processing started)
                if queue_manager.download_task is not None:
                    print("✅ Download processor task was created automatically")
                    task_status = "running" if not queue_manager.download_task.done() else "completed/failed"
                    print(f"✅ Download task status: {task_status}")
                else:
                    print("❌ Download processor task was not created")
                    return False
                
                # Check queue size
                queue_size = queue_manager.download_queue.qsize()
                print(f"✅ Queue size after restoration: {queue_size}")
                
                # Clean up the task
                if queue_manager.download_task:
                    queue_manager.download_task.cancel()
                    try:
                        await queue_manager.download_task
                    except asyncio.CancelledError:
                        pass
                
                return True
                
            finally:
                # Restore original constant
                if original_download_file:
                    constants.DOWNLOAD_QUEUE_FILE = original_download_file
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_empty_queue_no_start():
    """Test that processing doesn't start with empty queue"""
    print("\n🧪 Testing empty queue (no auto-start)...")
    
    try:
        from utils.queue_manager import QueueManager
        
        # Create a fresh queue manager with no persisted data
        queue_manager = QueueManager()
        
        # Check that no processing tasks are started
        if queue_manager.download_task is None:
            print("✅ No download processor started for empty queue")
        else:
            print("❌ Download processor started unnecessarily")
            return False
        
        if queue_manager.upload_task is None:
            print("✅ No upload processor started for empty queue")
        else:
            print("❌ Upload processor started unnecessarily")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

async def main():
    """Run queue restoration tests"""
    print("🚀 Queue Processing Auto-Start Tests")
    print("=" * 50)
    
    tests = [
        ("Queue Restoration Auto-Start", test_queue_restoration()),
        ("Empty Queue No Start", test_empty_queue_no_start())
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
        print("\n🎉 All tests passed! Queue auto-start is working correctly.")
        print("\n💡 Fix applied:")
        print("  - Queue processors now start automatically when items are restored")
        print("  - This fixes the issue where queued files don't get processed after restart")
        return True
    else:
        print(f"\n❌ {total - passed} test(s) failed.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)