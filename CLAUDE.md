# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

herd-mail is a CLI wrapper for [waggle](https://github.com/jasonacox-sam/waggle-mail) designed for AI-to-AI email communication. It handles Markdown→HTML conversion, threading, duplicate prevention, IMAP Sent folder synchronization, and message reading with attachment downloads.

This is a standalone Python script, not a package. No build system or setup.py required.

**Version 3.5**: Subcommand-based CLI (`send`, `list`, `read`, `check`, `download`, `flag`, `move`, `stats`, `config`, `search`). JSON-first output for AI agents (stdout=JSON, stderr=logging). `--human` for readable output. Version tracked via `__version__` in `herd_mail.py`, `--version` flag, and `config` output. Keep `__version__` and `pyproject.toml` version in sync.

## Development Commands

```bash
# Activate the venv (Python 3.14)
source .venv/bin/activate

# Run full test suite
python3 -m pytest test_herd_mail.py -v

# Run a single test class
python3 -m pytest test_herd_mail.py::TestConfig -v

# Run a single test
python3 -m pytest test_herd_mail.py::TestConfig::test_get_config_defaults -v

# Run without pytest
python3 test_herd_mail.py

# Validate configuration (requires .envrc sourced)
python3 herd_mail.py config
```

**Test Coverage**: ~95% | **Tests**: 105 passing

Tests mock SMTP/IMAP so they run without real credentials. Tests use `unittest.TestCase` classes, not pytest fixtures.

### Dependencies

Defined in `pyproject.toml`. Install with:
```bash
pip install .                    # Core (waggle-mail)
pip install ".[rich]"            # + markdown/pygments for --rich flag
pip install ".[dev]"             # + pytest
```

## Configuration

All configuration via environment variables. The `.envrc` file is **never committed** (see .gitignore).

```bash
cp .envrc.template .envrc
# Edit .envrc with real credentials
source .envrc  # or use direnv
```

Required vars: `WAGGLE_HOST`, `WAGGLE_USER`, `WAGGLE_PASS`, `WAGGLE_FROM`

Optional vars: `WAGGLE_IMAP_HOST` (required for read commands), `WAGGLE_IMAP_PORT`, `WAGGLE_IMAP_TLS`, `WAGGLE_SEND_LOG`, `WAGGLE_DEV_PATH`

## Architecture

### Single-file Design

Everything lives in `herd_mail.py` (~1300 lines) with tests in `test_herd_mail.py` (~1750 lines). No package structure.

### Subcommand Dispatch

`main()` parses args and dispatches to `cmd_*()` handlers. Each handler receives `(args, cfg)` and returns an exit code (0=success, 1=error, with `cmd_check` using 0=has unread, 1=none, 2=error).

**Backward compatibility**: Old-style `herd_mail.py --to ...` is detected in `main()` and routed to `cmd_send()` with a deprecation warning.

### Two Config Formats

1. **herd-mail format** (`get_config()`) — `WAGGLE_` prefixed env vars → dict with keys like `smtp_host`, `smtp_pass`
2. **waggle format** (`build_waggle_config()`) — translates to waggle's expected keys (`host`, `password`, etc.)

Every `cmd_*` handler calls `get_config()` then passes `build_waggle_config(cfg)` to waggle functions.

### waggle Integration

herd-mail is a thin wrapper. waggle provides: `send_email()`, `check_recently_sent()`, `read_message()`, `list_inbox()`, `download_attachments()`, `move_message()`. herd-mail adds: env-based config, CLI parsing, threading, JSON output, Sent folder sync, IMAP flag management.

If waggle isn't installed, stub functions are created at module level so the module can still be imported for testing. The `WAGGLE_AVAILABLE` flag gates actual usage in `main()`.

### IMAP Flag Management

`imap_store_flags()` is herd-mail's own IMAP UID STORE implementation (waggle has no flag API). It handles `\Seen`, `\Answered`, `\Flagged` via a whitelist (`ALLOWED_IMAP_FLAGS`). Used by:
- `cmd_flag()` — explicit flag add/remove subcommand
- `cmd_read()` — auto-marks `\Seen` after display (opt-out: `--no-mark-read`)
- `cmd_send()` — auto-marks `\Seen`+`\Answered` on original message when replying via `--message-id`

Auto-flag operations are non-fatal (warning on failure, command still succeeds).

### Sent Folder Sync

`save_to_sent()` is herd-mail's own IMAP APPEND implementation (not waggle). It saves a plain-text copy to the Sent folder after sending. Folder discovery tries candidates: `Sent`, `Sent Items`, `INBOX.Sent`. Failures are non-fatal.

### Output Design

- **stdout**: JSON via `output_json()` for machine consumption
- **stderr**: logging for humans
- `--human` flag on `list`/`read`/`check`/`flag`/`move` switches to human-readable stdout formatters (`output_human_*`)

### Body Loading Priority (send)

1. `--body-file` (reads from file)
2. `--body` (command line, with escape sequence decoding)
3. stdin (if not a tty)
4. Default: "(No message body)"

## Security

Key protections:
- Email header injection prevention (validates addresses)
- Path traversal protection (blocks sensitive dirs like `/etc`, `/proc`)
- ANSI escape stripping for terminal output
- No hardcoded credentials or paths (`WAGGLE_DEV_PATH` is opt-in)

## Python Standards

Follow user's global rules:
- Type hints for function signatures
- pathlib for file operations
- f-strings for formatting
- logging module, not print statements
