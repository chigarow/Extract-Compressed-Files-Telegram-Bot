#!/usr/bin/env python3
"""Integration tests for cleanup functionality."""

import os
import sys
import time
import tempfile
import shutil

# Add script directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from utils.queue_manager import QueueManager
from utils.constants import DATA_DIR, TORBOX_DIR


def test_cleanup_with_temporary_files():
    """Test cleanup functionality with temporary files."""
    print("=" * 70)
    print("INTEGRATION TEST: Cleanup Functionality")
    print("=" * 70)
    
    # Create a temporary test area within data directory
    test_subdir = os.path.join(DATA_DIR, "test_cleanup_temp")
    os.makedirs(test_subdir, exist_ok=True)
    
    try:
        print(f"\n📁 Created test directory: {test_subdir}")
        
        # Test 1: Create old files
        print("\n[TEST 1] Testing old file cleanup...")
        old_file1 = os.path.join(test_subdir, "old_test_file_1.txt")
        old_file2 = os.path.join(test_subdir, "old_test_file_2.txt")
        
        with open(old_file1, 'w') as f:
            f.write("Test content 1" * 1000)
        with open(old_file2, 'w') as f:
            f.write("Test content 2" * 1000)
        
        # Make files appear old (48 hours)
        old_time = time.time() - (48 * 3600)
        os.utime(old_file1, (old_time, old_time))
        os.utime(old_file2, (old_time, old_time))
        
        print(f"  ✓ Created 2 old test files")
        print(f"  ✓ Files timestamped 48 hours ago")
        
        # Run cleanup with 24 hour threshold
        qm = QueueManager()
        removed = qm.cleanup_old_files(max_age_hours=24)
        
        print(f"  ✓ Cleanup executed: {removed} files removed")
        
        # Verify files were removed
        if not os.path.exists(old_file1) and not os.path.exists(old_file2):
            print("  ✅ TEST 1 PASSED: Old files successfully removed")
        else:
            print("  ❌ TEST 1 FAILED: Old files still exist")
            return False
        
        # Test 2: Create recent files  
        print("\n[TEST 2] Testing recent file preservation...")
        recent_file = os.path.join(test_subdir, "recent_test_file.txt")
        
        with open(recent_file, 'w') as f:
            f.write("Recent content" * 1000)
        
        print(f"  ✓ Created 1 recent test file")
        
        # Run cleanup - should not remove recent file
        removed = qm.cleanup_old_files(max_age_hours=24)
        
        print(f"  ✓ Cleanup executed: {removed} files removed")
        
        if os.path.exists(recent_file) and removed == 0:
            print("  ✅ TEST 2 PASSED: Recent file preserved")
        else:
            print("  ❌ TEST 2 FAILED: Recent file was removed or count incorrect")
            return False
        
        # Clean up our test file
        os.remove(recent_file)
        
        # Test 3: Test extraction directory cleanup
        print("\n[TEST 3] Testing orphaned extraction directory cleanup...")
        
        # Create an extraction-like directory directly in DATA_DIR
        # (not in test_subdir, since cleanup only looks at DATA_DIR children)
        extraction_dir = os.path.join(DATA_DIR, "test_archive_cleanup_extracted")
        os.makedirs(extraction_dir, exist_ok=True)
        
        # Add some files to it
        for i in range(3):
            test_file = os.path.join(extraction_dir, f"extracted_file_{i}.txt")
            with open(test_file, 'w') as f:
                f.write(f"Extracted content {i}" * 1000)
        
        # Make directory appear old (over 1 hour)
        very_old_time = time.time() - (2 * 3600)  # 2 hours old
        for root, dirs, files in os.walk(extraction_dir):
            for file in files:
                file_path = os.path.join(root, file)
                os.utime(file_path, (very_old_time, very_old_time))
        
        print(f"  ✓ Created orphaned extraction directory with 3 files")
        print(f"  ✓ Directory timestamped as old (2 hours)")
        
        # Run extraction cleanup
        removed_dirs = qm.cleanup_failed_upload_files()
        
        print(f"  ✓ Cleanup executed: {len(removed_dirs)} directories removed")
        
        if not os.path.exists(extraction_dir) and len(removed_dirs) > 0:
            print("  ✅ TEST 3 PASSED: Orphaned directory removed")
        else:
            print(f"  ❌ TEST 3 FAILED: Orphaned directory still exists")
            if os.path.exists(extraction_dir):
                # Clean it up manually for next run
                shutil.rmtree(extraction_dir)
            return False
        
        # Test 4: Test TORBOX_DIR existence
        print("\n[TEST 4] Testing TORBOX_DIR structure...")
        
        if os.path.exists(TORBOX_DIR):
            print(f"  ✓ TORBOX_DIR exists: {TORBOX_DIR}")
            print("  ✅ TEST 4 PASSED: TORBOX_DIR properly configured")
        else:
            print(f"  ❌ TEST 4 FAILED: TORBOX_DIR missing: {TORBOX_DIR}")
            return False
        
        print("\n" + "=" * 70)
        print("✅ ALL INTEGRATION TESTS PASSED!")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED WITH EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Clean up test directory
        if os.path.exists(test_subdir):
            try:
                shutil.rmtree(test_subdir)
                print(f"\n🧹 Cleaned up test directory")
            except Exception as e:
                print(f"\n⚠️ Warning: Could not clean up test directory: {e}")


def test_command_handlers_exist():
    """Test that cleanup command handlers are properly imported."""
    print("\n" + "=" * 70)
    print("INTEGRATION TEST: Command Handler Imports")
    print("=" * 70)
    
    try:
        from utils.command_handlers import (
            handle_cleanup_command,
            handle_cleanup_orphans_command,
            handle_confirm_cleanup_command
        )
        
        print("\n✓ handle_cleanup_command imported")
        print("✓ handle_cleanup_orphans_command imported")
        print("✓ handle_confirm_cleanup_command imported")
        
        # Check if they're callable
        assert callable(handle_cleanup_command), "handle_cleanup_command not callable"
        assert callable(handle_cleanup_orphans_command), "handle_cleanup_orphans_command not callable"
        assert callable(handle_confirm_cleanup_command), "handle_confirm_cleanup_command not callable"
        
        print("\n✅ All command handlers are callable")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n❌ Command handler test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all integration tests."""
    print("\n🚀 Starting Integration Tests for Cleanup Functionality\n")
    
    results = []
    
    # Test 1: Command handlers
    results.append(("Command Handlers", test_command_handlers_exist()))
    
    # Test 2: Cleanup functionality
    results.append(("Cleanup Functionality", test_cleanup_with_temporary_files()))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False
    
    print("=" * 70)
    
    if all_passed:
        print("\n✅ ALL INTEGRATION TESTS PASSED!")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
