# Sent Folder Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add IMAP Sent folder sync to herd-mail so sent emails are actually saved, replacing the current misleading log message.

**Architecture:** New `save_to_sent()` function builds an RFC822 message from send parameters and appends it via `imaplib`. Called from `cmd_send` after successful SMTP delivery. Failure is non-fatal (warning only).

**Tech Stack:** Python stdlib: `imaplib`, `email.message.EmailMessage`, `email.utils.formatdate`

---

### File Map

- **Modify:** `herd_mail.py` — add `save_to_sent()`, add imports, update `cmd_send` call site
- **Modify:** `test_herd_mail.py` — add `TestSaveToSent` class, update existing send tests to mock `save_to_sent`

---

### Task 1: Implement `save_to_sent()` with tests

**Files:**
- Modify: `herd_mail.py:35-43` (imports), after `build_waggle_config` at line 395 (new function)
- Modify: `test_herd_mail.py` (new TestSaveToSent class)

- [ ] **Step 1: Write tests for save_to_sent**

Add to `test_herd_mail.py`, before `TestWaggleStubs`:

```python
class TestSaveToSent(unittest.TestCase):
    """Test IMAP Sent folder sync."""

    def _make_cfg(self):
        return {
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "smtp_user": "user@example.com",
            "smtp_pass": "secret",
            "from_addr": "user@example.com",
            "from_name": "Test User",
            "use_tls": True,
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "imap_tls": True,
        }

    @patch('herd_mail.imaplib.IMAP4_SSL')
    def test_save_successful(self, mock_imap_cls):
        """Test successful save to Sent folder."""
        mock_conn = MagicMock()
        mock_imap_cls.return_value = mock_conn
        mock_conn.login.return_value = ('OK', [b'Logged in'])
        mock_conn.list.return_value = ('OK', [b'(\\HasNoChildren) "/" "Sent"'])
        mock_conn.append.return_value = ('OK', [b'APPEND completed'])

        result = hm.save_to_sent(
            self._make_cfg(), "friend@example.com", "Hello", "Hi there!",
        )

        self.assertTrue(result)
        mock_conn.login.assert_called_once_with("user@example.com", "secret")
        mock_conn.append.assert_called_once()
        call_args = mock_conn.append.call_args[0]
        self.assertEqual(call_args[0], '"Sent"')
        mock_conn.logout.assert_called_once()

    @patch('herd_mail.imaplib.IMAP4_SSL')
    def test_save_connection_failure(self, mock_imap_cls):
        """Test save returns False on connection failure."""
        mock_imap_cls.side_effect = OSError("Connection refused")

        result = hm.save_to_sent(
            self._make_cfg(), "friend@example.com", "Hello", "Hi!",
        )

        self.assertFalse(result)

    @patch('herd_mail.imaplib.IMAP4_SSL')
    def test_save_folder_fallback(self, mock_imap_cls):
        """Test fallback to 'Sent Items' when 'Sent' not found."""
        mock_conn = MagicMock()
        mock_imap_cls.return_value = mock_conn
        mock_conn.login.return_value = ('OK', [b'Logged in'])
        mock_conn.list.return_value = ('OK', [b'(\\HasNoChildren) "/" "Sent Items"'])
        mock_conn.append.return_value = ('OK', [b'APPEND completed'])

        result = hm.save_to_sent(
            self._make_cfg(), "friend@example.com", "Hello", "Hi!",
        )

        self.assertTrue(result)
        call_args = mock_conn.append.call_args[0]
        self.assertEqual(call_args[0], '"Sent Items"')

    @patch('herd_mail.imaplib.IMAP4')
    def test_save_non_tls(self, mock_imap_cls):
        """Test non-TLS IMAP connection."""
        mock_conn = MagicMock()
        mock_imap_cls.return_value = mock_conn
        mock_conn.login.return_value = ('OK', [b'Logged in'])
        mock_conn.list.return_value = ('OK', [b'(\\HasNoChildren) "/" "Sent"'])
        mock_conn.append.return_value = ('OK', [b'APPEND completed'])

        cfg = self._make_cfg()
        cfg["imap_tls"] = False

        result = hm.save_to_sent(cfg, "friend@example.com", "Hello", "Hi!")

        self.assertTrue(result)
        mock_imap_cls.assert_called_once_with("imap.example.com", 993)

    @patch('herd_mail.imaplib.IMAP4_SSL')
    def test_save_message_headers(self, mock_imap_cls):
        """Test RFC822 message has correct headers."""
        mock_conn = MagicMock()
        mock_imap_cls.return_value = mock_conn
        mock_conn.login.return_value = ('OK', [b'Logged in'])
        mock_conn.list.return_value = ('OK', [b'(\\HasNoChildren) "/" "Sent"'])
        mock_conn.append.return_value = ('OK', [b'APPEND completed'])

        hm.save_to_sent(
            self._make_cfg(), "friend@example.com", "Hello", "Hi there!",
            cc="other@example.com", reply_to="reply@example.com",
            in_reply_to="<orig@example.com>", references="<ref@example.com>",
        )

        call_args = mock_conn.append.call_args[0]
        msg_bytes = call_args[2]  # third positional arg is the message bytes
        msg_str = msg_bytes.decode('utf-8') if isinstance(msg_bytes, bytes) else msg_bytes
        self.assertIn("From: Test User <user@example.com>", msg_str)
        self.assertIn("To: friend@example.com", msg_str)
        self.assertIn("Subject: Hello", msg_str)
        self.assertIn("Cc: other@example.com", msg_str)
        self.assertIn("Reply-To: reply@example.com", msg_str)
        self.assertIn("In-Reply-To: <orig@example.com>", msg_str)
        self.assertIn("References: <ref@example.com>", msg_str)
        self.assertIn("Hi there!", msg_str)

    @patch('herd_mail.imaplib.IMAP4_SSL')
    def test_save_no_matching_folder(self, mock_imap_cls):
        """Test returns False when no Sent folder found."""
        mock_conn = MagicMock()
        mock_imap_cls.return_value = mock_conn
        mock_conn.login.return_value = ('OK', [b'Logged in'])
        mock_conn.list.return_value = ('OK', [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "Drafts"'])

        result = hm.save_to_sent(
            self._make_cfg(), "friend@example.com", "Hello", "Hi!",
        )

        self.assertFalse(result)
        mock_conn.append.assert_not_called()
        mock_conn.logout.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_herd_mail.py::TestSaveToSent -v`
Expected: FAIL — `hm.save_to_sent` not found

- [ ] **Step 3: Add imports to herd_mail.py**

Add `imaplib` to the imports at the top of `herd_mail.py` (around line 38, with the other stdlib imports). Also add `email.message` and `email.utils.formatdate`:

```python
import imaplib
from email.message import EmailMessage
from email.utils import formatdate, parseaddr
```

Note: `parseaddr` is already imported from `email.utils` — merge the import line so it reads:

```python
from email.utils import formatdate, parseaddr
```

- [ ] **Step 4: Add SENT_FOLDER_CANDIDATES constant**

Add near the other constants (around line 51):

```python
SENT_FOLDER_CANDIDATES = ["Sent", "Sent Items", "INBOX.Sent"]
```

- [ ] **Step 5: Implement save_to_sent**

Add after `build_waggle_config` (after line 395) and before `output_json`:

```python
def save_to_sent(
    cfg: dict[str, Any],
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    reply_to: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
) -> bool:
    """
    Save a copy of the sent message to the IMAP Sent folder.

    Returns True if saved, False on any failure. Failures are non-fatal.
    """
    wcfg = build_waggle_config(cfg)

    # Build RFC822 message
    msg = EmailMessage()
    from_display = f"{wcfg['from_name']} <{wcfg['from_addr']}>" if wcfg.get("from_name") else wcfg["from_addr"]
    msg["From"] = from_display
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    if cc:
        msg["Cc"] = cc
    if reply_to:
        msg["Reply-To"] = reply_to
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.set_content(body)

    msg_bytes = msg.as_bytes()

    try:
        # Connect to IMAP
        if wcfg.get("imap_tls", True):
            conn = imaplib.IMAP4_SSL(wcfg["imap_host"], wcfg.get("imap_port", DEFAULT_IMAP_PORT))
        else:
            conn = imaplib.IMAP4(wcfg["imap_host"], wcfg.get("imap_port", DEFAULT_IMAP_PORT))

        try:
            conn.login(wcfg["user"], wcfg["password"])

            # Find the Sent folder
            status, folder_data = conn.list()
            folder_names = []
            if status == "OK" and folder_data:
                for item in folder_data:
                    if isinstance(item, bytes):
                        decoded = item.decode("utf-8", errors="replace")
                        # Extract folder name from IMAP LIST response
                        # Format: (flags) "delimiter" "name"
                        parts = decoded.rsplit('"', 2)
                        if len(parts) >= 2:
                            folder_names.append(parts[-2])

            sent_folder = None
            for candidate in SENT_FOLDER_CANDIDATES:
                if candidate in folder_names:
                    sent_folder = candidate
                    break

            if not sent_folder:
                logger.warning(f"No Sent folder found (tried: {', '.join(SENT_FOLDER_CANDIDATES)})")
                return False

            # Append message
            status, _ = conn.append(f'"{sent_folder}"', "\\Seen", None, msg_bytes)
            if status != "OK":
                logger.warning(f"IMAP APPEND failed: {status}")
                return False

            return True

        finally:
            try:
                conn.logout()
            except Exception:
                pass

    except (OSError, imaplib.IMAP4.error) as e:
        logger.warning(f"Could not save to Sent folder: {e}")
        return False
    except Exception as e:
        logger.warning(f"Unexpected error saving to Sent folder: {e}")
        return False
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest test_herd_mail.py::TestSaveToSent -v`
Expected: 6 passed

- [ ] **Step 7: Run full suite**

Run: `python3 -m pytest test_herd_mail.py -v`
Expected: 67 passed (61 existing + 6 new)

- [ ] **Step 8: Commit**

```bash
git add herd_mail.py test_herd_mail.py
git commit -m "Add save_to_sent() for IMAP Sent folder sync"
```

---

### Task 2: Wire save_to_sent into cmd_send and fix misleading log

**Files:**
- Modify: `herd_mail.py:550-571` (cmd_send after send_email call)
- Modify: `test_herd_mail.py` (update TestMain send tests, add integration tests)

- [ ] **Step 1: Write integration tests**

Add to `test_herd_mail.py`, after `TestSaveToSent`:

```python
class TestSendWithSentSync(unittest.TestCase):
    """Test cmd_send integration with save_to_sent."""

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

    @patch('herd_mail.save_to_sent')
    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_save_called_with_imap(self, mock_check, mock_send, mock_save):
        """Test save_to_sent is called when IMAP is configured."""
        mock_check.return_value = False
        mock_send.return_value = None
        mock_save.return_value = True
        os.environ["WAGGLE_IMAP_HOST"] = "imap.example.com"

        with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi!']):
            result = hm.main()

        self.assertEqual(result, 0)
        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args
        self.assertEqual(call_kwargs[0][1], "friend@example.com")  # to
        self.assertEqual(call_kwargs[0][2], "Hello")  # subject

    @patch('herd_mail.save_to_sent')
    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_save_not_called_without_imap(self, mock_check, mock_send, mock_save):
        """Test save_to_sent is NOT called when IMAP is not configured."""
        mock_check.return_value = False
        mock_send.return_value = None

        with patch('sys.argv', ['herd_mail.py', 'send', '--to', 'friend@example.com',
                                '--subject', 'Hello', '--body', 'Hi!']):
            result = hm.main()

        self.assertEqual(result, 0)
        mock_save.assert_not_called()
```

- [ ] **Step 2: Run tests to see failures**

Run: `python3 -m pytest test_herd_mail.py::TestSendWithSentSync -v`
Expected: FAIL — save_to_sent not called in cmd_send yet

- [ ] **Step 3: Update cmd_send to call save_to_sent**

In `herd_mail.py`, find the section in `cmd_send` after `send_email()` succeeds (around lines 567-571). Replace:

```python
        logger.info("Email sent successfully!")
        if cfg.get("imap_host"):
            logger.info("  (Saved to Sent folder via IMAP)")

        return 0
```

With:

```python
        saved = False
        if cfg.get("imap_host"):
            saved = save_to_sent(
                cfg, args.to, args.subject, body,
                cc=args.cc, reply_to=args.reply_to,
                in_reply_to=in_reply_to, references=references,
            )

        logger.info("Email sent successfully!")
        if saved:
            logger.info("  (Saved to Sent folder via IMAP)")
        elif cfg.get("imap_host"):
            logger.warning("  (Could not save to Sent folder)")

        return 0
```

- [ ] **Step 4: Update existing TestMain send tests to mock save_to_sent**

In `test_herd_mail.py`, update the existing send tests in `TestMain` that mock `send_email` so they also mock `save_to_sent`. This prevents tests from attempting real IMAP connections if `WAGGLE_IMAP_HOST` happens to be set.

Add `@patch('herd_mail.save_to_sent')` decorator to these tests (add it as the outermost decorator so it's the last parameter):

In `test_send_simple_email`:
```python
    @patch('herd_mail.save_to_sent')
    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_send_simple_email(self, mock_check_duplicate, mock_send, mock_save):
```

In `test_skip_duplicate_check`:
```python
    @patch('herd_mail.save_to_sent')
    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_skip_duplicate_check(self, mock_check_duplicate, mock_send, mock_save):
```

In `test_with_attachments`:
```python
    @patch('herd_mail.save_to_sent')
    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_with_attachments(self, mock_check_duplicate, mock_send, mock_save):
```

In `test_escape_sequences_in_body`:
```python
    @patch('herd_mail.save_to_sent')
    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_escape_sequences_in_body(self, mock_check_duplicate, mock_send, mock_save):
```

Also update `TestBodyLoading` tests:

In `test_body_from_file`:
```python
    @patch('herd_mail.save_to_sent')
    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_body_from_file(self, mock_check_duplicate, mock_send, mock_save):
```

In `test_body_from_stdin`:
```python
    @patch('herd_mail.save_to_sent')
    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_body_from_stdin(self, mock_check_duplicate, mock_send, mock_save):
```

Also update `TestBackwardCompat`:

In `test_old_style_send`:
```python
    @patch('herd_mail.save_to_sent')
    @patch('herd_mail.send_email')
    @patch('herd_mail.check_recently_sent')
    def test_old_style_send(self, mock_check, mock_send, mock_save):
```

- [ ] **Step 5: Run all tests**

Run: `python3 -m pytest test_herd_mail.py -v`
Expected: 69 passed (67 + 2 new integration tests)

- [ ] **Step 6: Commit**

```bash
git add herd_mail.py test_herd_mail.py
git commit -m "Wire save_to_sent into cmd_send and fix misleading log message"
```

---

### Task 3: Update documentation

**Files:**
- Modify: `README.md` — fix Sent folder sync description
- Modify: `CLAUDE.md` — update architecture notes

- [ ] **Step 1: Update README.md**

Find the "Sent Folder Sync" mention in the Features section and the troubleshooting section. Ensure the README accurately describes that:
- Sent folder sync works when `WAGGLE_IMAP_HOST` is configured
- It saves a plain text copy (no attachments) to the Sent folder
- It tries `Sent`, `Sent Items`, `INBOX.Sent` folder names
- Failure is non-fatal (warning logged, email still sent)

- [ ] **Step 2: Update CLAUDE.md**

In the Architecture / Core Flow section, update step 7 to note that Sent folder sync is implemented in herd-mail (not waggle):

Update the "IMAP Sync" line in the Core Flow to:
```
7. **Sent Folder Sync** — herd-mail appends plain text copy to IMAP Sent folder (if configured)
```

- [ ] **Step 3: Run tests one final time**

Run: `python3 -m pytest test_herd_mail.py -v`
Expected: 69 passed

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "Update documentation for Sent folder sync implementation"
```
