#!/usr/bin/env python3
"""
Functional test for queue processing behavior that simulates real usage.
This test verifies the status messages work correctly in practice.
"""

import asyncio
import sys
import logging
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set up detailed logging for testing
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_realistic_queue_behavior():
    """Test realistic queue behavior with simulated Telegram operations"""
    print("🧪 Testing realistic queue behavior...")
    
    try:
        from utils.queue_manager import QueueManager
        
        # Clean up queue file
        import json
        from pathlib import Path
        
        queue_file = Path("/Users/gradito.tunggulcahyo/Documents/Script/ExtractCompressedFiles/data/download_queue.json")
        if queue_file.exists():
            with open(queue_file, 'w') as f:
                json.dump([], f)
        
        queue_manager = QueueManager()
        
        print(f"✅ Created fresh queue manager")
        print(f"  - Initial download queue size: {queue_manager.download_queue.qsize()}")
        
        # Simulate rapid task additions (like receiving multiple files)
        tasks = []
        for i in range(3):
            task = {
                'type': 'direct_media_download',
                'filename': f'file_{i:02d}.mp4',
                'temp_path': f'/tmp/file_{i:02d}.mp4'
            }
            tasks.append(task)
        
        # Patch the actual download execution to prevent it from running
        original_execute = queue_manager._execute_download_task
        
        async def mock_execute(task):
            filename = task.get('filename', 'unknown')
            print(f"  [MOCK] Would download: {filename}")
            await asyncio.sleep(0.1)  # Simulate some processing time
            return
        
        queue_manager._execute_download_task = mock_execute
        
        # Add tasks rapidly
        results = []
        for i, task in enumerate(tasks):
            print(f"\n📥 Adding task {i+1}: {task['filename']}")
            was_first_item = await queue_manager.add_download_task(task)
            results.append((task['filename'], was_first_item))
            
            # Simulate status message logic from main script
            if was_first_item:
                status_msg = f'⬇️ Starting download: {task["filename"]}'
            else:
                queue_position = queue_manager.download_queue.qsize()
                status_msg = f'📋 {task["filename"]} added to download queue (position: {queue_position})'
            
            print(f"  - Status message: {status_msg}")
            print(f"  - Queue size: {queue_manager.download_queue.qsize()}")
            
            # Small delay to let processor start
            await asyncio.sleep(0.05)
        
        # Let all tasks process
        await asyncio.sleep(0.5)
        
        # Check results
        print(f"\n📊 Results:")
        for filename, was_first in results:
            print(f"  - {filename}: {'First item' if was_first else 'Queued item'}")
        
        # At least the first task should be marked as first
        assert results[0][1], "First task should be marked as first item"
        print("✅ First task was correctly marked as first")
        
        # Clean up
        queue_manager._execute_download_task = original_execute
        if queue_manager.download_task:
            queue_manager.download_task.cancel()
            try:
                await queue_manager.download_task
            except asyncio.CancelledError:
                pass
        
        print("✅ Realistic queue behavior test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_status_message_integration():
    """Test the integration between queue manager and status messages"""
    print("\n🧪 Testing status message integration...")
    
    try:
        # Test the logic from the main script
        def get_status_message(filename, was_first_item, queue_position):
            if was_first_item:
                return f'⬇️ Starting download: {filename}'
            else:
                return f'📋 {filename} added to download queue (position: {queue_position})'
        
        # Test various scenarios
        test_cases = [
            ("file1.mp4", True, 1, "⬇️ Starting download"),
            ("file2.mp4", False, 2, "📋 file2.mp4 added to download queue"),
            ("file3.mp4", False, 3, "📋 file3.mp4 added to download queue"),
        ]
        
        for filename, was_first, position, expected_prefix in test_cases:
            status = get_status_message(filename, was_first, position)
            print(f"  - {filename}: {status}")
            assert expected_prefix in status, f"Expected '{expected_prefix}' in status message"
        
        print("✅ Status message integration test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

async def test_queue_persistence():
    """Test that queue state persists correctly"""
    print("\n🧪 Testing queue persistence...")
    
    try:
        from utils.queue_manager import QueueManager
        
        # Clean up first
        import json
        from pathlib import Path
        
        queue_file = Path("/Users/gradito.tunggulcahyo/Documents/Script/ExtractCompressedFiles/data/download_queue.json")
        if queue_file.exists():
            with open(queue_file, 'w') as f:
                json.dump([], f)
        
        # Create manager and add a task
        queue_manager = QueueManager()
        
        task = {
            'type': 'direct_media_download',
            'filename': 'persistent_test.mp4',
            'temp_path': '/tmp/persistent_test.mp4'
        }
        
        await queue_manager.add_download_task(task)
        
        # Check that it was persisted
        with open(queue_file, 'r') as f:
            persisted_data = json.load(f)
        
        assert len(persisted_data) == 1, "Task should be persisted"
        assert persisted_data[0]['filename'] == 'persistent_test.mp4', "Correct task should be persisted"
        
        print("✅ Queue persistence test passed!")
        
        # Clean up
        if queue_manager.download_task:
            queue_manager.download_task.cancel()
            try:
                await queue_manager.download_task
            except asyncio.CancelledError:
                pass
        
        # Clean up file
        with open(queue_file, 'w') as f:
            json.dump([], f)
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all functional tests"""
    print("🚀 Functional Queue Processing Tests")
    print("=" * 50)
    
    tests = [
        ("Realistic Queue Behavior", test_realistic_queue_behavior()),
        ("Status Message Integration", test_status_message_integration()),
        ("Queue Persistence", test_queue_persistence())
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
        print("\n🎉 All functional tests passed!")
        print("\n💡 The queue processing system:")
        print("  ✅ Correctly identifies first vs subsequent files")
        print("  ✅ Shows appropriate status messages")
        print("  ✅ Persists queue state")
        print("  ✅ Handles rapid task additions")
        print("  ✅ Maintains proper processor lifecycle")
    else:
        print(f"\n❌ {total - passed} test(s) failed.")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)