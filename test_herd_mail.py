#!/usr/bin/env python3
"""
Unit tests for herd_mail.py

Run with: python3 -m pytest test_herd_mail.py -v
Or: python3 test_herd_mail.py (for basic validation)

These tests mock SMTP/IMAP so they run without real credentials.
"""

import os
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Ensure we can import the module under test
sys.path.insert(0, str(Path(__file__).parent))

import herd_mail as hm


class TestEmailValidation(unittest.TestCase):
    """Test email address validation."""

    def test_valid_email(self):
        """Test valid email addresses."""
        valid_emails = [
            "user@example.com",
            "test.user@example.com",
            "user+tag@example.co.uk",
            "user123@test-domain.com",
        ]
        for email in valid_emails:
            with self.subTest(email=email):
                self.assertTrue(hm.validate_email_address(email))

    def test_invalid_email(self):
        """Test invalid email addresses."""
        invalid_emails = [
            "",
            "notanemail",
            "@example.com",
            "user@",
            "user@domain",  # No TLD
            "user\n@example.com",  # Newline injection
            "user\r@example.com",  # CR injection
            "user\t@example.com",  # Tab injection
            "user\0@example.com",  # Null byte
            None,
        ]
        for email in invalid_emails:
            with self.subTest(email=email):
                self.assertFalse(hm.validate_email_address(email))

    def test_email_list_validation(self):
        """Test comma-separated email list validation."""
        self.assertTrue(hm.validate_email_list("user1@example.com,user2@example.com"))
        self.assertTrue(hm.validate_email_list("user@example.com"))
        self.assertTrue(hm.validate_email_list(""))  # Empty is ok
        self.assertFalse(hm.validate_email_list("valid@example.com,invalid"))
        self.assertFalse(hm.validate_email_list("user@,another@example.com"))


class TestSanitization(unittest.TestCase):
    """Test terminal output sanitization."""

    def test_sanitize_for_display(self):
        """Test sanitization removes control characters."""
        # Test control character removal
        self.assertEqual(hm.sanitize_for_display("hello\x1b[31mworld"), "helloworld")

        # Test newline and tab are kept
        self.assertEqual(hm.sanitize_for_display("hello\nworld"), "hello\nworld")
        self.assertEqual(hm.sanitize_for_display("hello\tworld"), "hello\tworld")

        # Test truncation
        long_text = "a" * 300
        result = hm.sanitize_for_display(long_text, max_length=200)
        self.assertEqual(len(result), 203)  # 200 + "..."
        self.assertTrue(result.endswith("..."))

        # Test empty string
        self.assertEqual(hm.sanitize_for_display(""), "")


class TestFilePathValidation(unittest.TestCase):
    """Test file path validation."""

    def test_valid_file_path(self):
        """Test validation of valid file paths."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
            f.write(b"test content")

        try:
            result = hm.validate_file_path(temp_path, must_exist=True)
            self.assertIsNotNone(result)
            self.assertTrue(result.exists())
        finally:
            os.unlink(temp_path)

    def test_nonexistent_file(self):
        """Test validation fails for nonexistent file."""
        result = hm.validate_file_path("/tmp/nonexistent_file_12345.txt", must_exist=True)
        self.assertIsNone(result)

    def test_directory_instead_of_file(self):
        """Test validation fails for directory."""
        result = hm.validate_file_path("/tmp", must_exist=True)
        self.assertIsNone(result)

    def test_sensitive_path_blocked(self):
        """Test that sensitive system paths are blocked."""
        sensitive_paths = ["/etc/passwd", "/sys/kernel", "/proc/self", "/dev/null"]
        for path in sensitive_paths:
            with self.subTest(path=path):
                result = hm.validate_file_path(path, must_exist=False)
                self.assertIsNone(result)


class TestEscapeSequences(unittest.TestCase):
    """Test escape sequence handling."""

    def test_decode_escape_sequences(self):
        """Test common escape sequences are decoded."""
        self.assertEqual(hm.decode_escape_sequences("hello\\nworld"), "hello\nworld")
        self.assertEqual(hm.decode_escape_sequences("hello\\tworld"), "hello\tworld")
        self.assertEqual(hm.decode_escape_sequences("hello\\rworld"), "hello\rworld")
        self.assertEqual(hm.decode_escape_sequences("hello\\\\world"), "hello\\world")
        self.assertEqual(hm.decode_escape_sequences('say \\"hello\\"'), 'say "hello"')
        self.assertEqual(hm.decode_escape_sequences("say \\'hello\\'"), "say 'hello'")

    def test_multiple_escape_sequences(self):
        """Test multiple escape sequences in one string."""
        result = hm.decode_escape_sequences("line1\\nline2\\tindented\\\\backslash")
        self.assertEqual(result, "line1\nline2\tindented\\backslash")


class TestPortParsing(unittest.TestCase):
    """Test port number parsing and validation."""

    def test_valid_ports(self):
        """Test valid port numbers."""
        self.assertEqual(hm.parse_port("465", 0, "test"), 465)
        self.assertEqual(hm.parse_port("993", 0, "test"), 993)
        self.assertEqual(hm.parse_port("1", 0, "test"), 1)
        self.assertEqual(hm.parse_port("65535", 0, "test"), 65535)

    def test_invalid_ports(self):
        """Test invalid port numbers raise ValueError."""
        with self.assertRaises(ValueError):
            hm.parse_port("0", 0, "test")  # Too low

        with self.assertRaises(ValueError):
            hm.parse_port("65536", 0, "test")  # Too high

        with self.assertRaises(ValueError):
            hm.parse_port("not_a_number", 0, "test")

        with self.assertRaises(ValueError):
            hm.parse_port("-1", 0, "test")


class TestConfig(unittest.TestCase):
    """Test configuration loading and validation."""

    def setUp(self):
        # Clear environment before each test
        self.clear_env()

    def tearDown(self):
        self.clear_env()

    def clear_env(self):
        """Remove WAGGLE_ env vars."""
        for key in list(os.environ.keys()):
            if key.startswith("WAGGLE_"):
                del os.environ[key]

    def test_get_config_defaults(self):
        """Test config loads with default values."""
        # Set minimal required vars
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"

        cfg = hm.get_config()

        self.assertEqual(cfg["smtp_host"], "smtp.example.com")
        self.assertEqual(cfg["smtp_port"], 465)  # default
        self.assertEqual(cfg["smtp_user"], "user@example.com")
        self.assertEqual(cfg["smtp_pass"], "secret")
        self.assertEqual(cfg["from_addr"], "user@example.com")
        self.assertEqual(cfg["from_name"], "")  # default
        self.assertTrue(cfg["use_tls"])  # default
        self.assertIsNone(cfg["imap_host"])  # optional
        self.assertEqual(cfg["imap_port"], 993)  # default

    def test_get_config_invalid_port(self):
        """Test config fails with invalid port."""
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_PORT"] = "invalid"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"

        with self.assertRaises(ValueError):
            hm.get_config()

    def test_validate_config_missing_required(self):
        """Test validation fails when required fields missing."""
        cfg = {
            "smtp_host": "",
            "smtp_user": "user@example.com",
            "smtp_pass": "secret",
            "from_addr": "user@example.com",
        }

        result = hm.validate_config(cfg)
        self.assertFalse(result)

    def test_validate_config_invalid_from_addr(self):
        """Test validation fails with invalid from_addr."""
        cfg = {
            "smtp_host": "smtp.example.com",
            "smtp_user": "user@example.com",
            "smtp_pass": "secret",
            "from_addr": "not_an_email",
        }

        result = hm.validate_config(cfg)
        self.assertFalse(result)

    def test_validate_config_complete(self):
        """Test validation passes with complete config."""
        cfg = {
            "smtp_host": "smtp.example.com",
            "smtp_user": "user@example.com",
            "smtp_pass": "secret",
            "from_addr": "user@example.com",
            "from_name": "Test User",
            "use_tls": True,
        }

        result = hm.validate_config(cfg)
        self.assertTrue(result)


class TestWaggleConfig(unittest.TestCase):
    """Test conversion to waggle's config format."""

    def test_build_waggle_config(self):
        """Test our config converts to waggle format correctly."""
        cfg = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_user": "user@example.com",
            "smtp_pass": "secret",
            "from_addr": "user@example.com",
            "from_name": "Test User",
            "use_tls": True,
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "imap_tls": True,
        }

        waggle_cfg = hm.build_waggle_config(cfg)

        self.assertEqual(waggle_cfg["host"], "smtp.example.com")
        self.assertEqual(waggle_cfg["port"], 587)
        self.assertEqual(waggle_cfg["user"], "user@example.com")
        self.assertEqual(waggle_cfg["password"], "secret")
        self.assertEqual(waggle_cfg["from_addr"], "user@example.com")
        self.assertEqual(waggle_cfg["from_name"], "Test User")
        self.assertTrue(waggle_cfg["tls"])
        self.assertEqual(waggle_cfg["imap_host"], "imap.example.com")


class TestMain(unittest.TestCase):
    """Test main() function with mocked dependencies."""

    def setUp(self):
        self.clear_env()
        self.setup_mock_env()
        # Mock waggle availability for tests
        self.waggle_patch = patch('herd_mail.WAGGLE_AVAILABLE', True)
        self.waggle_patch.start()

    def tearDown(self):
        self.waggle_patch.stop()
        self.clear_env()

    def clear_env(self):
        """Remove WAGGLE_ env vars."""
        for key in list(os.environ.keys()):
            if key.startswith("WAGGLE_"):
                del os.environ[key]

    def setup_mock_env(self):
        """Set up minimal valid environment."""
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"

    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_send_simple_email(self, mock_check_duplicate, mock_send):
        """Test sending a simple email."""
        mock_check_duplicate.return_value = False
        mock_send.return_value = None

        with patch('sys.argv', ['herd_mail.py', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi there!']):
            result = hm.main()

        self.assertEqual(result, 0)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs['to'], 'friend@example.com')
        self.assertEqual(call_kwargs['subject'], 'Hello')
        self.assertEqual(call_kwargs['body_md'], 'Hi there!')

    @patch('herd_mail.check_recently_sent')
    def test_duplicate_detection(self, mock_check_duplicate):
        """Test duplicate detection prevents send."""
        mock_check_duplicate.return_value = True

        with patch('sys.argv', ['herd_mail.py', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi!']):
            result = hm.main()

        self.assertEqual(result, 0)  # Not an error, just skipped

    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_skip_duplicate_check(self, mock_check_duplicate, mock_send):
        """Test --skip-duplicate-check bypasses detection."""
        mock_send.return_value = None

        with patch('sys.argv', ['herd_mail.py', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi!',
                                '--skip-duplicate-check']):
            result = hm.main()

        self.assertEqual(result, 0)
        mock_check_duplicate.assert_not_called()
        mock_send.assert_called_once()

    def test_dry_run(self):
        """Test --dry-run validates without sending."""
        with patch('sys.argv', ['herd_mail.py', '--dry-run', '--to', 'test@example.com',
                                '--subject', 'Test']):
            result = hm.main()

        self.assertEqual(result, 0)

    def test_missing_config(self):
        """Test error when config incomplete."""
        self.clear_env()
        # Don't set any env vars

        with patch('sys.argv', ['herd_mail.py', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi!']):
            result = hm.main()

        self.assertEqual(result, 1)

    def test_invalid_email_address(self):
        """Test error with invalid email address."""
        with patch('sys.argv', ['herd_mail.py', '--to', 'not_an_email',
                                '--subject', 'Hello', '--body', 'Hi!']):
            result = hm.main()

        self.assertEqual(result, 1)

    def test_invalid_cc_address(self):
        """Test error with invalid CC address."""
        with patch('sys.argv', ['herd_mail.py', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi!',
                                '--cc', 'invalid_email']):
            result = hm.main()

        self.assertEqual(result, 1)

    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_with_attachments(self, mock_check_duplicate, mock_send):
        """Test sending with attachments."""
        mock_check_duplicate.return_value = False
        mock_send.return_value = None

        with patch('sys.argv', ['herd_mail.py', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'See attached',
                                '--attachment', 'file1.pdf', 'file2.txt']):
            result = hm.main()

        self.assertEqual(result, 0)
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs['attachments'], ['file1.pdf', 'file2.txt'])

    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_escape_sequences_in_body(self, mock_check_duplicate, mock_send):
        """Test escape sequences in body are decoded."""
        mock_check_duplicate.return_value = False
        mock_send.return_value = None

        with patch('sys.argv', ['herd_mail.py', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Line1\\nLine2']):
            result = hm.main()

        self.assertEqual(result, 0)
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs['body_md'], 'Line1\nLine2')


class TestBodyLoading(unittest.TestCase):
    """Test body loading from various sources."""

    def setUp(self):
        self.clear_env()
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"
        # Mock waggle availability for tests
        self.waggle_patch = patch('herd_mail.WAGGLE_AVAILABLE', True)
        self.waggle_patch.start()

    def tearDown(self):
        self.waggle_patch.stop()
        self.clear_env()

    def clear_env(self):
        for key in list(os.environ.keys()):
            if key.startswith("WAGGLE_"):
                del os.environ[key]

    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_body_from_file(self, mock_check_duplicate, mock_send):
        """Test reading body from file."""
        mock_check_duplicate.return_value = False
        mock_send.return_value = None

        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Hello from file\n\nThis is the body.")
            temp_path = f.name

        try:
            with patch('sys.argv', ['herd_mail.py', '--to', 'friend@example.com',
                                    '--subject', 'Hello', '--body-file', temp_path]):
                result = hm.main()

            self.assertEqual(result, 0)
            call_kwargs = mock_send.call_args[1]
            self.assertEqual(call_kwargs['body_md'], "# Hello from file\n\nThis is the body.")
        finally:
            os.unlink(temp_path)

    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_body_from_stdin(self, mock_check_duplicate, mock_send):
        """Test reading body from stdin."""
        mock_check_duplicate.return_value = False
        mock_send.return_value = None

        # Mock stdin
        with patch('sys.stdin', StringIO("Hello from stdin")):
            with patch('sys.stdin.isatty', return_value=False):
                with patch('sys.argv', ['herd_mail.py', '--to', 'friend@example.com',
                                        '--subject', 'Hello']):
                    result = hm.main()

        self.assertEqual(result, 0)
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs['body_md'], "Hello from stdin")

    def test_body_file_not_found(self):
        """Test error when body file doesn't exist."""
        with patch('sys.argv', ['herd_mail.py', '--to', 'friend@example.com',
                                '--subject', 'Hello',
                                '--body-file', '/tmp/nonexistent_file_12345.txt']):
            result = hm.main()

        self.assertEqual(result, 1)


class TestWaggleStubs(unittest.TestCase):
    """Test that waggle function stubs exist for mocking."""

    def test_stubs_exist(self):
        """All waggle functions should be importable from herd_mail."""
        self.assertTrue(hasattr(hm, 'send_email'))
        self.assertTrue(hasattr(hm, 'check_recently_sent'))
        self.assertTrue(hasattr(hm, 'read_message'))
        self.assertTrue(hasattr(hm, 'list_inbox'))
        self.assertTrue(hasattr(hm, 'download_attachments'))


def run_basic_tests():
    """Run basic tests without pytest."""
    print("Running basic validation tests...")
    print("=" * 60)

    # Test 1: Email validation
    print("\n1. Testing email validation...")
    assert hm.validate_email_address("user@example.com") == True
    assert hm.validate_email_address("invalid") == False
    assert hm.validate_email_address("user\n@example.com") == False
    print("   ✓ Email validation works")

    # Test 2: Port parsing
    print("\n2. Testing port parsing...")
    assert hm.parse_port("465", 0, "test") == 465
    try:
        hm.parse_port("invalid", 0, "test")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    print("   ✓ Port parsing works")

    # Test 3: Escape sequences
    print("\n3. Testing escape sequences...")
    assert hm.decode_escape_sequences("hello\\nworld") == "hello\nworld"
    assert hm.decode_escape_sequences("hello\\\\world") == "hello\\world"
    print("   ✓ Escape sequence handling works")

    # Test 4: Sanitization
    print("\n4. Testing sanitization...")
    assert hm.sanitize_for_display("hello\x1b[31mworld") == "helloworld"
    assert hm.sanitize_for_display("hello\nworld") == "hello\nworld"
    print("   ✓ Sanitization works")

    # Test 5: Config loading
    print("\n5. Testing config loading...")
    os.environ["WAGGLE_HOST"] = "smtp.example.com"
    os.environ["WAGGLE_USER"] = "user@example.com"
    os.environ["WAGGLE_PASS"] = "secret"
    os.environ["WAGGLE_FROM"] = "user@example.com"

    cfg = hm.get_config()
    assert cfg["smtp_host"] == "smtp.example.com"
    assert cfg["smtp_port"] == 465
    print("   ✓ Config loads correctly")

    # Test 6: Config validation
    print("\n6. Testing config validation...")
    assert hm.validate_config(cfg) == True
    print("   ✓ Valid config passes")

    incomplete = {"smtp_host": "", "smtp_user": "user", "smtp_pass": "pass", "from_addr": "user"}
    assert hm.validate_config(incomplete) == False
    print("   ✓ Invalid config fails correctly")

    # Test 7: Waggle config conversion
    print("\n7. Testing waggle config conversion...")
    waggle_cfg = hm.build_waggle_config(cfg)
    assert waggle_cfg["host"] == "smtp.example.com"
    assert "imap_host" in waggle_cfg
    print("   ✓ Config converts to waggle format")

    print("\n" + "=" * 60)
    print("All basic tests passed! ✓")
    print("\nFor full test suite, install pytest and run:")
    print("  pip install pytest")
    print("  python3 -m pytest test_herd_mail.py -v")


if __name__ == "__main__":
    # If pytest is available, use it for full test suite
    try:
        import pytest
        print("Running with pytest...")
        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        # Fall back to basic tests
        run_basic_tests()
