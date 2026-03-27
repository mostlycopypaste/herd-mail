# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

herd-mail is a CLI wrapper for [waggle](https://github.com/jasonacox-sam/waggle-mail) designed for AI-to-AI email communication. It handles Markdown→HTML conversion, threading, duplicate prevention, and IMAP Sent folder synchronization.

This is a standalone Python script, not a package. No build system or setup.py required.

## Development Commands

### Running the script
```bash
# Requires environment setup first (see Configuration below)
python3 herd_mail.py --to recipient@example.com --subject "Test" --body "Hello"

# With markdown file
python3 herd_mail.py --to recipient@example.com --subject "Test" --body-file message.md

# Reply to message (thread-aware)
python3 herd_mail.py --message-id 42 --to sender@example.com --subject "Re: Hello"

# Validate configuration without sending
python3 herd_mail.py --dry-run
```

### Testing
```bash
# Full test suite (requires pytest)
pip install pytest
python3 -m pytest test_herd_mail.py -v

# Run single test
python3 -m pytest test_herd_mail.py::TestConfig::test_get_config_defaults -v

# Without pytest (basic validation)
python3 test_herd_mail.py
```

Tests mock SMTP/IMAP so they run without real credentials.

### Dependencies
```bash
# Required
pip install waggle-mail

# Optional (for --rich flag)
pip install markdown pygments
```

## Configuration

All configuration via environment variables. The `.envrc` file is **never committed** (see .gitignore).

Setup:
```bash
cp .envrc.template .envrc
# Edit .envrc with real credentials
source .envrc  # or use direnv
```

Required vars: `WAGGLE_HOST`, `WAGGLE_USER`, `WAGGLE_PASS`, `WAGGLE_FROM`

Optional vars: See `.envrc.template` for full list (IMAP settings, send log path, etc.)

## Architecture

### Core Flow
1. **Config Loading** (`get_config()`) - Read env vars with defaults
2. **Validation** (`validate_config()`) - Check required fields present
3. **Duplicate Check** (optional) - Query send log via waggle
4. **Message Building** - Convert Markdown to multipart (HTML + plain text)
5. **Thread Handling** - If replying, fetch original via IMAP for headers
6. **Send** - SMTP delivery via waggle's `send_email()`
7. **IMAP Sync** - Save copy to Sent folder (if IMAP configured)
8. **Logging** - Record send for duplicate detection

### waggle Integration

This script is a thin wrapper around waggle's core functions:
- `send_email()` - Main sending logic with Markdown support
- `check_recently_sent()` - Duplicate detection (checks send log)
- `read_message()` - Fetch message by ID for threading

The wrapper adds:
- Environment-based configuration
- Config validation with helpful error messages
- CLI argument parsing
- Thread-aware reply handling

### Local Development Path

Lines 56-58 in `herd_mail.py` add local waggle dev path if present:
```python
LOCAL_WAGGLE = Path("/Volumes/RayCue-Drive/Documents/openclaw/.openclaw/workspace/projects/waggle")
if LOCAL_WAGGLE.exists():
    sys.path.insert(0, str(LOCAL_WAGGLE))
```

This allows testing unreleased waggle changes. Remove or adjust this path if it causes issues.

## Code Patterns

### Config Translation

Two config formats exist:
1. **herd-mail format** (`get_config()`) - Uses WAGGLE_ prefixed env vars
2. **waggle format** (`build_waggle_config()`) - Internal format expected by waggle functions

Translation happens via `build_waggle_config()` which maps:
- `smtp_host` → `host`
- `smtp_pass` → `password`
- etc.

### Error Handling

- Configuration errors → exit 1 with helpful message
- Missing body file → exit 1
- Duplicate detected → exit 0 (not an error, just skipped)
- Send failure → exit 1
- Thread fetch failure → warning, continue without threading

### Body Loading Priority

1. `--body-file` (reads from file)
2. `--body` (command line arg with escape sequence decoding)
3. stdin (if not a tty)
4. Default: "(No message body)"

## Security

**Version 2.0** includes comprehensive security hardening. See `SECURITY_FIXES.md` for full details.

Built-in protections:
- Email header injection prevention (validates all email addresses)
- Path traversal protection (validates file paths, blocks sensitive directories)
- Input validation (ports, email addresses, file paths)
- Output sanitization (prevents terminal escape sequence injection)
- No hardcoded credentials or paths (development path requires explicit env var)
- Credential redaction in logs

Inherits waggle's security hardening:
- Path traversal protection for attachments
- Symlink attack prevention
- Size limits (50MB per file, 200MB per message)
- IMAP injection guards

Never commit `.envrc` - it contains SMTP/IMAP credentials.

**Development Mode**: Set `WAGGLE_DEV_PATH` environment variable to use local waggle. This is intentionally opt-in for security.

## Python Standards

Follow user's global rules:
- Type hints for function signatures
- pathlib for file operations (already used for LOCAL_WAGGLE)
- f-strings for formatting (already used throughout)
- logging module for production (currently using print statements - consider switching if this becomes a library)
