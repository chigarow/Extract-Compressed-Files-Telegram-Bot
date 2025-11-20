#!/usr/bin/env python3
"""
Automated export verification script.
Checks that all public functions in command_handlers.py are properly exported from utils.

This should be run as part of CI/CD or pre-commit hooks to catch missing exports early.
"""

import sys
import os
import inspect

# Add script directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

print("=" * 80)
print("AUTOMATED EXPORT VERIFICATION")
print("Checking all command_handlers functions are exported from utils...")
print("=" * 80)

try:
    import utils.command_handlers as ch
    import utils
    
    # Find all functions in command_handlers that should be exported
    handlers = [
        name for name, obj in inspect.getmembers(ch) 
        if inspect.isfunction(obj) and name.startswith('handle_')
    ]
    
    print(f"\nFound {len(handlers)} command handler functions in command_handlers.py:")
    for handler in sorted(handlers):
        print(f"  • {handler}")
    
    print(f"\nVerifying all are exported from utils package...")
    
    missing_exports = []
    for handler in handlers:
        if not hasattr(utils, handler):
            missing_exports.append(handler)
            print(f"  ❌ {handler} - NOT EXPORTED")
        else:
            print(f"  ✓ {handler} - exported")
    
    print("\n" + "=" * 80)
    
    if missing_exports:
        print("❌ EXPORT VERIFICATION FAILED!")
        print(f"\n{len(missing_exports)} function(s) not exported from utils:")
        for func in missing_exports:
            print(f"  • {func}")
        print("\nTo fix this, add the missing functions to:")
        print("  1. The import statement in utils/__init__.py")
        print("  2. The __all__ list in utils/__init__.py")
        print("=" * 80)
        sys.exit(1)
    else:
        print("✅ EXPORT VERIFICATION PASSED!")
        print(f"\nAll {len(handlers)} command handlers are properly exported.")
        print("=" * 80)
        sys.exit(0)
        
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    print("\n" + "=" * 80)
    print("❌ EXPORT VERIFICATION FAILED")
    print("=" * 80)
    sys.exit(1)
