#!/usr/bin/env python3
"""Quick validation test for cleanup functionality."""

import os
import sys
import time

# Add script directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from utils.queue_manager import QueueManager
from utils.constants import DATA_DIR, TORBOX_DIR

def test_cleanup_methods():
    """Test that cleanup methods exist and are callable."""
    print("🧪 Testing cleanup functionality validation...")
    
    qm = QueueManager()
    
    # Test 1: Check methods exist
    print("\n1️⃣ Checking cleanup methods exist...")
    assert hasattr(qm, 'cleanup_old_files'), "❌ cleanup_old_files method missing"
    assert hasattr(qm, 'cleanup_failed_upload_files'), "❌ cleanup_failed_upload_files method missing"
    print("✅ Both cleanup methods exist")
    
    # Test 2: Check methods are callable
    print("\n2️⃣ Checking methods are callable...")
    assert callable(qm.cleanup_old_files), "❌ cleanup_old_files not callable"
    assert callable(qm.cleanup_failed_upload_files), "❌ cleanup_failed_upload_files not callable"
    print("✅ Both methods are callable")
    
    # Test 3: Test cleanup_old_files with no files
    print("\n3️⃣ Testing cleanup_old_files (dry run)...")
    try:
        removed = qm.cleanup_old_files(max_age_hours=999999)  # Very old age to avoid deleting anything
        print(f"✅ cleanup_old_files executed: {removed} files removed")
    except Exception as e:
        print(f"❌ cleanup_old_files failed: {e}")
        return False
    
    # Test 4: Test cleanup_failed_upload_files
    print("\n4️⃣ Testing cleanup_failed_upload_files (dry run)...")
    try:
        removed_dirs = qm.cleanup_failed_upload_files()
        print(f"✅ cleanup_failed_upload_files executed: {len(removed_dirs)} directories removed")
    except Exception as e:
        print(f"❌ cleanup_failed_upload_files failed: {e}")
        return False
    
    # Test 5: Check directory structure
    print("\n5️⃣ Checking directory structure...")
    print(f"DATA_DIR: {DATA_DIR}")
    print(f"TORBOX_DIR: {TORBOX_DIR}")
    print(f"DATA_DIR exists: {os.path.exists(DATA_DIR)}")
    print(f"TORBOX_DIR exists: {os.path.exists(TORBOX_DIR)}")
    
    # Test 6: Check command handler imports
    print("\n6️⃣ Testing command handler imports...")
    try:
        from utils.command_handlers import (
            handle_cleanup_command, 
            handle_cleanup_orphans_command,
            handle_confirm_cleanup_command
        )
        print("✅ All cleanup command handlers imported successfully")
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False
    
    print("\n✅ All cleanup functionality validation tests passed!")
    return True

if __name__ == "__main__":
    try:
        success = test_cleanup_methods()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
