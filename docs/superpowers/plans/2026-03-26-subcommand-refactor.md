# Subcommand Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor herd_mail.py from flat flags to subcommands (send, list, read, check, download, config) with JSON-first output for AI agent consumption.

**Architecture:** Single-file refactor. Extract current send logic into `cmd_send`, add new `cmd_list`/`cmd_read`/`cmd_check`/`cmd_download`/`cmd_config` handlers that wrap waggle functions. Subcommand dispatch in `main()` with backward-compat fallback for `--to` without subcommand.

**Tech Stack:** Python 3.8+, argparse subparsers, waggle (list_inbox, read_message, download_attachments), json module for output.

---

### File Map

- **Modify:** `herd_mail.py` — refactor main(), add command handlers, output helpers, new imports
- **Modify:** `test_herd_mail.py` — update existing send tests to use subcommand argv, add new test classes

---

### Task 1: Add waggle stubs and imports for new functions

**Files:**
- Modify: `herd_mail.py:86-106` (import block and stubs)

- [ ] **Step 1: Write test for new stub availability**

Add to `test_herd_mail.py` at the end of existing test classes (before `run_basic_tests`):

```python
class TestWaggleStubs(unittest.TestCase):
    """Test that waggle function stubs exist for mocking."""

    def test_stubs_exist(self):
        """All waggle functions should be importable from herd_mail."""
        self.assertTrue(hasattr(hm, 'send_email'))
        self.assertTrue(hasattr(hm, 'check_recently_sent'))
        self.assertTrue(hasattr(hm, 'read_message'))
        self.assertTrue(hasattr(hm, 'list_inbox'))
        self.assertTrue(hasattr(hm, 'download_attachments'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_herd_mail.py::TestWaggleStubs -v`
Expected: FAIL — `list_inbox` and `download_attachments` not found on module

- [ ] **Step 3: Update imports and stubs in herd_mail.py**

Replace lines 86-106 in `herd_mail.py` with:

```python
# Try to import waggle, but don't exit at module level (allows tests to run)
WAGGLE_AVAILABLE = False
WAGGLE_IMPORT_ERROR = None

try:
    from waggle import (
        send_email, check_recently_sent, read_message,
        list_inbox, download_attachments,
    )
    WAGGLE_AVAILABLE = True
except ImportError as e:
    WAGGLE_IMPORT_ERROR = e

    def send_email(*args, **kwargs):
        raise RuntimeError("waggle not installed")

    def check_recently_sent(*args, **kwargs):
        raise RuntimeError("waggle not installed")

    def read_message(*args, **kwargs):
        raise RuntimeError("waggle not installed")

    def list_inbox(*args, **kwargs):
        raise RuntimeError("waggle not installed")

    def download_attachments(*args, **kwargs):
        raise RuntimeError("waggle not installed")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_herd_mail.py::TestWaggleStubs -v`
Expected: PASS

- [ ] **Step 5: Run full suite to verify no regressions**

Run: `python3 -m pytest test_herd_mail.py -v`
Expected: 31 passed

- [ ] **Step 6: Commit**

```bash
git add herd_mail.py test_herd_mail.py
git commit -m "Add waggle list_inbox and download_attachments imports and stubs"
```

---

### Task 2: Add `require_imap` to validate_config

**Files:**
- Modify: `herd_mail.py:341-372` (validate_config function)
- Modify: `test_herd_mail.py` (TestConfig class)

- [ ] **Step 1: Write tests for IMAP validation**

Add to `TestConfig` class in `test_herd_mail.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_herd_mail.py::TestConfig::test_validate_config_require_imap_missing test_herd_mail.py::TestConfig::test_validate_config_require_imap_present -v`
Expected: FAIL — `validate_config() got an unexpected keyword argument 'require_imap'`

- [ ] **Step 3: Update validate_config**

Replace the `validate_config` function in `herd_mail.py`:

```python
def validate_config(cfg: dict[str, Any], require_smtp: bool = True, require_imap: bool = False) -> bool:
    """
    Validate configuration has required values.

    Args:
        cfg: Configuration dictionary
        require_smtp: Whether to require SMTP settings
        require_imap: Whether to require IMAP settings

    Returns:
        True if valid, False otherwise
    """
    errors = []

    if require_smtp:
        required = ["smtp_host", "smtp_user", "smtp_pass", "from_addr"]
        for key in required:
            if not cfg.get(key):
                errors.append(f"Missing {key} (set WAGGLE_{key.upper()})")

        from_addr = cfg.get("from_addr")
        if from_addr and not validate_email_address(from_addr):
            errors.append(f"Invalid from_addr email format: {from_addr}")

    if require_imap:
        if not cfg.get("imap_host"):
            errors.append("Missing imap_host (set WAGGLE_IMAP_HOST)")

    if errors:
        logger.error("Configuration errors:")
        for error in errors:
            logger.error(f"  - {error}")
        logger.error("\nSee .envrc.template for required variables.")
        return False

    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_herd_mail.py::TestConfig -v`
Expected: 7 passed

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest test_herd_mail.py -v`
Expected: 33 passed

- [ ] **Step 6: Commit**

```bash
git add herd_mail.py test_herd_mail.py
git commit -m "Add require_imap parameter to validate_config"
```

---

### Task 3: Add output helpers (output_json, human formatters)

**Files:**
- Modify: `herd_mail.py` — add after `build_waggle_config`, before `main()`
- Modify: `test_herd_mail.py` — new TestOutput class

- [ ] **Step 1: Write tests for output helpers**

Add new import at top of `test_herd_mail.py`:

```python
import json
```

Add new test class:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_herd_mail.py::TestOutput -v`
Expected: FAIL — `hm.output_json` not found

- [ ] **Step 3: Implement output helpers**

Add to `herd_mail.py` after `build_waggle_config` and before `main()`. Also add `import json` at the top of the file with the other imports:

```python
import json
```

Then add the output helpers:

```python
DEFAULT_LIST_LIMIT = 20


def output_json(data: dict[str, Any]) -> None:
    """Write JSON to stdout. All logging must go to stderr."""
    print(json.dumps(data, indent=2, default=str))


def output_human_list(data: dict[str, Any]) -> None:
    """Write human-readable message list to stdout."""
    messages = data.get("messages", [])
    if not messages:
        print(f"No messages in {data['folder']}.")
        return

    print(f"{'UID':<8} {'From':<30} {'Subject':<40} {'Date':<20} {'Status'}")
    print("-" * 110)
    for msg in messages:
        status = "*" if msg.get("unread") else " "
        from_display = msg.get("from_name") or msg.get("from_addr", "")
        subject = msg.get("subject", "(no subject)")
        # Truncate long fields
        from_display = from_display[:28] if len(from_display) > 28 else from_display
        subject = subject[:38] if len(subject) > 38 else subject
        date = msg.get("date", "")[:18]
        print(f"{msg['uid']:<8} {from_display:<30} {subject:<40} {date:<20} {status}")


def output_human_read(data: dict[str, Any]) -> None:
    """Write human-readable message to stdout."""
    from_name = data.get("from_name", "")
    from_addr = data.get("from_addr", "")
    from_display = f"{from_name} <{from_addr}>" if from_name else from_addr

    print(f"From: {from_display}")
    print(f"To: {data.get('to', '')}")
    print(f"Date: {data.get('date', '')}")
    print(f"Subject: {data.get('subject', '')}")

    attachments = data.get("attachments", [])
    if attachments:
        names = ", ".join(a.get("filename", "unknown") for a in attachments)
        print(f"Attachments: {names}")

    print("-" * 60)

    body = data.get("body_plain") or data.get("body_html") or "(no body)"
    print(body)


def output_human_check(data: dict[str, Any]) -> None:
    """Write human-readable check result to stdout."""
    count = data.get("unread_count", 0)
    folder = data.get("folder", "INBOX")
    if count == 0:
        print(f"No unread messages in {folder}.")
    else:
        print(f"{count} unread message(s) in {folder}.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_herd_mail.py::TestOutput -v`
Expected: 6 passed

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest test_herd_mail.py -v`
Expected: 39 passed

- [ ] **Step 6: Commit**

```bash
git add herd_mail.py test_herd_mail.py
git commit -m "Add output helpers for JSON and human-readable formatting"
```

---

### Task 4: Refactor main() to subcommand dispatch with cmd_send and cmd_config

This is the biggest structural change. Extract the existing send logic into `cmd_send`, dry-run into `cmd_config`, and replace `main()` with subcommand dispatch.

**Files:**
- Modify: `herd_mail.py:399-601` (replace main() entirely)
- Modify: `test_herd_mail.py` (update TestMain argv, add TestCmdConfig, TestBackwardCompat)

- [ ] **Step 1: Write tests for subcommand dispatch, config, and backward compat**

Add to `test_herd_mail.py`:

```python
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
```

- [ ] **Step 2: Update existing TestMain tests to use subcommand argv**

In `test_herd_mail.py`, update all `TestMain` test methods. Replace every occurrence of `['herd_mail.py', '--to'` with `['herd_mail.py', 'send', '--to'` and `['herd_mail.py', '--dry-run'` with `['herd_mail.py', 'send', '--dry-run'`. Specifically:

In `test_send_simple_email`: change argv to `['herd_mail.py', 'send', '--to', 'friend@example.com', '--subject', 'Hello', '--body', 'Hi there!']`

In `test_duplicate_detection`: change argv to `['herd_mail.py', 'send', '--to', 'friend@example.com', '--subject', 'Hello', '--body', 'Hi!']`

In `test_skip_duplicate_check`: change argv to `['herd_mail.py', 'send', '--to', 'friend@example.com', '--subject', 'Hello', '--body', 'Hi!', '--skip-duplicate-check']`

In `test_dry_run`: change argv to `['herd_mail.py', 'send', '--dry-run', '--to', 'test@example.com', '--subject', 'Test']`

In `test_missing_config`: change argv to `['herd_mail.py', 'send', '--to', 'friend@example.com', '--subject', 'Hello', '--body', 'Hi!']`

In `test_invalid_email_address`: change argv to `['herd_mail.py', 'send', '--to', 'not_an_email', '--subject', 'Hello', '--body', 'Hi!']`

In `test_invalid_cc_address`: change argv to `['herd_mail.py', 'send', '--to', 'friend@example.com', '--subject', 'Hello', '--body', 'Hi!', '--cc', 'invalid_email']`

In `test_with_attachments`: change argv to `['herd_mail.py', 'send', '--to', 'friend@example.com', '--subject', 'Hello', '--body', 'See attached', '--attachment', 'file1.pdf', 'file2.txt']`

In `test_escape_sequences_in_body`: change argv to `['herd_mail.py', 'send', '--to', 'friend@example.com', '--subject', 'Hello', '--body', 'Line1\\nLine2']`

Update `TestBodyLoading` similarly:

In `test_body_from_file`: change to `['herd_mail.py', 'send', '--to', 'friend@example.com', '--subject', 'Hello', '--body-file', temp_path]`

In `test_body_from_stdin`: change to `['herd_mail.py', 'send', '--to', 'friend@example.com', '--subject', 'Hello']`

In `test_body_file_not_found`: change to `['herd_mail.py', 'send', '--to', 'friend@example.com', '--subject', 'Hello', '--body-file', '/tmp/nonexistent_file_12345.txt']`

- [ ] **Step 3: Run tests to see failures**

Run: `python3 -m pytest test_herd_mail.py -v`
Expected: Many failures — `main()` doesn't understand subcommands yet

- [ ] **Step 4: Rewrite main() with subcommand dispatch, cmd_send, cmd_config**

Replace everything from `def main()` to the end of the file in `herd_mail.py` with:

```python
def cmd_send(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """Handle the send subcommand."""
    # Validate email addresses early
    if not validate_email_address(args.to):
        logger.error(f"Invalid recipient email address: {sanitize_for_display(args.to)}")
        return 1

    if args.cc and not validate_email_list(args.cc):
        logger.error(f"Invalid CC email address(es): {sanitize_for_display(args.cc)}")
        return 1

    if args.reply_to and not validate_email_address(args.reply_to):
        logger.error(f"Invalid Reply-To email address: {sanitize_for_display(args.reply_to)}")
        return 1

    # Handle --dry-run as alias for config command
    if args.dry_run:
        return cmd_config(args, cfg)

    # Validate SMTP configuration
    if not validate_config(cfg, require_smtp=True):
        return 1

    # Get body content
    body: Optional[str] = None
    if args.body_file:
        validated_path = validate_file_path(args.body_file, must_exist=True)
        if not validated_path:
            return 1

        try:
            with open(validated_path, "r", encoding="utf-8") as f:
                body = f.read()
        except UnicodeDecodeError as e:
            logger.error(f"Error: Body file must be UTF-8: {e}")
            return 1
        except OSError as e:
            logger.error(f"Error reading body file: {e}")
            return 1
    elif args.body:
        body = decode_escape_sequences(args.body)
    else:
        if not sys.stdin.isatty():
            try:
                body = sys.stdin.read()
            except (OSError, UnicodeDecodeError) as e:
                logger.error(f"Error reading from stdin: {e}")
                return 1
        else:
            body = DEFAULT_NO_BODY_MESSAGE

    # Check for duplicates (unless skipped)
    if not args.skip_duplicate_check:
        try:
            if check_recently_sent(
                args.to,
                args.subject,
                within_minutes=DEFAULT_DUPLICATE_CHECK_MINUTES,
                config=build_waggle_config(cfg)
            ):
                logger.warning(
                    f"Duplicate detected: recently sent to "
                    f"{sanitize_for_display(args.to)} with similar subject"
                )
                logger.info("Use --skip-duplicate-check to override")
                return 0
        except (OSError, ValueError) as e:
            logger.warning(f"Could not check for duplicates: {e}")
            logger.info("Continuing anyway...")

    # Handle reply with threading
    in_reply_to: Optional[str] = None
    references: Optional[str] = None

    if args.message_id:
        try:
            logger.info(f"Fetching original message {args.message_id} for threading...")
            original = read_message(
                args.message_id,
                folder=DEFAULT_IMAP_FOLDER,
                config=build_waggle_config(cfg)
            )
            in_reply_to = original.get("message_id")
            references = original.get("reply_references")
            subject = sanitize_for_display(original.get('subject', 'Unknown'))
            logger.info(f"  Found: {subject}")
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.warning(f"Warning: Could not fetch original message: {e}")
            logger.info("  Continuing without threading headers...")
        except Exception as e:
            logger.warning(f"Unexpected error fetching message: {e}")
            logger.info("  Continuing without threading headers...")

    # Send the email
    try:
        to_display = sanitize_for_display(args.to, max_length=50)
        logger.info(f"Sending email to {to_display}...")

        send_email(
            to=args.to,
            subject=args.subject,
            body_md=body,
            cc=args.cc,
            reply_to=args.reply_to,
            in_reply_to=in_reply_to,
            references=references,
            attachments=args.attachment,
            rich=args.rich,
            config=build_waggle_config(cfg),
        )

        logger.info("Email sent successfully!")
        if cfg.get("imap_host"):
            logger.info("  (Saved to Sent folder via IMAP)")

        return 0

    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        return 1
    except TimeoutError as e:
        logger.error(f"Timeout error: {e}")
        return 1
    except ValueError as e:
        logger.error(f"Invalid input: {e}")
        return 1
    except OSError as e:
        logger.error(f"I/O error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.debug("", exc_info=True)
        return 1


def cmd_config(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """Handle the config subcommand. Validates SMTP and IMAP settings."""
    smtp_valid = validate_config(cfg, require_smtp=True, require_imap=False)

    if smtp_valid:
        logger.info("SMTP configuration valid.")
        smtp_user_display = cfg['smtp_user'][:3] + "***" if cfg['smtp_user'] else "***"
        logger.info(f"  SMTP: {smtp_user_display}@{cfg['smtp_host']}:{cfg['smtp_port']}")
        logger.info(f"  From: {cfg['from_name']} <{cfg['from_addr']}>")
    else:
        logger.error("SMTP configuration invalid.")

    if cfg.get("imap_host"):
        logger.info(f"  IMAP: {cfg['imap_host']}:{cfg['imap_port']} (configured)")
    else:
        logger.warning("  IMAP: not configured (set WAGGLE_IMAP_HOST for read commands)")

    return 0 if smtp_valid else 1


def main() -> int:
    """Main entry point with subcommand dispatch."""
    if not WAGGLE_AVAILABLE:
        logger.error("Error: waggle not installed. Run: pip install waggle-mail")
        if WAGGLE_IMPORT_ERROR:
            logger.error(f"Details: {WAGGLE_IMPORT_ERROR}")
        return 1

    # Backward compat: detect old-style invocation (no subcommand, but --to present)
    if len(sys.argv) > 1 and sys.argv[1].startswith('--'):
        if '--to' in sys.argv:
            logger.warning("Deprecation warning: use 'herd_mail.py send --to ...' instead")
            sys.argv.insert(1, 'send')
        elif '--dry-run' in sys.argv:
            logger.warning("Deprecation warning: use 'herd_mail.py config' instead")
            # Rewrite to: send --dry-run (which dispatches to cmd_config internally)
            sys.argv.insert(1, 'send')

    parser = argparse.ArgumentParser(
        description="herd-mail: AI-to-AI email communication via waggle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # send subcommand
    send_parser = subparsers.add_parser("send", help="Send an email")
    send_parser.add_argument("--to", required=True, help="Recipient email address")
    send_parser.add_argument("--subject", required=True, help="Email subject line")
    send_parser.add_argument("--body", help="Email body (Markdown supported)")
    send_parser.add_argument("--body-file", help="Read body from file (UTF-8)")
    send_parser.add_argument("--attachment", nargs="+", help="File(s) to attach")
    send_parser.add_argument("--cc", help="CC recipients (comma-separated)")
    send_parser.add_argument("--reply-to", help="Reply-To address")
    send_parser.add_argument("--message-id", help="IMAP message ID to reply to (enables threading)")
    send_parser.add_argument("--rich", action="store_true", help="Enable rich HTML formatting")
    send_parser.add_argument("--skip-duplicate-check", action="store_true", help="Skip duplicate detection")
    send_parser.add_argument("--dry-run", action="store_true", help="Validate config without sending")

    # list subcommand
    list_parser = subparsers.add_parser("list", help="List messages in a folder")
    list_parser.add_argument("--folder", default=DEFAULT_IMAP_FOLDER, help="IMAP folder (default: INBOX)")
    list_parser.add_argument("--limit", type=int, default=DEFAULT_LIST_LIMIT, help="Max messages (default: 20)")
    list_parser.add_argument("--unread", action="store_true", help="Only show unread messages")
    list_parser.add_argument("--human", action="store_true", help="Human-readable output")

    # read subcommand
    read_parser = subparsers.add_parser("read", help="Read a full message by UID")
    read_parser.add_argument("uid", help="IMAP message UID")
    read_parser.add_argument("--folder", default=DEFAULT_IMAP_FOLDER, help="IMAP folder (default: INBOX)")
    read_parser.add_argument("--human", action="store_true", help="Human-readable output")

    # check subcommand
    check_parser = subparsers.add_parser("check", help="Check for unread messages")
    check_parser.add_argument("--folder", default=DEFAULT_IMAP_FOLDER, help="IMAP folder (default: INBOX)")
    check_parser.add_argument("--human", action="store_true", help="Human-readable output")

    # download subcommand
    dl_parser = subparsers.add_parser("download", help="Download attachments from a message")
    dl_parser.add_argument("uid", help="IMAP message UID")
    dl_parser.add_argument("--folder", default=DEFAULT_IMAP_FOLDER, help="IMAP folder (default: INBOX)")
    dl_parser.add_argument("--dest-dir", default=".", help="Destination directory (default: .)")

    # config subcommand
    subparsers.add_parser("config", help="Validate configuration")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Load configuration
    try:
        cfg = get_config()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1

    # Dispatch to command handler
    commands = {
        "send": cmd_send,
        "config": cmd_config,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args, cfg)

    # Placeholder for read-side commands (implemented in later tasks)
    logger.error(f"Command '{args.command}' not yet implemented")
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run all tests**

Run: `python3 -m pytest test_herd_mail.py -v`
Expected: All tests pass (~43 tests)

- [ ] **Step 6: Commit**

```bash
git add herd_mail.py test_herd_mail.py
git commit -m "Refactor main() to subcommand dispatch with cmd_send and cmd_config"
```

---

### Task 5: Implement cmd_list

**Files:**
- Modify: `herd_mail.py` — add `cmd_list` function, wire into dispatch
- Modify: `test_herd_mail.py` — add TestCmdList class

- [ ] **Step 1: Write tests for cmd_list**

Add to `test_herd_mail.py`:

```python
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
```

- [ ] **Step 2: Run tests to see failures**

Run: `python3 -m pytest test_herd_mail.py::TestCmdList -v`
Expected: FAIL — `list` command not yet implemented

- [ ] **Step 3: Implement cmd_list**

Add to `herd_mail.py` after `cmd_config`:

```python
def cmd_list(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """Handle the list subcommand."""
    if not validate_config(cfg, require_smtp=False, require_imap=True):
        return 1

    try:
        messages = list_inbox(
            folder=args.folder,
            limit=args.limit,
            config=build_waggle_config(cfg),
        )
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Failed to list messages: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error listing messages: {e}")
        return 1

    if args.unread:
        messages = [m for m in messages if m.get("unread")]

    data = {
        "folder": args.folder,
        "count": len(messages),
        "messages": messages,
    }

    if args.human:
        output_human_list(data)
    else:
        output_json(data)

    return 0
```

Update the dispatch dict in `main()`:

```python
    commands = {
        "send": cmd_send,
        "list": cmd_list,
        "config": cmd_config,
    }
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest test_herd_mail.py::TestCmdList -v`
Expected: 5 passed

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest test_herd_mail.py -v`
Expected: All pass (~48 tests)

- [ ] **Step 6: Commit**

```bash
git add herd_mail.py test_herd_mail.py
git commit -m "Implement list subcommand with JSON/human output and unread filter"
```

---

### Task 6: Implement cmd_read

**Files:**
- Modify: `herd_mail.py` — add `cmd_read`, wire into dispatch
- Modify: `test_herd_mail.py` — add TestCmdRead class

- [ ] **Step 1: Write tests for cmd_read**

Add to `test_herd_mail.py`:

```python
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
```

- [ ] **Step 2: Run tests to see failures**

Run: `python3 -m pytest test_herd_mail.py::TestCmdRead -v`
Expected: FAIL

- [ ] **Step 3: Implement cmd_read**

Add to `herd_mail.py` after `cmd_list`:

```python
def cmd_read(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """Handle the read subcommand."""
    if not validate_config(cfg, require_smtp=False, require_imap=True):
        return 1

    try:
        message = read_message(
            args.uid,
            folder=args.folder,
            config=build_waggle_config(cfg),
        )
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Failed to read message {args.uid}: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error reading message: {e}")
        return 1

    if args.human:
        output_human_read(message)
    else:
        output_json(message)

    return 0
```

Update dispatch dict in `main()`:

```python
    commands = {
        "send": cmd_send,
        "list": cmd_list,
        "read": cmd_read,
        "config": cmd_config,
    }
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest test_herd_mail.py::TestCmdRead -v`
Expected: 4 passed

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest test_herd_mail.py -v`
Expected: All pass (~52 tests)

- [ ] **Step 6: Commit**

```bash
git add herd_mail.py test_herd_mail.py
git commit -m "Implement read subcommand for full message retrieval"
```

---

### Task 7: Implement cmd_check

**Files:**
- Modify: `herd_mail.py` — add `cmd_check`, wire into dispatch
- Modify: `test_herd_mail.py` — add TestCmdCheck class

- [ ] **Step 1: Write tests for cmd_check**

Add to `test_herd_mail.py`:

```python
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
```

- [ ] **Step 2: Run tests to see failures**

Run: `python3 -m pytest test_herd_mail.py::TestCmdCheck -v`
Expected: FAIL

- [ ] **Step 3: Implement cmd_check**

Add to `herd_mail.py` after `cmd_read`:

```python
def cmd_check(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """
    Handle the check subcommand.

    Exit codes: 0=has unread, 1=no unread, 2=error.
    """
    if not validate_config(cfg, require_smtp=False, require_imap=True):
        return 2

    try:
        messages = list_inbox(
            folder=args.folder,
            config=build_waggle_config(cfg),
        )
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Failed to check messages: {e}")
        return 2
    except Exception as e:
        logger.error(f"Unexpected error checking messages: {e}")
        return 2

    unread = [m for m in messages if m.get("unread")]

    data = {
        "folder": args.folder,
        "unread_count": len(unread),
        "messages": unread,
    }

    if args.human:
        output_human_check(data)
    else:
        output_json(data)

    return 0 if unread else 1
```

Update dispatch dict in `main()`:

```python
    commands = {
        "send": cmd_send,
        "list": cmd_list,
        "read": cmd_read,
        "check": cmd_check,
        "config": cmd_config,
    }
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest test_herd_mail.py::TestCmdCheck -v`
Expected: 4 passed

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest test_herd_mail.py -v`
Expected: All pass (~56 tests)

- [ ] **Step 6: Commit**

```bash
git add herd_mail.py test_herd_mail.py
git commit -m "Implement check subcommand with exit code semantics for polling"
```

---

### Task 8: Implement cmd_download

**Files:**
- Modify: `herd_mail.py` — add `cmd_download`, wire into dispatch
- Modify: `test_herd_mail.py` — add TestCmdDownload class

- [ ] **Step 1: Write tests for cmd_download**

Add to `test_herd_mail.py`:

```python
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
        call_kwargs = mock_dl.call_args[1] if mock_dl.call_args[1] else {}
        call_args = mock_dl.call_args[0] if mock_dl.call_args[0] else ()
        # Verify dest_dir was passed (positional or keyword)
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
```

- [ ] **Step 2: Run tests to see failures**

Run: `python3 -m pytest test_herd_mail.py::TestCmdDownload -v`
Expected: FAIL

- [ ] **Step 3: Implement cmd_download**

Add to `herd_mail.py` after `cmd_check`:

```python
def cmd_download(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """Handle the download subcommand."""
    if not validate_config(cfg, require_smtp=False, require_imap=True):
        return 1

    # Ensure dest_dir exists
    dest_dir = Path(args.dest_dir)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Cannot create destination directory: {e}")
        return 1

    try:
        files = download_attachments(
            args.uid,
            folder=args.folder,
            dest_dir=str(dest_dir),
            config=build_waggle_config(cfg),
        )
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Failed to download attachments: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error downloading attachments: {e}")
        return 1

    data = {
        "uid": args.uid,
        "folder": args.folder,
        "files": files,
    }

    output_json(data)
    return 0
```

Update dispatch dict in `main()`:

```python
    commands = {
        "send": cmd_send,
        "list": cmd_list,
        "read": cmd_read,
        "check": cmd_check,
        "download": cmd_download,
        "config": cmd_config,
    }
```

Also remove the placeholder at the bottom of `main()`:

```python
    # Remove these lines:
    # logger.error(f"Command '{args.command}' not yet implemented")
    # return 1
```

Replace with:

```python
    logger.error(f"Unknown command: {args.command}")
    return 1
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest test_herd_mail.py::TestCmdDownload -v`
Expected: 5 passed

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest test_herd_mail.py -v`
Expected: All pass (~61 tests)

- [ ] **Step 6: Commit**

```bash
git add herd_mail.py test_herd_mail.py
git commit -m "Implement download subcommand for attachment retrieval"
```

---

### Task 9: Update module docstring and run_basic_tests

**Files:**
- Modify: `herd_mail.py:1-48` (module docstring)
- Modify: `test_herd_mail.py` (run_basic_tests function)

- [ ] **Step 1: Update module docstring**

Replace the module docstring at the top of `herd_mail.py` (lines 2-48) with:

```python
"""
herd-mail: AI-to-AI communication facilitator for the herd.

A secure, user-friendly wrapper for waggle that handles the full lifecycle
of herd email communication: sending, reading, checking, and downloading.

Commands:
    herd_mail.py send --to recipient@example.com --subject "Hello" --body "Message"
    herd_mail.py list [--folder INBOX] [--limit 20] [--unread] [--human]
    herd_mail.py read <uid> [--folder INBOX] [--human]
    herd_mail.py check [--folder INBOX] [--human]
    herd_mail.py download <uid> [--folder INBOX] [--dest-dir .]
    herd_mail.py config

Environment Variables (see .envrc.template):
    WAGGLE_HOST         SMTP host
    WAGGLE_PORT         SMTP port (default: 465)
    WAGGLE_USER         SMTP/IMAP username
    WAGGLE_PASS         SMTP/IMAP password
    WAGGLE_FROM         From email address
    WAGGLE_NAME         Display name
    WAGGLE_TLS          Use TLS (default: true)
    WAGGLE_IMAP_HOST    IMAP host (required for list/read/check/download)
    WAGGLE_IMAP_PORT    IMAP port (default: 993)
    WAGGLE_IMAP_TLS     Use IMAP TLS (default: true)
    WAGGLE_TO           Default test recipient
    WAGGLE_SEND_LOG     Path to send log (for duplicate detection)
    WAGGLE_DEV_PATH     Optional: Path to local waggle for development

Author: O.C.
License: MIT
"""
```

- [ ] **Step 2: Update run_basic_tests in test_herd_mail.py**

Replace the `run_basic_tests` function with:

```python
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
```

- [ ] **Step 3: Run full suite**

Run: `python3 -m pytest test_herd_mail.py -v`
Expected: All pass (~61 tests)

- [ ] **Step 4: Commit**

```bash
git add herd_mail.py test_herd_mail.py
git commit -m "Update docstring for subcommand usage and refresh basic tests"
```

---

### Task 10: Update CLAUDE.md and README.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

- [ ] **Step 1: Update CLAUDE.md**

Update the Development Commands and Architecture sections to reflect the new subcommand structure. Key changes:

- Add list/read/check/download examples to "Running the script" section
- Update Architecture section to describe subcommand dispatch
- Add note about JSON output for AI agents
- Update the Core Flow section to include read-side flow

- [ ] **Step 2: Update README.md**

Key changes to README.md:

- Update Quick Start with new subcommand syntax
- Add "Reading Mail" section with list/read/check/download examples
- Update Command Line Reference with all subcommands
- Update the "How It Works" section
- Note the backward compatibility for old-style send invocations

- [ ] **Step 3: Run tests one final time**

Run: `python3 -m pytest test_herd_mail.py -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "Update documentation for subcommand CLI structure"
```
