# Sent Folder Sync — Design Spec

**Date:** 2026-03-27
**Status:** Approved

## Problem

herd-mail's `cmd_send` logs "Saved to Sent folder via IMAP" after sending, but waggle v1.8.3's `send_email()` only does SMTP delivery — it never appends to the IMAP Sent folder. The log message is misleading and the feature is not implemented.

## Solution

Add a `save_to_sent()` function in herd_mail.py that builds an RFC822 message from the send parameters and appends it to the IMAP Sent folder after a successful SMTP send.

## Design

### `save_to_sent()` Function

**Signature:**
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
```

**Returns:** `True` if saved successfully, `False` on failure.

**Steps:**
1. Build an RFC822 message using `email.message.EmailMessage` (stdlib) with From, To, Subject, Date, CC, Reply-To, In-Reply-To, References headers and a plain text body.
2. Connect to IMAP using `imaplib.IMAP4_SSL` (or `IMAP4` if `imap_tls` is False) with credentials from `build_waggle_config()` — same `user`/`password` as SMTP.
3. Try appending to Sent folder using common folder names in order: `"Sent"`, `"Sent Items"`, `"INBOX.Sent"`. Use IMAP `LIST` command to check which exists, then `APPEND`.
4. Close and logout the IMAP connection.

**What is NOT included in the Sent copy:**
- No Markdown→HTML conversion (plain text body only — the reference record)
- No attachments (avoids complex MIME reconstruction)

### Call Site in `cmd_send`

After `send_email()` succeeds, before the success log:

```python
send_email(...)

saved = False
if cfg.get("imap_host"):
    saved = save_to_sent(cfg, args.to, args.subject, body,
                         cc=args.cc, reply_to=args.reply_to,
                         in_reply_to=in_reply_to, references=references)

logger.info("Email sent successfully!")
if saved:
    logger.info("  (Saved to Sent folder via IMAP)")
elif cfg.get("imap_host"):
    logger.warning("  (Could not save to Sent folder)")
```

The log message now reflects actual outcome, not just config presence.

### IMAP Connection

Uses the existing IMAP config already in `build_waggle_config()`:
- `imap_host` — server hostname
- `imap_port` — port (default 993)
- `imap_tls` — SSL/TLS toggle
- `user` / `password` — same credentials as SMTP

### Sent Folder Discovery

IMAP servers use different names for the Sent folder. Try these in order:
1. `"Sent"` (most common)
2. `"Sent Items"` (Outlook/Exchange)
3. `"INBOX.Sent"` (namespace-prefixed servers)

Use `IMAP4.list()` to enumerate folders and match against these candidates. If none found, log a warning and return `False`.

### Error Handling

| Scenario | Behavior |
|----------|----------|
| IMAP not configured | Skip entirely (no call to `save_to_sent`) |
| Connection failure | Log warning to stderr, return `False` |
| Auth failure | Log warning to stderr, return `False` |
| No matching Sent folder | Log warning to stderr, return `False` |
| APPEND fails | Log warning to stderr, return `False` |

All failures are non-fatal. The email was already sent via SMTP — Sent folder sync is best-effort.

### Testing

New test class `TestSaveToSent` with ~6-8 tests:

| Test | Behavior |
|------|----------|
| Successful save | Mock IMAP4_SSL, verify APPEND called with correct folder and message |
| Connection failure | Mock IMAP4_SSL to raise, verify returns False, warning logged |
| Folder fallback | First folder not found, second works |
| Non-TLS connection | Verify IMAP4 used instead of IMAP4_SSL |
| Message headers | Verify RFC822 message has correct From/To/Subject/Date/CC/Reply-To |
| Integration: called after send | Mock both send_email and save_to_sent, verify save_to_sent called |
| Integration: skipped without IMAP | No IMAP config, verify save_to_sent not called |
| Integration: log reflects outcome | Verify "Saved to Sent" only on success, warning on failure |

Existing send tests updated to mock `save_to_sent` so they don't attempt real IMAP.

### Scope Boundaries

- No new CLI flags
- No new dependencies (imaplib and email are stdlib)
- No changes to read-side commands
- No retry logic
- No attachment reconstruction
- Intended as a pragmatic workaround until waggle ships native Sent sync
