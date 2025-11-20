#!/usr/bin/env python3
"""
Final Test Report Generator
Runs all verification tests and generates a comprehensive report.
"""

import subprocess
import sys

def run_test(name, command):
    """Run a test and return success status."""
    print(f"\n{'='*80}")
    print(f"Running: {name}")
    print(f"{'='*80}")
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        
        success = result.returncode == 0
        return success
    except subprocess.TimeoutExpired:
        print(f"❌ Test timed out after 30 seconds")
        return False
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        return False

def main():
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║                        FINAL TEST REPORT GENERATOR                           ║
║                   ImportError Fix Verification Suite                         ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
    
    tests = [
        ("Import Verification", "python3 verify_import_fix.py"),
        ("Export Verification", "python3 check_exports.py"),
        ("All Imports Test", "python3 test_all_imports.py"),
        ("Cleanup Validation", "python3 test_cleanup_validation.py"),
        ("Import Unit Tests", "python3 -m pytest tests/test_cleanup_imports.py -v"),
        ("Integration Tests", "python3 run_integration_tests.py"),
        ("Syntax Check", "python3 -m py_compile extract-compressed-files.py"),
    ]
    
    results = []
    
    for test_name, command in tests:
        success = run_test(test_name, command)
        results.append((test_name, success))
    
    # Generate Summary
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}\n")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    print(f"Test Results: {passed}/{total} passed\n")
    
    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status:12} {test_name}")
    
    print(f"\n{'='*80}")
    
    if passed == total:
        print("✅ ALL TESTS PASSED - FIX IS PRODUCTION READY")
        print(f"{'='*80}\n")
        return 0
    else:
        print(f"❌ {total - passed} TEST(S) FAILED - REVIEW REQUIRED")
        print(f"{'='*80}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
