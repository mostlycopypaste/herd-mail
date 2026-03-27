# herd-mail Subcommand Refactor — Read/Check/Download Support

**Date:** 2026-03-26
**Status:** Approved

## Problem

herd_mail.py currently only sends email. AI agents in the herd also need to check their inbox, read messages, and download attachments. The underlying waggle library already supports these operations (`list_inbox`, `read_message`, `download_attachments`) but herd-mail doesn't expose them.

## Design

### CLI Structure

Refactor from flat flags to subcommands:

```
herd_mail.py <command> [options]

Commands:
  send       Send an email
  list       List messages in a folder
  read       Read a full message by UID
  check      Check for unread messages (exit code semantics)
  download   Download attachments from a message
  config     Validate configuration
```

Backward compatibility: if no subcommand is given but `--to` is present, dispatch to `send` with a deprecation warning logged to stderr.

### Subcommand Specifications

#### `send`

Unchanged from current behavior. All existing flags preserved.

```
herd_mail.py send --to TO --subject SUBJECT [--body BODY] [--body-file FILE]
    [--attachment FILE ...] [--cc CC] [--reply-to ADDR]
    [--message-id UID] [--rich] [--skip-duplicate-check]
```

Exit codes: 0=sent, 1=error.

#### `list`

```
herd_mail.py list [--folder FOLDER] [--limit N] [--unread] [--human]
```

- `--folder`: IMAP folder (default: `INBOX`)
- `--limit`: Max messages to return (default: 20)
- `--unread`: Only show unread messages
- `--human`: Human-readable table instead of JSON

Exit codes: 0=success, 1=error.

JSON output:
```json
{
  "folder": "INBOX",
  "count": 2,
  "messages": [
    {
      "uid": "145",
      "from_addr": "alice@example.com",
      "from_name": "Alice",
      "subject": "Weekly sync",
      "date": "Mon, 24 Mar 2026 10:00:00 -0400",
      "unread": true,
      "size": 4096
    }
  ]
}
```

#### `read`

```
herd_mail.py read <uid> [--folder FOLDER] [--human]
```

Exit codes: 0=found, 1=error.

JSON output:
```json
{
  "uid": "145",
  "folder": "INBOX",
  "message_id": "<abc123@example.com>",
  "from_addr": "alice@example.com",
  "from_name": "Alice",
  "subject": "Weekly sync",
  "date": "Mon, 24 Mar 2026 10:00:00 -0400",
  "to": "herd@example.com",
  "body_plain": "Hey, here's the update...",
  "body_html": "<html>...",
  "in_reply_to": null,
  "references": null,
  "attachments": [
    {"filename": "report.pdf", "content_type": "application/pdf", "size": 12345}
  ]
}
```

#### `check`

```
herd_mail.py check [--folder FOLDER] [--human]
```

Designed for polling loops: `if herd_mail.py check; then herd_mail.py list --unread; fi`

Exit codes: 0=has unread messages, 1=no unread messages, 2=error.

JSON output:
```json
{
  "folder": "INBOX",
  "unread_count": 3,
  "messages": [...]
}
```

#### `download`

```
herd_mail.py download <uid> [--folder FOLDER] [--dest-dir DIR]
```

- `--dest-dir`: Where to save files (default: `.`, created if needed)

Exit codes: 0=downloaded (or no attachments), 1=error.

JSON output:
```json
{
  "uid": "145",
  "folder": "INBOX",
  "files": ["/absolute/path/report.pdf", "/absolute/path/data.csv"]
}
```

#### `config`

```
herd_mail.py config
```

Validates both SMTP and IMAP configuration. The `--dry-run` flag on `send` is preserved as an alias for backward compatibility (dispatches to `cmd_config` internally).

Exit codes: 0=valid, 1=invalid.

### Output Format Rules

- **JSON mode (default for list/read/check/download):** Only the JSON object goes to stdout. All logging goes to stderr. This lets agents pipe stdout directly to a JSON parser.
- **Human mode (`--human`):** Formatted text to stdout. `list` shows a table, `read` shows headers then body, `check` shows a one-line summary, `download` shows file paths.
- **`send` and `config`:** Keep current behavior (human output to stdout, no JSON mode needed).

### Code Organization

Single file, structured as:

```
herd_mail.py
  Constants, logging, imports
  Validation helpers (existing, unchanged)
  Config helpers (existing; validate_config gets require_imap param)
  Output helpers (new)
    output_json(data)
    output_human_list(data)
    output_human_read(data)
    output_human_check(data)
  Command handlers
    cmd_send(args, cfg)       — extracted from current main()
    cmd_list(args, cfg)       — new
    cmd_read(args, cfg)       — new
    cmd_check(args, cfg)      — new
    cmd_download(args, cfg)   — new
    cmd_config(args, cfg)     — extracted from dry-run logic
  main()                      — argparse subcommand setup, config loading, dispatch
  Backward compat             — no subcommand + --to → cmd_send + deprecation warning
```

### New Waggle Imports

```python
from waggle import send_email, check_recently_sent, read_message, list_inbox, download_attachments
```

With corresponding stubs when waggle is not installed (for testing).

### Config Validation

Read-side commands require IMAP configuration. `validate_config` gains a `require_imap` parameter:

```python
def validate_config(cfg, require_smtp=True, require_imap=False) -> bool:
```

When `require_imap=True`, validates that `imap_host` is set. Commands that need IMAP (`list`, `read`, `check`, `download`) pass `require_imap=True`.

### Error Handling

| Scenario | Behavior |
|----------|----------|
| IMAP not configured | Exit 1 (or 2 for `check`): `"IMAP not configured. Set WAGGLE_IMAP_HOST"` |
| Empty inbox / no unread | `list`: exit 0, empty array. `check`: exit 1, `unread_count: 0` |
| Invalid UID | Exit 1, error to stderr |
| Connection failure | Catch `ConnectionError`, `TimeoutError`, `OSError`. JSON error to stderr. |
| No attachments on download | Exit 0, `files: []` |
| dest-dir doesn't exist | Create it. If creation fails, exit 1. |

### Backward Compatibility

Detection in `main()`:

```
if no subcommand given:
    if --to is present:
        log deprecation warning to stderr
        dispatch to cmd_send
    else:
        print help and exit
```

Existing invocations like `herd_mail.py --to alice@example.com --subject "Hi" --body "Hello"` continue to work with a warning.

### Testing

Same mock-waggle pattern as existing tests. New test classes:

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestCmdList` | 4-5 | JSON output, `--unread`, `--limit`, `--human`, empty inbox |
| `TestCmdRead` | 3-4 | JSON output, `--human`, invalid UID, attachments |
| `TestCmdCheck` | 3-4 | Exit 0 (unread), exit 1 (none), exit 2 (error), JSON |
| `TestCmdDownload` | 3-4 | Saves files, `--dest-dir`, no attachments, invalid UID |
| `TestCmdConfig` | 2 | Valid config, missing IMAP |
| `TestBackwardCompat` | 2 | `--to` without subcommand, no args shows help |

Existing `TestMain` tests updated to use `['herd_mail.py', 'send', ...]` argv.

Target: ~45-50 tests total, up from 30.
