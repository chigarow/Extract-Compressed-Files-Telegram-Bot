#!/usr/bin/env python3
"""
Quick syntax validation for interactive login implementation.
This script validates that the interactive login code has no syntax errors.
"""

import ast
import sys

def validate_syntax(filename):
    """Validate Python syntax by parsing the file."""
    try:
        with open(filename, 'r') as f:
            code = f.read()
        
        # Try to parse the file
        ast.parse(code)
        print(f"✅ SUCCESS: {filename} has valid Python syntax")
        return True
    except SyntaxError as e:
        print(f"❌ SYNTAX ERROR in {filename}:")
        print(f"   Line {e.lineno}: {e.msg}")
        print(f"   Text: {e.text}")
        return False
    except Exception as e:
        print(f"❌ ERROR validating {filename}: {e}")
        return False

def check_login_functions():
    """Check that the login functions are properly defined."""
    try:
        # Add current directory to path
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        
        # Import using importlib to handle the filename with dashes
        import importlib.util
        spec = importlib.util.spec_from_file_location("main_module", "extract-compressed-files.py")
        main_module = importlib.util.module_from_spec(spec)
        
        print("   Loading module...")
        # Note: We can't fully execute it without dependencies, but we can parse it
        # So let's just check the file directly
        with open('extract-compressed-files.py', 'r') as f:
            content = f.read()
        
        # Check for the required functions
        required_items = [
            'def create_interactive_login_handlers():',
            'async def handle_login_response(event):',
            'async def main_async():',
            "login_state = {"
        ]
        
        for item in required_items:
            if item in content:
                print(f"✅ Found: {item.strip()}")
            else:
                print(f"❌ Missing: {item.strip()}")
                return False
        
        # Check for the specific login handlers
        if 'async def phone_callback():' in content:
            print("✅ Found: phone_callback function")
        else:
            print("❌ Missing: phone_callback function")
            return False
            
        if 'async def code_callback():' in content:
            print("✅ Found: code_callback function")
        else:
            print("❌ Missing: code_callback function")
            return False
            
        if 'async def password_callback():' in content:
            print("✅ Found: password_callback function")
        else:
            print("❌ Missing: password_callback function")
            return False
        
        return True
    except Exception as e:
        print(f"❌ ERROR checking functions: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("INTERACTIVE LOGIN SYNTAX VALIDATION")
    print("=" * 60)
    print()
    
    # Validate syntax
    print("1. Validating Python syntax...")
    syntax_ok = validate_syntax('extract-compressed-files.py')
    print()
    
    if not syntax_ok:
        print("❌ FAILED: Syntax errors found")
        sys.exit(1)
    
    # Check functions
    print("2. Checking login functions...")
    functions_ok = check_login_functions()
    print()
    
    if not functions_ok:
        print("❌ FAILED: Missing required functions or globals")
        sys.exit(1)
    
    print("=" * 60)
    print("✅ ALL CHECKS PASSED!")
    print("=" * 60)
    print()
    print("The interactive login implementation is syntactically correct.")
    print("You can now test it by running the script.")
    sys.exit(0)
