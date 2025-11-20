#!/usr/bin/env python3
"""
Verification script to test the exact import that was failing in production.
This simulates the import statement from extract-compressed-files.py line 34.
"""

import sys
import os

# Add script directory to path (same as main file)
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

print("=" * 80)
print("IMPORT VERIFICATION TEST")
print("Testing the exact import that was failing in production...")
print("=" * 80)

try:
    # This is the EXACT import from extract-compressed-files.py that was failing
    from utils import (
        handle_cleanup_command, 
        handle_confirm_cleanup_command, 
        handle_cleanup_orphans_command
    )
    
    print("\n✅ SUCCESS: All cleanup command handlers imported successfully!")
    print(f"   - handle_cleanup_command: {handle_cleanup_command}")
    print(f"   - handle_confirm_cleanup_command: {handle_confirm_cleanup_command}")
    print(f"   - handle_cleanup_orphans_command: {handle_cleanup_orphans_command}")
    
    # Verify they are callable
    assert callable(handle_cleanup_command), "handle_cleanup_command not callable"
    assert callable(handle_confirm_cleanup_command), "handle_confirm_cleanup_command not callable"
    assert callable(handle_cleanup_orphans_command), "handle_cleanup_orphans_command not callable"
    
    print("\n✅ All functions are callable")
    
    # Verify they are async
    import inspect
    assert inspect.iscoroutinefunction(handle_cleanup_command), "handle_cleanup_command not async"
    assert inspect.iscoroutinefunction(handle_confirm_cleanup_command), "handle_confirm_cleanup_command not async"
    assert inspect.iscoroutinefunction(handle_cleanup_orphans_command), "handle_cleanup_orphans_command not async"
    
    print("✅ All functions are async (coroutines)")
    
    print("\n" + "=" * 80)
    print("✅ IMPORT VERIFICATION COMPLETE - FIX IS WORKING!")
    print("=" * 80)
    
    sys.exit(0)
    
except ImportError as e:
    print(f"\n❌ FAILED: ImportError occurred!")
    print(f"   Error: {e}")
    print("\n" + "=" * 80)
    print("❌ IMPORT VERIFICATION FAILED")
    print("=" * 80)
    sys.exit(1)
    
except Exception as e:
    print(f"\n❌ FAILED: Unexpected error occurred!")
    print(f"   Error: {e}")
    import traceback
    traceback.print_exc()
    print("\n" + "=" * 80)
    print("❌ IMPORT VERIFICATION FAILED")
    print("=" * 80)
    sys.exit(1)
