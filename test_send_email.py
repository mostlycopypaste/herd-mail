#!/usr/bin/env python3
"""
Unit tests for send_email.py

Run with: python3 -m pytest test_send_email.py -v
Or: python3 test_send_email.py (for basic validation)

These tests mock SMTP/IMAP so they run without real credentials.
"""

import os
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Ensure we can import the module under test
sys.path.insert(0, str(Path(__file__).parent))

import send_email as se


class TestConfig(unittest.TestCase):
    """Test configuration loading and validation."""

    def setUp(self):
        # Clear environment before each test
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

        cfg = se.get_config()

        self.assertEqual(cfg["smtp_host"], "smtp.example.com")
        self.assertEqual(cfg["smtp_port"], 465)  # default
        self.assertEqual(cfg["smtp_user"], "user@example.com")
        self.assertEqual(cfg["smtp_pass"], "secret")
        self.assertEqual(cfg["from_addr"], "user@example.com")
        self.assertEqual(cfg["from_name"], "")  # default
        self.assertTrue(cfg["use_tls"])  # default
        self.assertIsNone(cfg["imap_host"])  # optional
        self.assertEqual(cfg["imap_port"], 993)  # default

    def test_validate_config_missing_required(self):
        """Test validation fails when required fields missing."""
        cfg = {
            "smtp_host": "",
            "smtp_user": "user@example.com",
            "smtp_pass": "secret",
            "from_addr": "user@example.com",
        }

        # Capture stderr
        with patch('sys.stderr', new=StringIO()) as fake_stderr:
            result = se.validate_config(cfg)
            error_output = fake_stderr.getvalue()

        self.assertFalse(result)
        self.assertIn("Missing smtp_host", error_output)

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

        result = se.validate_config(cfg)
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

        waggle_cfg = se.build_waggle_config(cfg)

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

    @patch('send_email.send_email')
    @patch('send_email.check_recently_sent')
    def test_send_simple_email(self, mock_check_duplicate, mock_send):
        """Test sending a simple email."""
        mock_check_duplicate.return_value = False
        mock_send.return_value = None

        with patch('sys.argv', ['send_email.py', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi there!']):
            result = se.main()

        self.assertEqual(result, 0)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs['to'], 'friend@example.com')
        self.assertEqual(call_kwargs['subject'], 'Hello')
        self.assertEqual(call_kwargs['body_md'], 'Hi there!')

    @patch('send_email.check_recently_sent')
    def test_duplicate_detection(self, mock_check_duplicate):
        """Test duplicate detection prevents send."""
        mock_check_duplicate.return_value = True

        with patch('sys.argv', ['send_email.py', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi!']):
            result = se.main()

        self.assertEqual(result, 0)  # Not an error, just skipped

    @patch('send_email.send_email')
    @patch('send_email.check_recently_sent')
    def test_skip_duplicate_check(self, mock_check_duplicate, mock_send):
        """Test --skip-duplicate-check bypasses detection."""
        mock_send.return_value = None

        with patch('sys.argv', ['send_email.py', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi!',
                                '--skip-duplicate-check']):
            result = se.main()

        self.assertEqual(result, 0)
        mock_check_duplicate.assert_not_called()
        mock_send.assert_called_once()

    def test_dry_run(self):
        """Test --dry-run validates without sending."""
        with patch('sys.argv', ['send_email.py', '--dry-run']):
            with patch('sys.stdout', new=StringIO()) as fake_stdout:
                result = se.main()
                output = fake_stdout.getvalue()

        self.assertEqual(result, 0)
        self.assertIn("Configuration valid!", output)
        self.assertIn("smtp.example.com", output)

    def test_missing_config(self):
        """Test error when config incomplete."""
        self.clear_env()
        # Don't set any env vars

        with patch('sys.argv', ['send_email.py', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi!']):
            with patch('sys.stderr', new=StringIO()):
                result = se.main()

        self.assertEqual(result, 1)

    @patch('send_email.send_email')
    @patch('send_email.check_recently_sent')
    def test_with_attachments(self, mock_check_duplicate, mock_send):
        """Test sending with attachments."""
        mock_check_duplicate.return_value = False
        mock_send.return_value = None

        with patch('sys.argv', ['send_email.py', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'See attached',
                                '--attachment', 'file1.pdf', 'file2.txt']):
            result = se.main()

        self.assertEqual(result, 0)
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs['attachments'], ['file1.pdf', 'file2.txt'])


class TestBodyLoading(unittest.TestCase):
    """Test body loading from various sources."""

    def setUp(self):
        self.clear_env()
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"

    def clear_env(self):
        for key in list(os.environ.keys()):
            if key.startswith("WAGGLE_"):
                del os.environ[key]

    @patch('send_email.send_email')
    @patch('send_email.check_recently_sent')
    def test_body_from_file(self, mock_check_duplicate, mock_send):
        """Test reading body from file."""
        mock_check_duplicate.return_value = False
        mock_send.return_value = None

        # Create temp file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Hello from file\n\nThis is the body.")
            temp_path = f.name

        try:
            with patch('sys.argv', ['send_email.py', '--to', 'friend@example.com',
                                    '--subject', 'Hello', '--body-file', temp_path]):
                result = se.main()

            self.assertEqual(result, 0)
            call_kwargs = mock_send.call_args[1]
            self.assertEqual(call_kwargs['body_md'], "# Hello from file\n\nThis is the body.")
        finally:
            os.unlink(temp_path)

    @patch('send_email.send_email')
    @patch('send_email.check_recently_sent')
    def test_body_from_stdin(self, mock_check_duplicate, mock_send):
        """Test reading body from stdin."""
        mock_check_duplicate.return_value = False
        mock_send.return_value = None

        # Mock stdin
        with patch('sys.stdin', StringIO("Hello from stdin")):
            with patch('sys.stdin.isatty', return_value=False):
                with patch('sys.argv', ['send_email.py', '--to', 'friend@example.com',
                                        '--subject', 'Hello']):
                    result = se.main()

        self.assertEqual(result, 0)
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs['body_md'], "Hello from stdin")


def run_basic_tests():
    """Run basic tests without pytest."""
    print("Running basic validation tests...")
    print("=" * 60)

    # Test 1: Config loading
    print("\n1. Testing config loading...")
    os.environ["WAGGLE_HOST"] = "smtp.example.com"
    os.environ["WAGGLE_USER"] = "user@example.com"
    os.environ["WAGGLE_PASS"] = "secret"
    os.environ["WAGGLE_FROM"] = "user@example.com"

    cfg = se.get_config()
    assert cfg["smtp_host"] == "smtp.example.com"
    assert cfg["smtp_port"] == 465
    print("   ✓ Config loads correctly")

    # Test 2: Config validation
    print("\n2. Testing config validation...")
    assert se.validate_config(cfg) == True
    print("   ✓ Valid config passes")

    incomplete = {"smtp_host": "", "smtp_user": "user", "smtp_pass": "pass", "from_addr": "user"}
    assert se.validate_config(incomplete) == False
    print("   ✓ Invalid config fails correctly")

    # Test 3: Waggle config conversion
    print("\n3. Testing waggle config conversion...")
    waggle_cfg = se.build_waggle_config(cfg)
    assert waggle_cfg["host"] == "smtp.example.com"
    assert "imap_host" in waggle_cfg
    print("   ✓ Config converts to waggle format")

    print("\n" + "=" * 60)
    print("All basic tests passed! ✓")
    print("\nFor full test suite, install pytest and run:")
    print("  pip install pytest")
    print("  python3 -m pytest test_send_email.py -v")


if __name__ == "__main__":
    # If pytest is available, use it for full test suite
    try:
        import pytest
        print("Running with pytest...")
        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        # Fall back to basic tests
        run_basic_tests()
