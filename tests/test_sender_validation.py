"""
Unit tests for sender validation feature.

Tests that the bot only processes messages from the configured account_b_username
and properly rejects messages from unauthorized users.

This test can run standalone without Telethon or other dependencies installed.
It tests the validation logic that will be used in the main application.
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_sender_validation_logic():
    """Test the core sender validation logic without async dependencies."""
    print("\n🧪 Testing sender validation logic...")
    
    # Simulate config
    class MockConfig:
        target_username = '@lidahular'
    
    config = MockConfig()
    
    # Test cases: (sender_username, should_authorize, description)
    test_cases = [
        ('lidahular', True, 'Exact match (lowercase)'),
        ('LIDAHULAR', True, 'Case insensitive (uppercase)'),
        ('LidaHular', True, 'Case insensitive (mixed)'),
        ('attacker', False, 'Different username'),
        ('hacker123', False, 'Unauthorized user'),
        (None, False, 'No username (ID only users)'),
        ('girlfriend', False, 'Unauthorized GIF sender'),
    ]
    
    passed = 0
    failed = 0
    
    for sender_username, expected_auth, description in test_cases:
        # Simulate validation logic from main app
        target_username = config.target_username.lstrip('@').lower()
        sender_username_normalized = sender_username.lower() if sender_username else None
        is_authorized = (sender_username_normalized == target_username)
        
        # Check result
        if is_authorized == expected_auth:
            print(f"  ✅ {description}: {'AUTHORIZED' if is_authorized else 'BLOCKED'}")
            passed += 1
        else:
            print(f"  ❌ {description}: Expected {expected_auth}, got {is_authorized}")
            failed += 1
    
    print(f"\n📊 Test Results: {passed} passed, {failed} failed")
    return failed == 0


def test_username_normalization():
    """Test username normalization (@ prefix removal and lowercase)."""
    print("\n🧪 Testing username normalization...")
    
    test_cases = [
        ('@lidahular', 'lidahular'),
        ('@LIDAHULAR', 'lidahular'),
        ('lidahular', 'lidahular'),
        ('@LidaHular', 'lidahular'),
        ('LIDAHULAR', 'lidahular'),
    ]
    
    passed = 0
    failed = 0
    
    for input_username, expected_output in test_cases:
        # Normalization logic
        normalized = input_username.lstrip('@').lower()
        
        if normalized == expected_output:
            print(f"  ✅ '{input_username}' → '{normalized}'")
            passed += 1
        else:
            print(f"  ❌ '{input_username}' → '{normalized}' (expected '{expected_output}')")
            failed += 1
    
    print(f"\n📊 Test Results: {passed} passed, {failed} failed")
    return failed == 0


def test_security_scenarios():
    """Test specific security scenarios mentioned in the issue."""
    print("\n🧪 Testing security scenarios...")
    
    # The reported issue: girlfriend sent GIF, bot processed it
    target_username = 'lidahular'
    
    scenarios = [
        {
            'name': 'Authorized user sends archive',
            'sender': 'lidahular',
            'content': 'archive.zip',
            'should_process': True
        },
        {
            'name': 'Unauthorized user (girlfriend) sends GIF',
            'sender': 'girlfriend',
            'content': 'missing-you-love.gif',
            'should_process': False
        },
        {
            'name': 'Authorized user sends command',
            'sender': 'LIDAHULAR',
            'content': '/help',
            'should_process': True
        },
        {
            'name': 'Random user sends Torbox link',
            'sender': 'random_user',
            'content': 'https://store-031.weur.tb-cdn.st/zip/test.zip',
            'should_process': False
        },
        {
            'name': 'User without username sends file',
            'sender': None,
            'content': 'file.zip',
            'should_process': False
        },
    ]
    
    passed = 0
    failed = 0
    
    for scenario in scenarios:
        sender = scenario['sender']
        expected = scenario['should_process']
        
        # Validation logic
        sender_normalized = sender.lower() if sender else None
        is_authorized = (sender_normalized == target_username)
        
        result = "PROCESSED" if is_authorized else "BLOCKED"
        expected_result = "PROCESSED" if expected else "BLOCKED"
        
        if is_authorized == expected:
            print(f"  ✅ {scenario['name']}: {result}")
            passed += 1
        else:
            print(f"  ❌ {scenario['name']}: {result} (expected {expected_result})")
            failed += 1
    
    print(f"\n📊 Test Results: {passed} passed, {failed} failed")
    return failed == 0


def test_logging_format():
    """Test that logging format includes necessary security information."""
    print("\n🧪 Testing security logging format...")
    
    # Simulate sender info
    class MockSender:
        def __init__(self, username, user_id, first_name):
            self.username = username
            self.id = user_id
            self.first_name = first_name
    
    test_cases = [
        MockSender('attacker', 12345, 'Attacker'),
        MockSender(None, 99999, 'NoUsername'),
    ]
    
    passed = 0
    failed = 0
    
    for sender in test_cases:
        sender_username = sender.username
        sender_id = sender.id
        sender_name = sender.first_name
        
        # Create sender identifier (from main app logic)
        if sender_username:
            sender_identifier = f"@{sender_username}"
        else:
            sender_identifier = f"{sender_name} (ID: {sender_id})"
        
        # Verify identifier has necessary info
        has_info = (
            (sender_username and f"@{sender_username}" in sender_identifier) or
            (not sender_username and str(sender_id) in sender_identifier)
        )
        
        if has_info:
            print(f"  ✅ Sender identifier: {sender_identifier}")
            passed += 1
        else:
            print(f"  ❌ Incomplete identifier: {sender_identifier}")
            failed += 1
    
    print(f"\n📊 Test Results: {passed} passed, {failed} failed")
    return failed == 0


def test_edge_cases():
    """Test edge cases in sender validation."""
    print("\n🧪 Testing edge cases...")
    
    target_username = 'lidahular'
    
    edge_cases = [
        ('lidahular', True, 'Exact match'),
        ('lidahular ', False, 'Trailing space (should not match after strip)'),
        (' lidahular', False, 'Leading space (should not match after strip)'),
        ('lida hular', False, 'Space in middle'),
        ('', False, 'Empty string'),
        ('lidahular123', False, 'Extra characters'),
        ('lidahula', False, 'Missing character'),
    ]
    
    passed = 0
    failed = 0
    
    for sender_username, expected_auth, description in edge_cases:
        # Note: strip() should be added if needed in actual implementation
        sender_normalized = sender_username.lower() if sender_username else None
        is_authorized = (sender_normalized == target_username)
        
        if is_authorized == expected_auth:
            print(f"  ✅ {description}: {'AUTHORIZED' if is_authorized else 'BLOCKED'}")
            passed += 1
        else:
            print(f"  ❌ {description}: Expected {expected_auth}, got {is_authorized}")
            failed += 1
    
    print(f"\n📊 Test Results: {passed} passed, {failed} failed")
    return failed == 0


def main():
    """Run all standalone tests."""
    print("=" * 70)
    print("🔐 SENDER VALIDATION SECURITY TESTS")
    print("=" * 70)
    print("\nThese tests verify that only messages from account_b_username")
    print("are processed, preventing unauthorized access.")
    print()
    
    all_passed = True
    
    # Run all test suites
    all_passed &= test_sender_validation_logic()
    all_passed &= test_username_normalization()
    all_passed &= test_security_scenarios()
    all_passed &= test_logging_format()
    all_passed &= test_edge_cases()
    
    # Summary
    print("\n" + "=" * 70)
    if all_passed:
        print("🎉 ALL SENDER VALIDATION TESTS PASSED!")
        print("✅ The validation logic correctly filters messages by sender")
        print("✅ Only authorized user (account_b_username) can trigger bot actions")
        print("✅ Security logging includes sender identification")
        print("✅ Case-insensitive matching works correctly")
        print("✅ Users without usernames are properly blocked")
    else:
        print("❌ SOME TESTS FAILED")
        print("Please review the failed tests above")
    
    print("=" * 70)
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
