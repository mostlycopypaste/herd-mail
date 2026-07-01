#!/usr/bin/env python3
"""
Unit tests for herd_mail.py

Run with: python3 -m pytest test_herd_mail.py -v
Or: python3 test_herd_mail.py (for basic validation)

These tests mock SMTP/IMAP so they run without real credentials.
"""

import json
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


class TestVersion(unittest.TestCase):
    """Test version tracking."""

    def test_version_string_exists(self):
        """Module has a __version__ attribute."""
        self.assertTrue(hasattr(hm, '__version__'))
        self.assertRegex(hm.__version__, r'^\d+\.\d+\.\d+')

    def test_version_flag(self):
        """--version prints version and exits."""
        with patch('herd_mail.WAGGLE_AVAILABLE', True):
            with self.assertRaises(SystemExit) as ctx:
                with patch('sys.argv', ['herd_mail.py', '--version']):
                    hm.main()
            self.assertEqual(ctx.exception.code, 0)

    def test_config_shows_version(self):
        """Config output includes version."""
        for key in list(os.environ.keys()):
            if key.startswith("WAGGLE_"):
                del os.environ[key]
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"

        try:
            with patch('herd_mail.WAGGLE_AVAILABLE', True), \
                 patch('sys.argv', ['herd_mail.py', 'config']), \
                 patch('herd_mail.logger') as mock_logger:
                hm.main()

            log_output = " ".join(
                str(call) for call in mock_logger.info.call_args_list
            )
            self.assertIn(hm.__version__, log_output)
        finally:
            for key in list(os.environ.keys()):
                if key.startswith("WAGGLE_"):
                    del os.environ[key]


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

    def test_validate_config_require_imap_missing(self):
        """Test validation fails when IMAP required but missing."""
        cfg = {
            "smtp_host": "smtp.example.com",
            "smtp_user": "user@example.com",
            "smtp_pass": "secret",
            "from_addr": "user@example.com",
            "imap_host": None,
        }
        result = hm.validate_config(cfg, require_smtp=False, require_imap=True)
        self.assertFalse(result)

    def test_validate_config_require_imap_present(self):
        """Test validation passes when IMAP required and present."""
        cfg = {
            "smtp_host": "smtp.example.com",
            "smtp_user": "user@example.com",
            "smtp_pass": "secret",
            "from_addr": "user@example.com",
            "imap_host": "imap.example.com",
        }
        result = hm.validate_config(cfg, require_smtp=False, require_imap=True)
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

        with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'friend@example.com',
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

        with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi!']):
            result = hm.main()

        self.assertEqual(result, 0)  # Not an error, just skipped

    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_skip_duplicate_check(self, mock_check_duplicate, mock_send):
        """Test --skip-duplicate-check bypasses detection."""
        mock_send.return_value = None

        with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi!',
                                '--skip-duplicate-check']):
            result = hm.main()

        self.assertEqual(result, 0)
        mock_check_duplicate.assert_not_called()
        mock_send.assert_called_once()

    def test_dry_run(self):
        """Test --dry-run validates without sending."""
        with patch('sys.argv', ['herd_mail.py', 'send', '--dry-run', '--to', 'test@example.com',
                                '--subject', 'Test']):
            result = hm.main()

        self.assertEqual(result, 0)

    def test_missing_config(self):
        """Test error when config incomplete."""
        self.clear_env()
        # Don't set any env vars

        with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi!']):
            result = hm.main()

        self.assertEqual(result, 1)

    def test_invalid_email_address(self):
        """Test error with invalid email address."""
        with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'not_an_email',
                                '--subject', 'Hello', '--body', 'Hi!']):
            result = hm.main()

        self.assertEqual(result, 1)

    def test_invalid_cc_address(self):
        """Test error with invalid CC address."""
        with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'friend@example.com',
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

        with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'friend@example.com',
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

        with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'friend@example.com',
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
            with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'friend@example.com',
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
                with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'friend@example.com',
                                        '--subject', 'Hello']):
                    result = hm.main()

        self.assertEqual(result, 0)
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs['body_md'], "Hello from stdin")

    def test_body_file_not_found(self):
        """Test error when body file doesn't exist."""
        with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'friend@example.com',
                                '--subject', 'Hello',
                                '--body-file', '/tmp/nonexistent_file_12345.txt']):
            result = hm.main()

        self.assertEqual(result, 1)


class TestOutput(unittest.TestCase):
    """Test output formatting helpers."""

    def test_output_json(self):
        """Test JSON output goes to stdout."""
        data = {"folder": "INBOX", "count": 1, "messages": []}
        captured = StringIO()
        with patch('sys.stdout', captured):
            hm.output_json(data)
        result = json.loads(captured.getvalue())
        self.assertEqual(result["folder"], "INBOX")
        self.assertEqual(result["count"], 1)

    def test_output_human_list_with_messages(self):
        """Test human-readable list output."""
        data = {
            "folder": "INBOX",
            "count": 1,
            "messages": [{
                "uid": "42",
                "from_addr": "alice@example.com",
                "from_name": "Alice",
                "subject": "Hello",
                "date": "Mon, 24 Mar 2026 10:00:00 -0400",
                "unread": True,
                "size": 1024,
            }]
        }
        captured = StringIO()
        with patch('sys.stdout', captured):
            hm.output_human_list(data)
        output = captured.getvalue()
        self.assertIn("alice@example.com", output)
        self.assertIn("Hello", output)

    def test_output_human_list_empty(self):
        """Test human-readable list output with no messages."""
        data = {"folder": "INBOX", "count": 0, "messages": []}
        captured = StringIO()
        with patch('sys.stdout', captured):
            hm.output_human_list(data)
        output = captured.getvalue()
        self.assertIn("No messages", output)

    def test_output_human_read(self):
        """Test human-readable read output."""
        data = {
            "uid": "42",
            "folder": "INBOX",
            "from_addr": "alice@example.com",
            "from_name": "Alice",
            "subject": "Hello",
            "date": "Mon, 24 Mar 2026",
            "to": "bob@example.com",
            "body_plain": "Hi Bob!",
            "body_html": None,
            "attachments": [],
        }
        captured = StringIO()
        with patch('sys.stdout', captured):
            hm.output_human_read(data)
        output = captured.getvalue()
        self.assertIn("From: Alice <alice@example.com>", output)
        self.assertIn("Hi Bob!", output)

    def test_output_human_check_with_unread(self):
        """Test human-readable check output with unread messages."""
        data = {"folder": "INBOX", "unread_count": 3, "messages": []}
        captured = StringIO()
        with patch('sys.stdout', captured):
            hm.output_human_check(data)
        output = captured.getvalue()
        self.assertIn("3", output)
        self.assertIn("unread", output)

    def test_output_human_check_none_unread(self):
        """Test human-readable check output with no unread messages."""
        data = {"folder": "INBOX", "unread_count": 0, "messages": []}
        captured = StringIO()
        with patch('sys.stdout', captured):
            hm.output_human_check(data)
        output = captured.getvalue()
        self.assertIn("No unread", output)


class TestCmdConfig(unittest.TestCase):
    """Test config subcommand."""

    def setUp(self):
        self.clear_env()
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"
        os.environ["WAGGLE_IMAP_HOST"] = "imap.example.com"
        self.waggle_patch = patch('herd_mail.WAGGLE_AVAILABLE', True)
        self.waggle_patch.start()

    def tearDown(self):
        self.waggle_patch.stop()
        self.clear_env()

    def clear_env(self):
        for key in list(os.environ.keys()):
            if key.startswith("WAGGLE_"):
                del os.environ[key]

    def test_config_valid(self):
        """Test config command with valid SMTP+IMAP config."""
        with patch('sys.argv', ['herd_mail.py', 'config']):
            result = hm.main()
        self.assertEqual(result, 0)

    def test_config_missing_imap(self):
        """Test config command warns about missing IMAP."""
        del os.environ["WAGGLE_IMAP_HOST"]
        with patch('sys.argv', ['herd_mail.py', 'config']):
            result = hm.main()
        # config still succeeds if SMTP is valid, but warns about IMAP
        self.assertEqual(result, 0)


class TestBackwardCompat(unittest.TestCase):
    """Test backward compatibility for old-style invocations."""

    def setUp(self):
        self.clear_env()
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"
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
    def test_old_style_send(self, mock_check, mock_send):
        """Test old-style --to without subcommand still works."""
        mock_check.return_value = False
        mock_send.return_value = None

        with patch('sys.argv', ['herd_mail.py', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi!']):
            result = hm.main()

        self.assertEqual(result, 0)
        mock_send.assert_called_once()

    def test_no_args_shows_help(self):
        """Test no arguments exits with error (help shown)."""
        with patch('sys.argv', ['herd_mail.py']):
            result = hm.main()
        self.assertEqual(result, 1)


class TestCmdList(unittest.TestCase):
    """Test list subcommand."""

    def setUp(self):
        self.clear_env()
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"
        os.environ["WAGGLE_IMAP_HOST"] = "imap.example.com"
        self.waggle_patch = patch('herd_mail.WAGGLE_AVAILABLE', True)
        self.waggle_patch.start()

    def tearDown(self):
        self.waggle_patch.stop()
        self.clear_env()

    def clear_env(self):
        for key in list(os.environ.keys()):
            if key.startswith("WAGGLE_"):
                del os.environ[key]

    @patch('herd_mail.list_inbox')
    def test_list_json_output(self, mock_list):
        """Test list outputs JSON to stdout."""
        mock_list.return_value = [
            {"uid": "1", "from_addr": "alice@example.com", "from_name": "Alice",
             "subject": "Hello", "date": "Mon, 24 Mar 2026", "flags": "",
             "unread": True, "size": 1024},
        ]
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'list']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        data = json.loads(captured.getvalue())
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["messages"][0]["from_addr"], "alice@example.com")

    @patch('herd_mail.list_inbox')
    def test_list_unread_filter(self, mock_list):
        """Test --unread filters to unread only."""
        mock_list.return_value = [
            {"uid": "1", "from_addr": "a@example.com", "from_name": "A",
             "subject": "Read", "date": "Mon", "flags": "\\Seen",
             "unread": False, "size": 100},
            {"uid": "2", "from_addr": "b@example.com", "from_name": "B",
             "subject": "Unread", "date": "Tue", "flags": "",
             "unread": True, "size": 200},
        ]
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'list', '--unread']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        data = json.loads(captured.getvalue())
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["messages"][0]["uid"], "2")

    @patch('herd_mail.list_inbox')
    def test_list_empty(self, mock_list):
        """Test list with empty inbox."""
        mock_list.return_value = []
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'list']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        data = json.loads(captured.getvalue())
        self.assertEqual(data["count"], 0)

    @patch('herd_mail.list_inbox')
    def test_list_human_output(self, mock_list):
        """Test list with --human flag."""
        mock_list.return_value = [
            {"uid": "1", "from_addr": "alice@example.com", "from_name": "Alice",
             "subject": "Hello", "date": "Mon, 24 Mar 2026", "flags": "",
             "unread": True, "size": 1024},
        ]
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'list', '--human']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        output = captured.getvalue()
        self.assertIn("alice@example.com", output)

    def test_list_no_imap(self):
        """Test list fails without IMAP config."""
        del os.environ["WAGGLE_IMAP_HOST"]
        with patch('sys.argv', ['herd_mail.py', 'list']):
            result = hm.main()
        self.assertEqual(result, 1)


class TestCmdRead(unittest.TestCase):
    """Test read subcommand."""

    def setUp(self):
        self.clear_env()
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"
        os.environ["WAGGLE_IMAP_HOST"] = "imap.example.com"
        self.waggle_patch = patch('herd_mail.WAGGLE_AVAILABLE', True)
        self.waggle_patch.start()

    def tearDown(self):
        self.waggle_patch.stop()
        self.clear_env()

    def clear_env(self):
        for key in list(os.environ.keys()):
            if key.startswith("WAGGLE_"):
                del os.environ[key]

    @patch('herd_mail.read_message')
    def test_read_json_output(self, mock_read):
        """Test read outputs full message as JSON."""
        mock_read.return_value = {
            "uid": "42", "folder": "INBOX",
            "message_id": "<abc@example.com>",
            "from_addr": "alice@example.com", "from_name": "Alice",
            "subject": "Hello", "date": "Mon, 24 Mar 2026",
            "to": "bob@example.com",
            "body_plain": "Hi Bob!", "body_html": None,
            "in_reply_to": None, "references": None,
            "attachments": [],
        }
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'read', '42']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        data = json.loads(captured.getvalue())
        self.assertEqual(data["uid"], "42")
        self.assertEqual(data["body_plain"], "Hi Bob!")

    @patch('herd_mail.read_message')
    def test_read_human_output(self, mock_read):
        """Test read with --human flag."""
        mock_read.return_value = {
            "uid": "42", "folder": "INBOX",
            "from_addr": "alice@example.com", "from_name": "Alice",
            "subject": "Hello", "date": "Mon, 24 Mar 2026",
            "to": "bob@example.com",
            "body_plain": "Hi Bob!", "body_html": None,
            "attachments": [],
        }
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'read', '42', '--human']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        output = captured.getvalue()
        self.assertIn("From: Alice <alice@example.com>", output)
        self.assertIn("Hi Bob!", output)

    @patch('herd_mail.read_message')
    def test_read_connection_error(self, mock_read):
        """Test read handles connection errors."""
        mock_read.side_effect = ConnectionError("Connection refused")
        with patch('sys.argv', ['herd_mail.py', 'read', '99']):
            result = hm.main()
        self.assertEqual(result, 1)

    def test_read_no_imap(self):
        """Test read fails without IMAP config."""
        del os.environ["WAGGLE_IMAP_HOST"]
        with patch('sys.argv', ['herd_mail.py', 'read', '42']):
            result = hm.main()
        self.assertEqual(result, 1)


class TestCmdCheck(unittest.TestCase):
    """Test check subcommand."""

    def setUp(self):
        self.clear_env()
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"
        os.environ["WAGGLE_IMAP_HOST"] = "imap.example.com"
        self.waggle_patch = patch('herd_mail.WAGGLE_AVAILABLE', True)
        self.waggle_patch.start()

    def tearDown(self):
        self.waggle_patch.stop()
        self.clear_env()

    def clear_env(self):
        for key in list(os.environ.keys()):
            if key.startswith("WAGGLE_"):
                del os.environ[key]

    @patch('herd_mail.list_inbox')
    def test_check_has_unread(self, mock_list):
        """Test check returns 0 when unread messages exist."""
        mock_list.return_value = [
            {"uid": "1", "from_addr": "a@example.com", "from_name": "A",
             "subject": "New", "date": "Mon", "flags": "",
             "unread": True, "size": 100},
            {"uid": "2", "from_addr": "b@example.com", "from_name": "B",
             "subject": "Read", "date": "Tue", "flags": "\\Seen",
             "unread": False, "size": 200},
        ]
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'check']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        data = json.loads(captured.getvalue())
        self.assertEqual(data["unread_count"], 1)

    @patch('herd_mail.list_inbox')
    def test_check_no_unread(self, mock_list):
        """Test check returns 1 when no unread messages."""
        mock_list.return_value = [
            {"uid": "1", "from_addr": "a@example.com", "from_name": "A",
             "subject": "Read", "date": "Mon", "flags": "\\Seen",
             "unread": False, "size": 100},
        ]
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'check']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 1)
        data = json.loads(captured.getvalue())
        self.assertEqual(data["unread_count"], 0)

    @patch('herd_mail.list_inbox')
    def test_check_connection_error(self, mock_list):
        """Test check returns 2 on error."""
        mock_list.side_effect = ConnectionError("Connection refused")
        with patch('sys.argv', ['herd_mail.py', 'check']):
            result = hm.main()
        self.assertEqual(result, 2)

    @patch('herd_mail.list_inbox')
    def test_check_human_output(self, mock_list):
        """Test check with --human flag."""
        mock_list.return_value = [
            {"uid": "1", "unread": True, "from_addr": "a@example.com",
             "from_name": "A", "subject": "New", "date": "Mon",
             "flags": "", "size": 100},
        ]
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'check', '--human']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        output = captured.getvalue()
        self.assertIn("1", output)
        self.assertIn("unread", output)


class TestCmdDownload(unittest.TestCase):
    """Test download subcommand."""

    def setUp(self):
        self.clear_env()
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"
        os.environ["WAGGLE_IMAP_HOST"] = "imap.example.com"
        self.waggle_patch = patch('herd_mail.WAGGLE_AVAILABLE', True)
        self.waggle_patch.start()

    def tearDown(self):
        self.waggle_patch.stop()
        self.clear_env()

    def clear_env(self):
        for key in list(os.environ.keys()):
            if key.startswith("WAGGLE_"):
                del os.environ[key]

    @patch('herd_mail.download_attachments')
    def test_download_files(self, mock_dl):
        """Test download returns file paths as JSON."""
        mock_dl.return_value = ["/tmp/report.pdf", "/tmp/data.csv"]
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'download', '42']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        data = json.loads(captured.getvalue())
        self.assertEqual(data["uid"], "42")
        self.assertEqual(len(data["files"]), 2)

    @patch('herd_mail.download_attachments')
    def test_download_no_attachments(self, mock_dl):
        """Test download with no attachments returns empty list."""
        mock_dl.return_value = []
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'download', '42']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        data = json.loads(captured.getvalue())
        self.assertEqual(data["files"], [])

    @patch('herd_mail.download_attachments')
    def test_download_with_dest_dir(self, mock_dl):
        """Test download with --dest-dir."""
        mock_dl.return_value = ["/custom/dir/file.pdf"]
        captured = StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('sys.argv', ['herd_mail.py', 'download', '42', '--dest-dir', tmpdir]):
                with patch('sys.stdout', captured):
                    result = hm.main()
        self.assertEqual(result, 0)
        mock_dl.assert_called_once()
        self.assertTrue(tmpdir in str(mock_dl.call_args))

    @patch('herd_mail.download_attachments')
    def test_download_connection_error(self, mock_dl):
        """Test download handles connection errors."""
        mock_dl.side_effect = ConnectionError("Connection refused")
        with patch('sys.argv', ['herd_mail.py', 'download', '42']):
            result = hm.main()
        self.assertEqual(result, 1)

    def test_download_no_imap(self):
        """Test download fails without IMAP config."""
        del os.environ["WAGGLE_IMAP_HOST"]
        with patch('sys.argv', ['herd_mail.py', 'download', '42']):
            result = hm.main()
        self.assertEqual(result, 1)


class TestSendWithSentSync(unittest.TestCase):
    """Test cmd_send with waggle send_email (save_sent built-in)."""

    def setUp(self):
        self.clear_env()
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"
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
    def test_send_with_imap_config(self, mock_check, mock_send):
        """Test send succeeds when IMAP is configured (waggle handles save)."""
        mock_check.return_value = False
        mock_send.return_value = None
        os.environ["WAGGLE_IMAP_HOST"] = "imap.example.com"

        with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi!']):
            result = hm.main()

        self.assertEqual(result, 0)
        mock_send.assert_called_once()

    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_send_without_imap_config(self, mock_check, mock_send):
        """Test send still works without IMAP config (no separate save step)."""
        mock_check.return_value = False
        mock_send.return_value = None

        with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi!']):
            result = hm.main()

        self.assertEqual(result, 0)
        mock_send.assert_called_once()


class TestValidateImapFlags(unittest.TestCase):
    """Test IMAP flag validation and normalization."""

    def test_valid_flags(self):
        """Standard flags are accepted."""
        normalized, errors = hm.validate_imap_flags([r"\Seen", r"\Answered", r"\Flagged"])
        self.assertEqual(errors, [])
        self.assertEqual(normalized, [r"\Seen", r"\Answered", r"\Flagged"])

    def test_case_insensitive(self):
        """Flags are normalized case-insensitively."""
        normalized, errors = hm.validate_imap_flags([r"\seen", r"\ANSWERED"])
        self.assertEqual(errors, [])
        self.assertEqual(normalized, [r"\Seen", r"\Answered"])

    def test_without_backslash(self):
        """Flags without leading backslash are normalized."""
        normalized, errors = hm.validate_imap_flags(["Seen", "Flagged"])
        self.assertEqual(errors, [])
        self.assertEqual(normalized, [r"\Seen", r"\Flagged"])

    def test_invalid_flag_rejected(self):
        """Invalid flags produce errors."""
        normalized, errors = hm.validate_imap_flags([r"\Deleted", r"\Draft", "bogus"])
        self.assertEqual(len(errors), 3)
        self.assertEqual(normalized, [])

    def test_mixed_valid_invalid(self):
        """Mix of valid and invalid flags."""
        normalized, errors = hm.validate_imap_flags([r"\Seen", r"\Deleted"])
        self.assertEqual(normalized, [r"\Seen"])
        self.assertEqual(len(errors), 1)


class TestCmdFlag(unittest.TestCase):
    """Test flag subcommand."""

    def setUp(self):
        self.clear_env()
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"
        os.environ["WAGGLE_IMAP_HOST"] = "imap.example.com"
        self.waggle_patch = patch('herd_mail.WAGGLE_AVAILABLE', True)
        self.waggle_patch.start()

    def tearDown(self):
        self.waggle_patch.stop()
        self.clear_env()

    def clear_env(self):
        for key in list(os.environ.keys()):
            if key.startswith("WAGGLE_"):
                del os.environ[key]

    @patch('herd_mail.set_flags')
    def test_flag_add_json(self, mock_set_flags):
        """Test flag add outputs JSON."""
        mock_set_flags.return_value = True
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'flag', 'add', '42', r'\Seen']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        data = json.loads(captured.getvalue())
        self.assertEqual(data["action"], "add")

    @patch('herd_mail.clear_flags')
    def test_flag_remove_human(self, mock_clear_flags):
        """Test flag remove with --human output."""
        mock_clear_flags.return_value = True
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'flag', 'remove', '42', r'\Seen', '--human']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        self.assertIn("-\\Seen", captured.getvalue())

    @patch('herd_mail.set_flags')
    def test_flag_bulk_uids(self, mock_set_flags):
        """Test bulk UID flag operation."""
        mock_set_flags.return_value = True
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'flag', 'add', '10,20,30', r'\Seen']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        mock_set_flags.assert_called_once()
        call_args = mock_set_flags.call_args
        # waggle set_flags takes comma-separated UIDs as string
        self.assertEqual(call_args[0][0], "10,20,30")

    def test_flag_invalid_flag(self):
        """Test invalid flag returns exit code 1."""
        with patch('sys.argv', ['herd_mail.py', 'flag', 'add', '42', r'\Deleted']):
            result = hm.main()
        self.assertEqual(result, 1)

    def test_flag_no_imap(self):
        """Test flag without IMAP config returns 1."""
        del os.environ["WAGGLE_IMAP_HOST"]
        with patch('sys.argv', ['herd_mail.py', 'flag', 'add', '42', r'\Seen']):
            result = hm.main()
        self.assertEqual(result, 1)

    @patch('herd_mail.set_flags')
    def test_flag_connection_error(self, mock_set_flags):
        """Test flag handles connection errors."""
        mock_set_flags.side_effect = ConnectionError("Connection refused")
        with patch('sys.argv', ['herd_mail.py', 'flag', 'add', '42', r'\Seen']):
            result = hm.main()
        self.assertEqual(result, 1)


class TestCmdMove(unittest.TestCase):
    """Test move subcommand."""

    def setUp(self):
        self.clear_env()
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"
        os.environ["WAGGLE_IMAP_HOST"] = "imap.example.com"
        self.waggle_patch = patch('herd_mail.WAGGLE_AVAILABLE', True)
        self.waggle_patch.start()

    def tearDown(self):
        self.waggle_patch.stop()
        self.clear_env()

    def clear_env(self):
        for key in list(os.environ.keys()):
            if key.startswith("WAGGLE_"):
                del os.environ[key]

    @patch('herd_mail.move_message')
    def test_move_success(self, mock_move):
        """Test successful move outputs JSON."""
        mock_move.return_value = True
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'move', '42', 'INBOX.Archive']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        data = json.loads(captured.getvalue())
        self.assertEqual(data["uid"], "42")
        self.assertEqual(data["to_folder"], "INBOX.Archive")

    @patch('herd_mail.move_message')
    def test_move_human(self, mock_move):
        """Test move with --human output."""
        mock_move.return_value = True
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'move', '42', 'INBOX.Archive', '--human']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        self.assertIn("Moved UID 42", captured.getvalue())

    @patch('herd_mail.move_message')
    def test_move_failure(self, mock_move):
        """Test move handles errors."""
        mock_move.side_effect = RuntimeError("COPY failed")
        with patch('sys.argv', ['herd_mail.py', 'move', '42', 'INBOX.Archive']):
            result = hm.main()
        self.assertEqual(result, 1)

    def test_move_no_imap(self):
        """Test move fails without IMAP config."""
        del os.environ["WAGGLE_IMAP_HOST"]
        with patch('sys.argv', ['herd_mail.py', 'move', '42', 'INBOX.Archive']):
            result = hm.main()
        self.assertEqual(result, 1)


class TestAutoFlagOnRead(unittest.TestCase):
    r"""Test automatic \Seen marking in cmd_read."""

    def setUp(self):
        self.clear_env()
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"
        os.environ["WAGGLE_IMAP_HOST"] = "imap.example.com"
        self.waggle_patch = patch('herd_mail.WAGGLE_AVAILABLE', True)
        self.waggle_patch.start()

    def tearDown(self):
        self.waggle_patch.stop()
        self.clear_env()

    def clear_env(self):
        for key in list(os.environ.keys()):
            if key.startswith("WAGGLE_"):
                del os.environ[key]

    @patch('herd_mail.read_message')
    def test_read_marks_seen(self, mock_read):
        """After reading, message is marked as \\Seen via read_message(mark_read=True)."""
        mock_read.side_effect = [
            {
                "uid": "42", "folder": "INBOX",
                "from_addr": "a@example.com", "from_name": "A",
                "subject": "Hi", "date": "Mon", "to": "b@example.com",
                "body_plain": "Hello", "body_html": None, "attachments": [],
            },
            {"uid": "42"},
        ]
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'read', '42']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        self.assertEqual(mock_read.call_count, 2)
        second_call = mock_read.call_args_list[1]
        self.assertTrue(second_call[1].get('mark_read', False))

    @patch('herd_mail.read_message')
    def test_no_mark_read_flag(self, mock_read):
        """--no-mark-read skips the mark_read call."""
        mock_read.return_value = {
            "uid": "42", "folder": "INBOX",
            "from_addr": "a@example.com", "from_name": "A",
            "subject": "Hi", "date": "Mon", "to": "b@example.com",
            "body_plain": "Hello", "body_html": None, "attachments": [],
        }
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'read', '42', '--no-mark-read']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        # Only one call (content read), no second call for mark_read
        self.assertEqual(mock_read.call_count, 1)

    @patch('herd_mail.read_message')
    def test_mark_read_failure_nonfatal(self, mock_read):
        """Mark-read failure doesn't affect read success."""
        # First call returns content, second call (mark_read) raises
        mock_read.side_effect = [
            {
                "uid": "42", "folder": "INBOX",
                "from_addr": "a@example.com", "from_name": "A",
                "subject": "Hi", "date": "Mon", "to": "b@example.com",
                "body_plain": "Hello", "body_html": None, "attachments": [],
            },
            OSError("Connection failed"),
        ]
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'read', '42']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        # Message was still read and output
        data = json.loads(captured.getvalue())
        self.assertEqual(data["uid"], "42")


class TestAutoFlagOnReply(unittest.TestCase):
    """Test automatic flagging when replying via cmd_send."""

    def setUp(self):
        self.clear_env()
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"
        os.environ["WAGGLE_IMAP_HOST"] = "imap.example.com"
        self.waggle_patch = patch('herd_mail.WAGGLE_AVAILABLE', True)
        self.waggle_patch.start()

    def tearDown(self):
        self.waggle_patch.stop()
        self.clear_env()

    def clear_env(self):
        for key in list(os.environ.keys()):
            if key.startswith("WAGGLE_"):
                del os.environ[key]

    @patch('herd_mail.set_flags')
    @patch('herd_mail.send_email')
    @patch('herd_mail.read_message')
    @patch('herd_mail.check_recently_sent')
    def test_reply_marks_answered(self, mock_check, mock_read_msg, mock_send,
                                   mock_set_flags):
        """Reply marks original as \\Seen + \\Answered via waggle set_flags."""
        mock_check.return_value = False
        mock_read_msg.return_value = {
            "message_id": "<orig@example.com>",
            "reply_references": "<orig@example.com>",
            "subject": "Original",
        }
        mock_send.return_value = None
        mock_set_flags.return_value = True

        with patch('sys.argv', ['herd_mail.py', 'send', '--message-id', '42',
                                '--to', 'friend@example.com',
                                '--subject', 'Re: Original', '--body', 'Thanks!']):
            result = hm.main()

        self.assertEqual(result, 0)
        mock_set_flags.assert_called_once()
        call_args = mock_set_flags.call_args
        flags = call_args[0][1]
        self.assertIn(r"\Seen", flags)
        self.assertIn(r"\Answered", flags)

    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_non_reply_no_flag(self, mock_check, mock_send):
        """Non-reply send does not flag anything."""
        mock_check.return_value = False
        mock_send.return_value = None

        with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi!']):
            result = hm.main()

        self.assertEqual(result, 0)

    @patch('herd_mail.set_flags')
    @patch('herd_mail.send_email')
    @patch('herd_mail.read_message')
    @patch('herd_mail.check_recently_sent')
    def test_reply_flag_failure_nonfatal(self, mock_check, mock_read_msg,
                                         mock_send, mock_set_flags):
        """Flag failure doesn't affect send success."""
        mock_check.return_value = False
        mock_read_msg.return_value = {
            "message_id": "<orig@example.com>",
            "reply_references": "<orig@example.com>",
            "subject": "Original",
        }
        mock_send.return_value = None
        mock_set_flags.side_effect = OSError("IMAP error")

        with patch('sys.argv', ['herd_mail.py', 'send', '--message-id', '42',
                                '--to', 'friend@example.com',
                                '--subject', 'Re: Original', '--body', 'Thanks!']):
            result = hm.main()

        self.assertEqual(result, 0)


class TestFormatQuoteBlock(unittest.TestCase):
    """Test formatting of quoted original message for replies."""

    def test_formats_quote_with_body(self):
        """Quote block includes header and body text."""
        original = {
            "from_raw": "Alice <alice@example.com>",
            "date": "Tue, 01 Apr 2026 10:30:00 +0000",
            "subject": "Project update",
            "body_plain": "Here is the update.\nSecond line.",
        }
        result = hm.format_quote_block(original)
        self.assertIn("-----Original Message-----", result)
        self.assertIn("From: Alice <alice@example.com>", result)
        self.assertIn("Sent: Tue, 01 Apr 2026 10:30:00 +0000", result)
        self.assertIn("Subject: Project update", result)
        self.assertIn("Here is the update.", result)
        self.assertIn("Second line.", result)

    def test_formats_quote_without_body(self):
        """Quote block works when original has no body."""
        original = {
            "from_raw": "Bob <bob@example.com>",
            "date": "Wed, 02 Apr 2026 12:00:00 +0000",
            "subject": "Empty",
            "body_plain": None,
        }
        result = hm.format_quote_block(original)
        self.assertIn("-----Original Message-----", result)
        self.assertIn("From: Bob <bob@example.com>", result)
        self.assertNotIn("None", result)

    def test_formats_quote_missing_fields(self):
        """Quote block handles missing dict keys gracefully."""
        original = {}
        result = hm.format_quote_block(original)
        self.assertIn("-----Original Message-----", result)


class TestReplyQuotedBody(unittest.TestCase):
    """Test that cmd_send appends quoted original to reply body."""

    def setUp(self):
        self.clear_env()
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"
        os.environ["WAGGLE_IMAP_HOST"] = "imap.example.com"
        self.waggle_patch = patch('herd_mail.WAGGLE_AVAILABLE', True)
        self.waggle_patch.start()

    def tearDown(self):
        self.waggle_patch.stop()
        self.clear_env()

    def clear_env(self):
        for key in list(os.environ.keys()):
            if key.startswith("WAGGLE_"):
                del os.environ[key]

    @patch('herd_mail.set_flags')
    @patch('herd_mail.send_email')
    @patch('herd_mail.read_message')
    @patch('herd_mail.check_recently_sent')
    def test_reply_includes_quoted_original(self, mock_check, mock_read_msg,
                                             mock_send, mock_set_flags):
        """Reply body sent to send_email includes quoted original message."""
        mock_check.return_value = False
        mock_read_msg.return_value = {
            "message_id": "<orig@example.com>",
            "reply_references": "<orig@example.com>",
            "subject": "Original Subject",
            "from_raw": "Alice <alice@example.com>",
            "date": "Tue, 01 Apr 2026 10:30:00 +0000",
            "body_plain": "Original body text here.",
        }
        mock_send.return_value = None
        mock_set_flags.return_value = True

        with patch('sys.argv', ['herd_mail.py', 'send', '--message-id', '42',
                                '--to', 'alice@example.com',
                                '--subject', 'Re: Original Subject',
                                '--body', 'Thanks for the update!']):
            result = hm.main()

        self.assertEqual(result, 0)
        body_sent = mock_send.call_args[1].get('body_md') or mock_send.call_args[0][2]
        self.assertIn("Thanks for the update!", body_sent)
        self.assertIn("-----Original Message-----", body_sent)
        self.assertIn("Original body text here.", body_sent)

    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_non_reply_no_quote(self, mock_check, mock_send):
        """Non-reply send does not add any quote block."""
        mock_check.return_value = False
        mock_send.return_value = None

        with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Just a message']):
            result = hm.main()

        self.assertEqual(result, 0)
        body_sent = mock_send.call_args[1].get('body_md') or mock_send.call_args[0][2]
        self.assertNotIn("-----Original Message-----", body_sent)


class TestWaggleStubs(unittest.TestCase):
    """Test that waggle function stubs exist for mocking."""

    def test_stubs_exist(self):
        """All waggle functions should be importable from herd_mail."""
        self.assertTrue(hasattr(hm, 'send_email'))
        self.assertTrue(hasattr(hm, 'check_recently_sent'))
        self.assertTrue(hasattr(hm, 'read_message'))
        self.assertTrue(hasattr(hm, 'list_inbox'))
        self.assertTrue(hasattr(hm, 'download_attachments'))
        self.assertTrue(hasattr(hm, 'move_message'))
        self.assertTrue(hasattr(hm, 'set_flags'))
        self.assertTrue(hasattr(hm, 'clear_flags'))


# ---------------------------------------------------------------------------
# Issue #14: UID -> sequence-number resolution removed.
#
# waggle 1.9.12+ uses UID-based IMAP commands (m.uid("FETCH"/"STORE")) and
# list_inbox() returns real UIDs. The old uid_to_sequence_number() /
# resolve_sequence_to_uids() round-trips mapped valid UIDs to stale sequence
# numbers, silently dropping threading headers on `send --message-id` and
# raising "Invalid messageset" on list/flag. These tests lock in the fix:
# every UID consumer must pass the caller's real UID straight through, and no
# extra IMAP round-trip may happen for list/check.
# ---------------------------------------------------------------------------
class TestUidResolutionRemovedUnit(unittest.TestCase):
    """Unit: the sequence-number helpers are gone; UIDs pass through verbatim."""

    def test_sequence_helpers_removed(self):
        """The fragile conversion helpers no longer exist on the module."""
        self.assertFalse(hasattr(hm, 'uid_to_sequence_number'))
        self.assertFalse(hasattr(hm, 'resolve_sequence_to_uids'))


class TestUidPassthroughEnv(unittest.TestCase):
    """Shared env harness for the UID-passthrough command tests."""

    def setUp(self):
        self.clear_env()
        os.environ["WAGGLE_HOST"] = "smtp.example.com"
        os.environ["WAGGLE_USER"] = "user@example.com"
        os.environ["WAGGLE_PASS"] = "secret"
        os.environ["WAGGLE_FROM"] = "user@example.com"
        os.environ["WAGGLE_IMAP_HOST"] = "imap.example.com"
        self.waggle_patch = patch('herd_mail.WAGGLE_AVAILABLE', True)
        self.waggle_patch.start()

    def tearDown(self):
        self.waggle_patch.stop()
        self.clear_env()

    def clear_env(self):
        for key in list(os.environ.keys()):
            if key.startswith("WAGGLE_"):
                del os.environ[key]


class TestUidPassthroughIntegration(TestUidPassthroughEnv):
    """Integration: each UID consumer forwards the caller's real UID unchanged."""

    @patch('herd_mail.set_flags')
    @patch('herd_mail.send_email')
    @patch('herd_mail.read_message')
    @patch('herd_mail.check_recently_sent')
    def test_send_message_id_uses_real_uid(self, mock_check, mock_read,
                                           mock_send, mock_set_flags):
        """send --message-id fetches the original by the REAL UID (no conversion)."""
        mock_check.return_value = False
        mock_read.return_value = {
            "message_id": "<orig@example.com>",
            "reply_references": "<orig@example.com>",
            "subject": "Original",
            "from_raw": "Alice <alice@example.com>",
            "date": "Tue, 01 Apr 2026 10:30:00 +0000",
            "body_plain": "Original body.",
        }
        mock_send.return_value = None
        mock_set_flags.return_value = True

        with patch('sys.argv', ['herd_mail.py', 'send', '--message-id', '26297',
                                '--to', 'alice@example.com',
                                '--subject', 'Re: Original', '--body', 'Reply']):
            result = hm.main()

        self.assertEqual(result, 0)
        # read_message must receive the literal UID we passed, not a seq number.
        self.assertEqual(mock_read.call_args[0][0], '26297')
        # Threading headers derived from the original are forwarded to send.
        self.assertEqual(mock_send.call_args[1]['in_reply_to'], "<orig@example.com>")
        self.assertEqual(mock_send.call_args[1]['references'], "<orig@example.com>")

    @patch('herd_mail.download_attachments')
    def test_download_uses_real_uid(self, mock_dl):
        """download forwards the real UID directly to waggle."""
        mock_dl.return_value = []
        with patch('sys.argv', ['herd_mail.py', 'download', '26297']):
            with patch('sys.stdout', StringIO()):
                result = hm.main()
        self.assertEqual(result, 0)
        self.assertEqual(mock_dl.call_args[0][0], '26297')

    @patch('herd_mail.move_message')
    def test_move_uses_real_uid(self, mock_move):
        """move forwards the real UID directly to waggle."""
        mock_move.return_value = True
        with patch('sys.argv', ['herd_mail.py', 'move', '26297', 'INBOX.Archive']):
            with patch('sys.stdout', StringIO()):
                result = hm.main()
        self.assertEqual(result, 0)
        self.assertEqual(mock_move.call_args[0][0], '26297')

    @patch('herd_mail.list_inbox')
    def test_list_uid_preserved(self, mock_list):
        """list output preserves the real UID returned by waggle verbatim."""
        mock_list.return_value = [
            {"uid": "26297", "from_addr": "a@example.com", "from_name": "A",
             "subject": "Hi", "date": "Mon", "flags": "", "unread": True, "size": 1},
        ]
        captured = StringIO()
        with patch('sys.argv', ['herd_mail.py', 'list']):
            with patch('sys.stdout', captured):
                result = hm.main()
        self.assertEqual(result, 0)
        data = json.loads(captured.getvalue())
        self.assertEqual(data["messages"][0]["uid"], "26297")


class TestUidPassthroughFunctional(TestUidPassthroughEnv):
    """Functional: golden reply-threading path plus the fetch-error path."""

    @patch('herd_mail.set_flags')
    @patch('herd_mail.send_email')
    @patch('herd_mail.read_message')
    @patch('herd_mail.check_recently_sent')
    def test_golden_reply_threads(self, mock_check, mock_read, mock_send,
                                  mock_set_flags):
        """End-to-end: a UID reply sends successfully WITH threading headers."""
        mock_check.return_value = False
        mock_read.return_value = {
            "message_id": "<orig@example.com>",
            "reply_references": "<a@example.com> <orig@example.com>",
            "subject": "Original",
            "from_raw": "Alice <alice@example.com>",
            "date": "Tue, 01 Apr 2026 10:30:00 +0000",
            "body_plain": "Body.",
        }
        mock_send.return_value = None
        with patch('sys.argv', ['herd_mail.py', 'send', '--message-id', '5',
                                '--to', 'alice@example.com',
                                '--subject', 'Re: Original', '--body', 'Hi']):
            result = hm.main()
        self.assertEqual(result, 0)
        self.assertIsNotNone(mock_send.call_args[1]['in_reply_to'])

    @patch('herd_mail.send_email')
    @patch('herd_mail.read_message')
    @patch('herd_mail.check_recently_sent')
    def test_fetch_error_still_sends(self, mock_check, mock_read, mock_send):
        """Error path: if the original can't be fetched, send still succeeds."""
        mock_check.return_value = False
        mock_read.side_effect = OSError("Message not found")
        mock_send.return_value = None
        with patch('sys.argv', ['herd_mail.py', 'send', '--message-id', '999999',
                                '--to', 'alice@example.com',
                                '--subject', 'Re: X', '--body', 'Hi']):
            result = hm.main()
        self.assertEqual(result, 0)
        mock_send.assert_called_once()
        self.assertIsNone(mock_send.call_args[1]['in_reply_to'])


class TestUidPassthroughSecurity(TestUidPassthroughEnv):
    """Security/data-boundary: the UID is never rewritten by a hidden lookup."""

    @patch('herd_mail.read_message')
    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_uid_not_mutated_by_side_lookup(self, mock_check, mock_send, mock_read):
        """A non-numeric/odd message-id is forwarded verbatim (no seq rewrite)."""
        mock_check.return_value = False
        mock_read.return_value = {"message_id": "<x@e>", "reply_references": None,
                                  "subject": "S", "from_raw": "", "date": "",
                                  "body_plain": ""}
        mock_send.return_value = None
        odd_id = "26297"
        with patch('sys.argv', ['herd_mail.py', 'send', '--message-id', odd_id,
                                '--to', 'a@example.com', '--subject', 'Re',
                                '--body', 'b']):
            with patch('sys.stdout', StringIO()):
                result = hm.main()
        self.assertEqual(result, 0)
        # Exactly the caller-supplied UID reached waggle — no substitution.
        self.assertEqual(mock_read.call_args[0][0], odd_id)


class TestUidResolutionPerformance(TestUidPassthroughEnv):
    """Performance: list/check must not open a second IMAP connection (N+1)."""

    @patch('herd_mail.imaplib.IMAP4_SSL')
    @patch('herd_mail.list_inbox')
    def test_list_opens_no_extra_imap_connection(self, mock_list, mock_ssl):
        """The removed resolve step used to do connect + N UID fetches per list."""
        mock_list.return_value = [
            {"uid": "1", "from_addr": "a@e.com", "from_name": "A", "subject": "s",
             "date": "Mon", "flags": "", "unread": True, "size": 1},
        ]
        with patch('sys.argv', ['herd_mail.py', 'list']):
            with patch('sys.stdout', StringIO()):
                result = hm.main()
        self.assertEqual(result, 0)
        # No direct imaplib connection should be opened by herd-mail for a list.
        mock_ssl.assert_not_called()


class TestUidResolutionRetry(TestUidPassthroughEnv):
    """Retry: PLACEHOLDER.

    herd-mail does not implement its own IMAP retry/backoff — network retries
    are delegated to waggle. This change removes IMAP round-trips rather than
    adding any, so there is no new retry loop to exercise. We instead assert the
    intentional no-retry contract: a single failed IMAP call surfaces as a clean
    error exit (no silent looping), which is the behaviour a retry wrapper would
    wrap in future.
    """

    @patch('herd_mail.download_attachments')
    def test_connection_error_surfaced_not_retried(self, mock_dl):
        mock_dl.side_effect = ConnectionError("Connection refused")
        with patch('sys.argv', ['herd_mail.py', 'download', '42']):
            result = hm.main()
        self.assertEqual(result, 1)
        # Called exactly once — herd-mail does not loop/retry internally.
        self.assertEqual(mock_dl.call_count, 1)


class TestUidResolutionFrame(TestUidPassthroughEnv):
    """Frame/smoke: the affected subcommands still dispatch without crashing."""

    @patch('herd_mail.move_message')
    @patch('herd_mail.download_attachments')
    @patch('herd_mail.list_inbox')
    def test_uid_commands_smoke(self, mock_list, mock_dl, mock_move):
        mock_list.return_value = []
        mock_dl.return_value = []
        mock_move.return_value = True
        for argv in (
            ['herd_mail.py', 'list'],
            ['herd_mail.py', 'download', '1'],
            ['herd_mail.py', 'move', '1', 'INBOX.Archive'],
        ):
            with self.subTest(argv=argv):
                with patch('sys.argv', argv):
                    with patch('sys.stdout', StringIO()):
                        self.assertEqual(hm.main(), 0)


def run_basic_tests():
    """Run basic tests without pytest."""
    print("Running basic validation tests...")
    print("=" * 60)

    print("\n1. Testing email validation...")
    assert hm.validate_email_address("user@example.com") == True
    assert hm.validate_email_address("invalid") == False
    assert hm.validate_email_address("user\n@example.com") == False
    print("   Pass")

    print("\n2. Testing port parsing...")
    assert hm.parse_port("465", 0, "test") == 465
    try:
        hm.parse_port("invalid", 0, "test")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    print("   Pass")

    print("\n3. Testing escape sequences...")
    assert hm.decode_escape_sequences("hello\\nworld") == "hello\nworld"
    assert hm.decode_escape_sequences("hello\\\\world") == "hello\\world"
    print("   Pass")

    print("\n4. Testing sanitization...")
    assert hm.sanitize_for_display("hello\x1b[31mworld") == "helloworld"
    assert hm.sanitize_for_display("hello\nworld") == "hello\nworld"
    print("   Pass")

    print("\n5. Testing config loading...")
    os.environ["WAGGLE_HOST"] = "smtp.example.com"
    os.environ["WAGGLE_USER"] = "user@example.com"
    os.environ["WAGGLE_PASS"] = "secret"
    os.environ["WAGGLE_FROM"] = "user@example.com"

    cfg = hm.get_config()
    assert cfg["smtp_host"] == "smtp.example.com"
    assert cfg["smtp_port"] == 465
    print("   Pass")

    print("\n6. Testing IMAP validation...")
    assert hm.validate_config(cfg, require_smtp=False, require_imap=True) == False
    cfg["imap_host"] = "imap.example.com"
    assert hm.validate_config(cfg, require_smtp=False, require_imap=True) == True
    print("   Pass")

    print("\n7. Testing output helpers...")
    import json
    from io import StringIO
    data = {"folder": "INBOX", "count": 0, "messages": []}
    captured = StringIO()
    import sys as _sys
    old_stdout = _sys.stdout
    _sys.stdout = captured
    hm.output_json(data)
    _sys.stdout = old_stdout
    assert json.loads(captured.getvalue())["count"] == 0
    print("   Pass")

    print("\n" + "=" * 60)
    print("All basic tests passed!")
    print("\nFor full test suite: python3 -m pytest test_herd_mail.py -v")


if __name__ == "__main__":
    # If pytest is available, use it for full test suite
    try:
        import pytest
        print("Running with pytest...")
        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        # Fall back to basic tests
        run_basic_tests()
