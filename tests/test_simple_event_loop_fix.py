#!/usr/bin/env python3
"""
Simple test for the event loop fix - ensures no RuntimeError on initialization.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_no_runtime_error():
    """Test that QueueManager can be created without RuntimeError: no running event loop"""
    print("🧪 Testing QueueManager initialization without event loop...")
    
    try:
        # This should NOT raise RuntimeError: no running event loop
        from utils.queue_manager import QueueManager
        queue_manager = QueueManager()
        
        print("✅ QueueManager created successfully")
        print(f"  - Pending download items: {queue_manager._pending_download_items}")
        print(f"  - Pending upload items: {queue_manager._pending_upload_items}")
        print(f"  - Download task created: {queue_manager.download_task is not None}")
        
        return True
    except RuntimeError as e:
        if "no running event loop" in str(e):
            print(f"❌ RuntimeError still occurs: {e}")
            return False
        else:
            print(f"❌ Different RuntimeError: {e}")
            return False
    except Exception as e:
        print(f"❌ Other error: {e}")
        return False

async def test_ensure_processors_started():
    """Test that ensure_processors_started works with event loop"""
    print("\n🧪 Testing ensure_processors_started with event loop...")
    
    try:
        from utils.queue_manager import get_queue_manager
        queue_manager = get_queue_manager()
        
        initial_pending_download = queue_manager._pending_download_items
        initial_pending_upload = queue_manager._pending_upload_items
        
        print(f"  - Initial pending downloads: {initial_pending_download}")
        print(f"  - Initial pending uploads: {initial_pending_upload}")
        
        # This should work now that we have an event loop
        await queue_manager.ensure_processors_started()
        
        if initial_pending_download > 0:
            assert queue_manager.download_task is not None, "Download task should be created"
            print("✅ Download processor started")
        else:
            print("ℹ️  No download items to process")
            
        if initial_pending_upload > 0:
            assert queue_manager.upload_task is not None, "Upload task should be created"
            print("✅ Upload processor started")
        else:
            print("ℹ️  No upload items to process")
        
        # Clean up
        if queue_manager.download_task:
            queue_manager.download_task.cancel()
            try:
                await queue_manager.download_task
            except asyncio.CancelledError:
                pass
                
        if queue_manager.upload_task:
            queue_manager.upload_task.cancel()
            try:
                await queue_manager.upload_task
            except asyncio.CancelledError:
                pass
        
        return True
        
    except Exception as e:
        print(f"❌ Error in ensure_processors_started: {e}")
        return False

async def test_integration_workflow():
    """Test the complete workflow like in the main script"""
    print("\n🧪 Testing integration workflow...")
    
    try:
        # Simulate main script workflow
        from utils.queue_manager import get_queue_manager
        
        # Step 1: Get queue manager (happens during import)
        queue_manager = get_queue_manager()
        print("✅ Queue manager obtained")
        
        # Step 2: Start processors (happens in main_async)
        await queue_manager.ensure_processors_started()
        print("✅ Processors started")
        
        # Step 3: Add new task (normal operation)
        test_task = {'type': 'direct_media_download', 'filename': 'test.mp4'}
        await queue_manager.add_download_task(test_task)
        print("✅ New task added")
        
        # Clean up
        if queue_manager.download_task:
            queue_manager.download_task.cancel()
            try:
                await queue_manager.download_task
            except asyncio.CancelledError:
                pass
        
        return True
        
    except Exception as e:
        print(f"❌ Error in integration workflow: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests"""
    print("🚀 Event Loop Fix Validation")
    print("=" * 40)
    
    # Test 1: No event loop error on init
    result1 = test_no_runtime_error()
    
    # Test 2: ensure_processors_started works
    result2 = await test_ensure_processors_started()
    
    # Test 3: Integration workflow
    result3 = await test_integration_workflow()
    
    print("\n" + "=" * 40)
    print("📊 Test Results:")
    print(f"  {'✅' if result1 else '❌'} No RuntimeError on init")
    print(f"  {'✅' if result2 else '❌'} ensure_processors_started works")
    print(f"  {'✅' if result3 else '❌'} Integration workflow works")
    
    all_passed = result1 and result2 and result3
    
    if all_passed:
        print("\n🎉 All tests passed! Event loop fix is working correctly.")
        print("\n💡 The fix:")
        print("  - QueueManager can be initialized without event loop")
        print("  - Processors start when ensure_processors_started() is called")
        print("  - Integration with main script workflow works")
    else:
        print("\n❌ Some tests failed.")
    
    return all_passed

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)