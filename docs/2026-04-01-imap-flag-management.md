# IMAP Flag Management Implementation

**Date**: 2026-04-01
**Status**: Implemented, tests passing (97/97)
**Branch**: main (not yet committed)
**waggle version**: upgraded from 1.8.3 to 1.8.7

---

## Problem

herd-mail relied on himalaya for IMAP flag operations (`himalaya flag add <uid> \Seen`), but flags did not persist on Amazon WorkMail. Messages remained unread after marking, breaking the check → read → process → mark-read workflow used by AI agents.

## Solution

Added native IMAP flag management directly in herd-mail using Python's `imaplib`, bypassing himalaya entirely. This follows the same pattern as the existing `save_to_sent()` function, which already uses direct IMAP connections for Sent folder sync.

---

## What Changed

### New Subcommands

#### `flag` — Manual flag management
```bash
# Mark single message as read
herd_mail.py flag add 42 '\Seen'

# Mark multiple messages as read + answered
herd_mail.py flag add 630,631,632 '\Seen' '\Answered'

# Remove flag
herd_mail.py flag remove 42 '\Seen'

# Human-readable output
herd_mail.py flag add 42 '\Seen' --human
```

Allowed flags (whitelist): `\Seen`, `\Answered`, `\Flagged`. The `\Deleted` flag is blocked to prevent accidental message deletion.

#### `move` — Move messages between folders
```bash
herd_mail.py move 42 INBOX.Archive
herd_mail.py move 42 INBOX.Processed --folder INBOX.Review
```

Wraps waggle's existing `move_message()` function (COPY + \Deleted + EXPUNGE).

### Modified Behavior

#### `read` — Auto-marks `\Seen`
```bash
# Reads message AND marks as \Seen (new default)
herd_mail.py read 42

# Read without marking (opt-out)
herd_mail.py read 42 --no-mark-read
```

Previously, `read` used waggle's `read_message()` which always uses `BODY.PEEK[]` (never sets flags). Now, after successfully reading and outputting the message, herd-mail issues a separate `UID STORE +FLAGS (\Seen)` call. This is non-fatal — if the flag operation fails, the read still succeeds with a warning on stderr.

#### `send --message-id` — Auto-marks `\Seen` + `\Answered` on original
```bash
# Reply to message 42, auto-flags original
herd_mail.py send --message-id 42 --to sender@example.com --subject "Re: Hello" --body "Thanks!"
```

After a successful reply send, the original message referenced by `--message-id` is marked with both `\Seen` and `\Answered`. This is also non-fatal.

---

## New Functions

| Function | Location | Purpose |
|----------|----------|---------|
| `normalize_imap_flag(flag)` | ~line 167 | Normalizes flag to canonical form (e.g., `\seen` → `\Seen`) |
| `validate_imap_flags(flags)` | ~line 173 | Validates flags against `ALLOWED_IMAP_FLAGS` whitelist |
| `imap_store_flags(cfg, uids, flags, action, folder)` | ~line 519 | Core IMAP UID STORE helper — add/remove flags on one or more UIDs |
| `output_human_flag(data)` | ~line 645 | Human-readable flag operation output |
| `cmd_flag(args, cfg)` | ~line 958 | Handler for `flag` subcommand |
| `cmd_move(args, cfg)` | ~line 993 | Handler for `move` subcommand |

### `imap_store_flags()` — Design Details

This is the central primitive. All flag operations go through it.

- Connects to IMAP using `ssl.create_default_context()` (matching waggle's `_imap_connect()`)
- Uses `conn.uid("STORE", uid_bytes, "+FLAGS"/"-FLAGS", flag_str)` — the same IMAP command waggle uses internally in `move_message()` for `\Deleted`
- Iterates over each UID individually (bulk = multiple STORE calls in one connection)
- Returns a result dict with per-UID status for JSON output
- `finally` block ensures `conn.logout()` even on errors

---

## Tests Added

28 new tests across 6 test classes (69 → 97 total):

| Class | Tests | What It Covers |
|-------|-------|----------------|
| `TestValidateImapFlags` | 5 | Valid flags, case normalization, without backslash, invalid rejected, mixed |
| `TestImapStoreFlags` | 7 | Add/remove, bulk UIDs, multiple flags, connection failure, non-TLS, select failure |
| `TestCmdFlag` | 6 | JSON output, human output, bulk UIDs, invalid flag, no IMAP, connection error |
| `TestCmdMove` | 4 | Success, human output, failure, no IMAP |
| `TestAutoFlagOnRead` | 3 | Marks \Seen, --no-mark-read skips, failure is non-fatal |
| `TestAutoFlagOnReply` | 3 | Marks \Seen+\Answered, non-reply skips, failure is non-fatal |

All tests mock IMAP via `@patch('herd_mail.imaplib.IMAP4_SSL')`, following the existing `TestSaveToSent` pattern.

---

## waggle API Audit

Performed a full audit of waggle v1.8.7 against herd-mail's usage.

### Now Using All Available Functions

| waggle function | herd-mail usage |
|-----------------|-----------------|
| `send_email()` | `cmd_send()` |
| `check_recently_sent()` | Duplicate detection in `cmd_send()` |
| `read_message()` | `cmd_read()` and reply threading |
| `list_inbox()` | `cmd_list()` and `cmd_check()` |
| `download_attachments()` | `cmd_download()` |
| `move_message()` | **NEW** — `cmd_move()` |

Not yet used: `fetch_quoted_body()` (Outlook-style inline quoting for replies — future enhancement).

### waggle Gaps Identified

These are features herd-mail implements directly because waggle doesn't expose them:

| Gap | herd-mail Workaround | Proposed Upstream Issue |
|-----|---------------------|----------------------|
| No flag management API | `imap_store_flags()` using imaplib directly | Add `set_flags(uid, flags, action, folder, config)` |
| `read_message()` always PEEKs | Separate `imap_store_flags()` call after read (2 IMAP connections) | Add `mark_read=False` parameter |
| No IMAP APPEND | `save_to_sent()` using imaplib directly | Add `append_to_folder(msg_bytes, folder, flags, config)` (on waggle v1.9.0 roadmap) |

### SSL Context Fix

Noticed that `save_to_sent()` uses bare `imaplib.IMAP4_SSL()` without `ssl.create_default_context()`, while waggle's own `_imap_connect()` does use it. The new `imap_store_flags()` uses proper SSL context. `save_to_sent()` should be updated to match (minor hardening, not done in this change).

---

## Changes Between waggle v1.8.3 and v1.8.7

| Version | Change | Impact on herd-mail |
|---------|--------|-------------------|
| 1.8.4 | Bug fix: paragraph wrapping with inline elements | None |
| 1.8.5 | Markdown table rendering in emails | Emails with tables now render properly |
| 1.8.6 | Maildir backend for local reply quoting | None |
| 1.8.7 | Font styling: Georgia → Aptos | Visual change in sent emails |

No new IMAP API was added in any version. Flag management remains a gap.

---

## Outstanding Work

### Immediate (before commit)
- [ ] Manual smoke test on WorkMail: `flag add`, `flag remove`, `read` auto-mark, `send --message-id` auto-flag
- [ ] Verify `move` works on WorkMail folder names

### Future Enhancements
- **Smart CC flagging**: When replying to a CC'd thread (To: others, Cc: includes me), mark `\Seen` only instead of `\Seen`+`\Answered`. Logic would inspect original message's To/Cc headers in `cmd_send()`.
- **`fetch_quoted_body()` integration**: Use waggle's quoting function for inline reply bodies.
- **Fix `save_to_sent()` SSL context**: Add `ssl.create_default_context()` to match `imap_store_flags()`.

### Upstream Contributions
File issues and offer PRs on [jasonacox-sam/waggle-mail](https://github.com/jasonacox-sam/waggle-mail) after manual testing confirms persistence on WorkMail:

1. **Issue: Add IMAP flag management functions** — `set_flags()` public API
2. **Issue: Add `mark_read` parameter to `read_message()`** — switch from `BODY.PEEK[]` to `BODY[]`
3. **Issue: Add IMAP APPEND for Sent folder sync** — already on v1.9.0 roadmap

---

## File Inventory

| File | Lines Changed | What Changed |
|------|--------------|--------------|
| `herd_mail.py` | ~150 added | ssl import, ALLOWED_IMAP_FLAGS, validate_imap_flags, imap_store_flags, output_human_flag, cmd_flag, cmd_move, auto-flag in cmd_read + cmd_send, argparse entries, dispatch dict, move_message import + stub |
| `test_herd_mail.py` | ~280 added | 6 new test classes (28 tests), updated TestWaggleStubs |
| `CLAUDE.md` | Updated | Test count, line count, new subcommands, flag management section |
