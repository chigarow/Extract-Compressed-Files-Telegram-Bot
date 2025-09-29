#!/usr/bin/env python3
"""
Test script specifically for the /compression-timeout command fix
"""

import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_compression_timeout_command():
    """Test the new /compression-timeout command"""
    print("🧪 Testing /compression-timeout command...")
    
    try:
        from utils.command_handlers import handle_compression_timeout_command, _parse_timeout_value
        
        # Test the parsing function
        print("  📊 Testing timeout value parsing...")
        
        test_cases = [
            ("300", 300),
            ("5m", 300),
            ("120m", 7200),
            ("2h", 7200),
            ("1h30m", 5400),
            ("600s", 600),
            ("10m", 600),
            ("1h", 3600)
        ]
        
        for input_val, expected in test_cases:
            result = _parse_timeout_value(input_val)
            assert result == expected, f"Expected {expected} for {input_val}, got {result}"
            print(f"    ✅ {input_val} -> {result}s")
        
        # Test the command handler
        print("  📞 Testing command handler...")
        
        mock_event = MagicMock()
        mock_event.reply = AsyncMock()
        
        # Test successful timeout setting
        await handle_compression_timeout_command(mock_event, "10m")
        
        # Check that reply was called
        assert mock_event.reply.called, "Command handler should reply"
        reply_text = mock_event.reply.call_args[0][0]
        assert "600s" in reply_text, f"Reply should mention 600s, got: {reply_text}"
        print("    ✅ Command handler executed successfully")
        
        # Test invalid input
        mock_event.reply.reset_mock()
        await handle_compression_timeout_command(mock_event, "invalid")
        
        assert mock_event.reply.called, "Command handler should reply to invalid input"
        reply_text = mock_event.reply.call_args[0][0]
        assert "Invalid timeout value" in reply_text, f"Should indicate invalid input, got: {reply_text}"
        print("    ✅ Invalid input handled correctly")
        
        print("✅ /compression-timeout command test PASSED")
        return True
        
    except Exception as e:
        print(f"❌ /compression-timeout command test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_import_in_main_file():
    """Test that the command is properly imported in main file"""
    print("🔍 Testing command import in main file...")
    
    try:
        # Check if the command can be imported
        from extract_compressed_files import handle_compression_timeout_command
        print("✅ Command can be imported from main file")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

def test_config_integration():
    """Test that the compression timeout integrates with config"""
    print("⚙️  Testing config integration...")
    
    try:
        from config import config
        
        # Check that compression timeout attribute exists
        timeout = getattr(config, 'compression_timeout_seconds', None)
        if timeout is not None:
            print(f"✅ Config has compression_timeout_seconds: {timeout}")
            return True
        else:
            print("⚠️  compression_timeout_seconds not found in config")
            return False
            
    except Exception as e:
        print(f"❌ Config integration test failed: {e}")
        return False

async def main():
    """Main test function"""
    print("🚀 Testing Compression Timeout Command Implementation")
    print("=" * 60)
    
    tests = [
        ("Compression Timeout Command", test_compression_timeout_command()),
        ("Main File Import", test_import_in_main_file()),
        ("Config Integration", test_config_integration())
    ]
    
    results = []
    for test_name, test_coro in tests:
        print(f"\n📋 Running: {test_name}")
        try:
            if asyncio.iscoroutine(test_coro):
                result = await test_coro
            else:
                result = test_coro
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {test_name}")
        if result:
            passed += 1
    
    total = len(results)
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! The /compression-timeout command is working correctly.")
        print("\n💡 Command usage examples:")
        print("  /compression-timeout 300     # 5 minutes")
        print("  /compression-timeout 5m      # 5 minutes") 
        print("  /compression-timeout 2h      # 2 hours")
        print("  /compression-timeout 1h30m   # 1 hour 30 minutes")
        return True
    else:
        print(f"\n❌ {total - passed} test(s) failed. Please check the implementation.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)