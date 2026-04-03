# herd-mail 🐝

**Version 3.0** — Production-ready, security-hardened email CLI with reading and sending

AI-to-AI communication facilitator for the herd.

A secure, user-friendly CLI wrapper for [waggle](https://github.com/jasonacox-sam/waggle) that handles the full lifecycle of herd email communication: sending with threading and duplicate prevention, reading with JSON output for AI agents, attachment downloads, and sent-folder synchronization.

## Features

### Sending
- **Markdown → HTML**: Write emails in Markdown, get beautiful HTML + plain text
- **Thread-aware Replies**: Auto-fetch original messages for proper threading
- **Attachments**: Send files with security validation
- **Duplicate Prevention**: Checks send log to prevent accidental resends
- **Sent Folder Sync**: Saves plain text copy to IMAP Sent folder (when IMAP configured)

### Reading
- **List Messages**: JSON output for AI agents, human-readable for interactive use
- **Read Messages**: Full message content with headers, auto-marks as read
- **Check for Unread**: Polling-friendly exit codes (0=has unread, 1=none, 2=error)
- **Download Attachments**: Save attachments with path validation

### Flag & Move
- **Flag Management**: Add/remove `\Seen`, `\Answered`, `\Flagged` on messages
- **Bulk Operations**: Comma-separated UIDs for batch flagging
- **Move Messages**: Move between IMAP folders (archive, triage, etc.)
- **Auto-Flagging**: `read` marks `\Seen`; `send --message-id` marks `\Seen`+`\Answered`

### General
- **Subcommand CLI**: `send`, `list`, `read`, `check`, `download`, `flag`, `move`, `config`
- **JSON-first Output**: Stdout for data, stderr for logging (AI-agent friendly)
- **Environment-based**: No hardcoded credentials in scripts
- **Security Hardened**: Email validation, path validation, injection prevention
- **Type Safe**: Full type hints for Python 3.8+
- **Backward Compatible**: Old `--to` syntax still works with deprecation warning

## Quick Start

```bash
# Clone and enter directory
git clone <this-repo>
cd herd-mail

# Install dependencies
pip install waggle-mail

# Optional: rich formatting
pip install markdown pygments

# Set up environment
cp .envrc.template .envrc
# Edit .envrc with your credentials
source .envrc

# Validate configuration
python3 herd_mail.py config

# Send a test email
python3 herd_mail.py send --to friend@example.com --subject "Hello" --body "Hi from herd-mail!"
```

## Installation

### Prerequisites

- Python 3.8+
- pip

### Install waggle

[waggle](https://github.com/jasonacox-sam/waggle-mail) is the underlying email library that powers herd-mail. It handles multipart email (Markdown → HTML + plain text), IMAP operations, and security-hardened attachment handling.

```bash
pip install waggle-mail
```

### Optional: Rich Formatting

For syntax-highlighted code blocks in emails:

```bash
pip install markdown pygments
```

Then use `--rich` flag when sending.

## Configuration

All configuration is via environment variables. Copy the template and fill in your values:

```bash
cp .envrc.template .envrc
```

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `WAGGLE_HOST` | SMTP server hostname | `smtp.gmail.com` |
| `WAGGLE_PORT` | SMTP port (usually 465 for SSL) | `465` |
| `WAGGLE_USER` | SMTP username | `you@gmail.com` |
| `WAGGLE_PASS` | SMTP password or app password | `your-app-password` |
| `WAGGLE_FROM` | From email address | `you@gmail.com` |
| `WAGGLE_NAME` | Display name | `Your Name` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `WAGGLE_TLS` | Use TLS/SSL | `true` |
| `WAGGLE_IMAP_HOST` | IMAP server (for Sent folder) | (none) |
| `WAGGLE_IMAP_PORT` | IMAP port | `993` |
| `WAGGLE_IMAP_TLS` | Use IMAP SSL | `true` |
| `WAGGLE_TO` | Default test recipient | (none) |
| `WAGGLE_SEND_LOG` | Path to send log | `~/.local/share/waggle-sent.log` |
| `WAGGLE_DEV_PATH` | Path to local waggle (development only) | (none) |

### Security Note

`.envrc` is in `.gitignore` — never commit real credentials! The template shows the structure without exposing secrets.

## Usage

### Validate Configuration

Check that all required environment variables are set:

```bash
python3 herd_mail.py config
```

### Send a Simple Email

```bash
python3 herd_mail.py send \
  --to friend@example.com \
  --subject "Hello from herd-mail" \
  --body "This is a test email!"
```

### Send with Markdown Body from File

```bash
python3 herd_mail.py send \
  --to friend@example.com \
  --subject "Weekly Update" \
  --body-file message.md
```

Example `message.md`:

```markdown
# Weekly Update

Here's what happened this week:

- **Feature A** launched
- Bug fixes in **Module B**

## Code Sample

```python
def hello():
    print("Hello, world!")
```
```

### Reply to a Message (Threading)

```bash
python3 herd_mail.py send \
  --message-id 42 \
  --to sender@example.com \
  --subject "Re: Original Subject" \
  --body "Thanks for your email!"
```

This automatically:
- Fetches the original message from IMAP
- Sets `In-Reply-To` and `References` headers
- Maintains proper email threading

### Send with Attachment

```bash
python3 herd_mail.py send \
  --to friend@example.com \
  --subject "Document" \
  --body "See attached" \
  --attachment report.pdf
```

Multiple attachments:

```bash
python3 herd_mail.py send \
  --to friend@example.com \
  --subject "Files" \
  --attachment file1.pdf file2.txt file3.png
```

### Rich HTML Formatting

```bash
python3 herd_mail.py send \
  --to friend@example.com \
  --subject "Code Review" \
  --body-file code-review.md \
  --rich
```

Adds syntax highlighting for code blocks.

### Pipe Body from Stdin

```bash
cat message.txt | python3 herd_mail.py send \
  --to friend@example.com \
  --subject "Hello"
```

## Reading Mail

### List Messages

JSON output (for AI agents):

```bash
python3 herd_mail.py list
```

Human-readable output:

```bash
python3 herd_mail.py list --human
```

List only unread messages:

```bash
python3 herd_mail.py list --unread --human
```

### Read a Specific Message

```bash
# JSON output
python3 herd_mail.py read 42

# Human-readable
python3 herd_mail.py read 42 --human
```

### Check for Unread Messages

Useful for polling loops. Exit codes:
- `0` - Has unread messages
- `1` - No unread messages
- `2` - Error

```bash
if python3 herd_mail.py check; then
    echo "You have unread messages"
    python3 herd_mail.py list --unread
fi
```

### Download Attachments

```bash
# Download to current directory
python3 herd_mail.py download 42

# Download to specific directory
python3 herd_mail.py download 42 --dest-dir ./attachments
```

### Manage Flags

```bash
# Mark a message as read
python3 herd_mail.py flag add 42 '\Seen'

# Mark multiple messages as read and answered
python3 herd_mail.py flag add 630,631,632 '\Seen' '\Answered'

# Remove a flag
python3 herd_mail.py flag remove 42 '\Flagged'
```

Allowed flags: `\Seen`, `\Answered`, `\Flagged`.

### Move Messages

```bash
# Move to archive
python3 herd_mail.py move 42 INBOX.Archive

# Move from a specific source folder
python3 herd_mail.py move 42 INBOX.Processed --folder INBOX.Review
```

### Backward Compatibility

Old-style syntax still works with a deprecation warning:

```bash
# This works but shows a warning
python3 herd_mail.py --to friend@example.com --subject "Hello" --body "Hi!"
```

Recommended to use `send` subcommand instead.

## Command Line Reference

### Main Command

```
usage: herd_mail.py [-h] {config,send,list,read,check,download,flag,move} ...

herd-mail: AI-to-AI email communication via waggle

subcommands:
  {config,send,list,read,check,download,flag,move}
    config              Validate configuration
    send                Send an email
    list                List messages
    read                Read a specific message (auto-marks as read)
    check               Check for unread messages (exit 0=has unread, 1=none, 2=error)
    download            Download attachments from a message
    flag                Add or remove IMAP flags on messages
    move                Move a message to another folder
```

### config subcommand

```
usage: herd_mail.py config [-h]

Validate configuration without connecting
```

### send subcommand

```
usage: herd_mail.py send [-h] --to TO --subject SUBJECT [--body BODY]
                         [--body-file BODY_FILE] [--attachment ATTACHMENT [ATTACHMENT ...]]
                         [--cc CC] [--reply-to REPLY_TO] [--message-id MESSAGE_ID]
                         [--rich] [--skip-duplicate-check]

options:
  --to TO               Recipient email address
  --subject SUBJECT     Email subject line
  --body BODY           Email body (Markdown supported)
  --body-file BODY_FILE
                        Read body from file (UTF-8)
  --attachment ATTACHMENT [ATTACHMENT ...]
                        File(s) to attach
  --cc CC               CC recipients (comma-separated)
  --reply-to REPLY_TO   Reply-To address
  --message-id MESSAGE_ID
                        IMAP message ID to reply to (enables threading)
  --rich                Enable rich HTML formatting
  --skip-duplicate-check
                        Skip checking for recent duplicates
```

### list subcommand

```
usage: herd_mail.py list [-h] [--unread] [--human]

options:
  --unread              Show only unread messages
  --human               Human-readable output (default: JSON)
```

### read subcommand

```
usage: herd_mail.py read [-h] [--human] [--no-mark-read] uid

positional arguments:
  uid              Message UID to read

options:
  --human          Human-readable output (default: JSON)
  --no-mark-read   Don't mark message as read after displaying
```

Reading a message automatically marks it as `\Seen`. Use `--no-mark-read` to prevent this.

### check subcommand

```
usage: herd_mail.py check [-h]

Check for unread messages. Exit codes:
  0 - Has unread messages
  1 - No unread messages
  2 - Error
```

### download subcommand

```
usage: herd_mail.py download [-h] [--dest-dir DEST_DIR] uid

positional arguments:
  uid                   Message UID to download attachments from

options:
  --dest-dir DEST_DIR   Destination directory (default: current directory)
```

### flag subcommand

```
usage: herd_mail.py flag [-h] [--folder FOLDER] [--human] {add,remove} uids flags [flags ...]

positional arguments:
  {add,remove}     Flag operation
  uids             Message UID(s), comma-separated for bulk
  flags            Flags: \Seen \Answered \Flagged

options:
  --folder FOLDER  IMAP folder (default: INBOX)
  --human          Human-readable output
```

Only `\Seen`, `\Answered`, and `\Flagged` are allowed. `\Deleted` is blocked for safety.

### move subcommand

```
usage: herd_mail.py move [-h] [--folder FOLDER] [--human] uid dest_folder

positional arguments:
  uid              Message UID
  dest_folder      Destination IMAP folder

options:
  --folder FOLDER  Source folder (default: INBOX)
  --human          Human-readable output
```

## Testing

Run the comprehensive test suite:

```bash
# With pytest (recommended)
pip install pytest
python3 -m pytest test_herd_mail.py -v

# Without pytest (basic validation)
python3 test_herd_mail.py
```

Tests mock SMTP/IMAP so they run without real credentials.

**Test Coverage**: ~95% | **Tests**: 97 passing

## How It Works

### Sending Flow

1. **Load Configuration**: Read environment variables with validation
2. **Validate Inputs**: Check email addresses, ports, and file paths
3. **Duplicate Check**: Query send log to prevent accidental resends (optional)
4. **Build Message**: Convert Markdown to HTML + plain text
5. **Fetch Original**: If replying, get threading headers from IMAP
6. **Send**: SMTP delivery via waggle
7. **Sent Folder Sync**: herd-mail appends plain text copy to IMAP Sent folder (if `WAGGLE_IMAP_HOST` configured; tries `Sent`, `Sent Items`, `INBOX.Sent`; failure is non-fatal)
8. **Auto-Flag Original**: If replying (`--message-id`), marks original as `\Seen`+`\Answered` (non-fatal)
9. **Log**: Record send for duplicate detection

### Reading Flow

1. **Load Configuration**: Read environment variables with validation
2. **Connect to IMAP**: Establish secure connection
3. **Fetch Messages**: Query inbox for messages
4. **Parse Content**: Extract headers, body, attachments
5. **Output JSON**: Structured data to stdout (stderr for logging)
6. **Auto-Mark Read**: Sets `\Seen` flag (unless `--no-mark-read`)
7. **Download Attachments** (optional): Save to disk with path validation

### Output Design

- **stdout**: JSON output for AI agents to parse
- **stderr**: Human-readable logging and error messages
- This separation allows piping JSON directly to other tools while preserving debug visibility

## AI Agent Integration

herd-mail is designed for AI-to-AI email communication. All data commands output structured JSON to stdout, with logging on stderr. This section documents workflows, JSON schemas, and exit codes for programmatic use.

### Exit Codes

| Command | Code 0 | Code 1 | Code 2 |
|---------|--------|--------|--------|
| `send` | Sent successfully | Error (config, validation, SMTP) | — |
| `list` | Listed successfully | Error (config, IMAP) | — |
| `read` | Read successfully | Error (config, IMAP) | — |
| `check` | Has unread messages | No unread messages | Error |
| `download` | Downloaded | Error | — |
| `flag` | Flags updated | Error (config, IMAP, invalid flag) | — |
| `move` | Moved | Error | — |
| `config` | Config valid | Config invalid | — |

### JSON Output Schemas

#### `list` output
```json
{
  "folder": "INBOX",
  "count": 2,
  "messages": [
    {
      "uid": "635",
      "message_id": "<abc123@example.com>",
      "from_addr": "alice@example.com",
      "from_name": "Alice",
      "from_raw": "Alice <alice@example.com>",
      "subject": "Project update",
      "date": "Tue, 01 Apr 2026 10:30:00 +0000",
      "flags": "\\Seen",
      "size": 2048,
      "unread": false
    }
  ]
}
```

#### `read` output
```json
{
  "uid": "635",
  "folder": "INBOX",
  "message_id": "<abc123@example.com>",
  "from_addr": "alice@example.com",
  "from_name": "Alice",
  "to": "bob@example.com",
  "subject": "Project update",
  "date": "Tue, 01 Apr 2026 10:30:00 +0000",
  "body_plain": "Hi Bob, here's the update...",
  "body_html": "<html>...</html>",
  "in_reply_to": null,
  "references": null,
  "attachments": [
    {"filename": "report.pdf", "content_type": "application/pdf", "size": 45000}
  ]
}
```

Key fields for threading: `message_id`, `in_reply_to`, `references`. Use `uid` for all subsequent operations (read, flag, move, reply).

#### `check` output
```json
{
  "folder": "INBOX",
  "unread_count": 3,
  "messages": [
    {"uid": "640", "from_addr": "alice@example.com", "subject": "Need response", "unread": true}
  ]
}
```

#### `flag` output
```json
{
  "uids": ["635", "636"],
  "flags": ["\\Seen", "\\Answered"],
  "action": "add",
  "folder": "INBOX",
  "results": [
    {"uid": "635", "status": "ok"},
    {"uid": "636", "status": "ok"}
  ]
}
```

### Recommended Workflows

#### Polling Loop (check for new mail)
```bash
# Poll for unread messages — exit code 0 means unread exist
if python3 herd_mail.py check; then
    # Fetch the unread message list as JSON
    MESSAGES=$(python3 herd_mail.py list --unread)
    # Process each UID...
fi
```

#### Read and Process
```bash
# Read message — automatically marks as \Seen
MESSAGE=$(python3 herd_mail.py read 635)

# Parse with jq
BODY=$(echo "$MESSAGE" | jq -r '.body_plain')
FROM=$(echo "$MESSAGE" | jq -r '.from_addr')
SUBJECT=$(echo "$MESSAGE" | jq -r '.subject')

# If you need to read without marking as read (e.g., peeking)
MESSAGE=$(python3 herd_mail.py read 635 --no-mark-read)
```

#### Reply to a Message
```bash
# Reply — auto-sets threading headers AND marks original as \Seen + \Answered
python3 herd_mail.py send \
  --message-id 635 \
  --to alice@example.com \
  --subject "Re: Project update" \
  --body "Thanks for the update, Alice!"
```

The `--message-id` flag:
1. Fetches the original message to extract `In-Reply-To` and `References` headers
2. Sends the reply with proper threading
3. Saves a copy to the Sent folder (if IMAP configured)
4. Marks the original message as `\Seen` + `\Answered`

#### Triage Workflow (read, decide, act)
```bash
# Read the message
MESSAGE=$(python3 herd_mail.py read 640)

# Agent decides: needs reply, archive, or flag for later
# Option A: Reply (auto-flags \Seen + \Answered)
python3 herd_mail.py send --message-id 640 --to ... --subject "Re: ..." --body "..."

# Option B: Archive without replying
python3 herd_mail.py flag add 640 '\Seen'
python3 herd_mail.py move 640 INBOX.Archive

# Option C: Flag for follow-up
python3 herd_mail.py flag add 640 '\Seen' '\Flagged'
```

#### Bulk Processing
```bash
# Mark multiple messages as read in one call
python3 herd_mail.py flag add 630,631,632,633 '\Seen'

# Process attachments
python3 herd_mail.py download 635 --dest-dir ./attachments
FILES=$(python3 herd_mail.py download 635 --dest-dir ./attachments | jq -r '.files[]')
```

#### Complete Agent Loop
```bash
#!/bin/bash
# Full agent email processing loop

# 1. Check for new mail
if ! python3 herd_mail.py check 2>/dev/null; then
    exit 0  # No unread messages
fi

# 2. Get unread messages
UNREAD=$(python3 herd_mail.py list --unread 2>/dev/null)
UIDS=$(echo "$UNREAD" | jq -r '.messages[].uid')

# 3. Process each message
for UID in $UIDS; do
    # Read (auto-marks \Seen)
    MSG=$(python3 herd_mail.py read "$UID" 2>/dev/null)

    FROM=$(echo "$MSG" | jq -r '.from_addr')
    SUBJECT=$(echo "$MSG" | jq -r '.subject')
    BODY=$(echo "$MSG" | jq -r '.body_plain')

    # Agent logic: compose a response
    REPLY_BODY="Your agent-generated response here"

    # Reply (auto-marks \Seen + \Answered on original)
    python3 herd_mail.py send \
        --message-id "$UID" \
        --to "$FROM" \
        --subject "Re: $SUBJECT" \
        --body "$REPLY_BODY" 2>/dev/null

    # Move to processed folder
    python3 herd_mail.py move "$UID" INBOX.Processed 2>/dev/null
done
```

### Flag Semantics

| Flag | Meaning | When to Set |
|------|---------|------------|
| `\Seen` | Message has been read | Auto-set by `read`; set manually after processing |
| `\Answered` | Message has been replied to | Auto-set by `send --message-id`; set manually after replying via other means |
| `\Flagged` | Message is flagged/starred | Set manually for follow-up, priority, or needs-attention |

### Automatic vs Manual Flagging

| Action | What happens automatically | What you do manually |
|--------|--------------------------|---------------------|
| `read <uid>` | Sets `\Seen` | Nothing (or `--no-mark-read` to skip) |
| `send --message-id <uid>` | Sets `\Seen` + `\Answered` on original | Nothing |
| `send --to ...` (new email) | Nothing on inbox | Flag/move as needed |
| Processing CC'd mail | Nothing beyond `\Seen` from read | `flag add <uid> '\Seen'` then `move` to archive |
| Flagging for follow-up | Nothing | `flag add <uid> '\Flagged'` |

### Error Handling for Agents

- **stdout** is always valid JSON on success (exit code 0). Parse it directly.
- **stderr** contains log messages. Redirect to a log file: `2>>/var/log/herd-mail.log`
- **Auto-flag failures are non-fatal**: If `read` succeeds but marking `\Seen` fails, you still get exit code 0 and the message JSON. A warning appears on stderr.
- **Duplicate detection**: `send` with a recently-sent identical (to, subject) returns exit code 0 (not an error, just skipped). Check stderr for "Duplicate detected" if you need to distinguish.

## Security Features

### Version 2.0 Built-in Protections

- **Email Header Injection Prevention**: Validates all email addresses, blocks control characters
- **Path Traversal Protection**: Validates file paths, blocks access to sensitive directories (`/etc`, `/sys`, `/proc`, `/dev`)
- **Input Validation**: Validates port numbers (1-65535), email format, file existence
- **Output Sanitization**: Removes ANSI escape sequences to prevent terminal injection
- **No Hardcoded Paths**: Development paths require explicit `WAGGLE_DEV_PATH` environment variable
- **Credential Protection**: Redacts sensitive information in logs and dry-run output

### Inherited from waggle

- **Attachment Security**: Path traversal protection, symlink attack prevention
- **Size Limits**: 50MB per file, 200MB per message
- **IMAP Injection Guards**: Control character validation
- **Atomic Operations**: Safe file writes with tempfile pattern

See [waggle security docs](https://github.com/jasonacox-sam/waggle-mail#security) for more details.

## Troubleshooting

### "Error: waggle not installed"

```bash
pip install waggle-mail
```

### "Configuration errors: Missing smtp_host"

Your `.envrc` file is missing required variables. Check `.envrc.template` for the full list.

### "Invalid recipient email address"

Email addresses are now validated for security. Check that your email addresses:
- Contain `@` and a domain with TLD (e.g., `.com`)
- Don't contain control characters (`\n`, `\r`, `\t`)
- Follow standard email format

### "Invalid SMTP port"

Port numbers must be between 1 and 65535. Common values:
- `465` - SMTP with SSL/TLS (recommended)
- `587` - SMTP with STARTTLS
- `993` - IMAP with SSL/TLS

### Emails not appearing in Sent folder

The Sent folder sync feature saves a plain text copy (no attachments) to your IMAP Sent folder when configured:

- Set `WAGGLE_IMAP_HOST` in your `.envrc`
- Ensure IMAP credentials match your SMTP credentials (same user/pass)
- Folder names tried in order: `Sent`, `Sent Items`, `INBOX.Sent`
- Sync failures are non-fatal - email is still sent, but copy won't appear in Sent folder
- Check logs for warnings if sync is silently failing

### Duplicate detection not working

Set `WAGGLE_SEND_LOG` to a writable path:

```bash
export WAGGLE_SEND_LOG=$HOME/.local/share/waggle-sent.log
mkdir -p $(dirname $WAGGLE_SEND_LOG)
```

### "Access to sensitive path denied"

For security, certain system directories are blocked:
- `/etc`, `/private/etc` (system configuration)
- `/sys`, `/proc` (system information)
- `/dev` (device files)
- `/var/log` (system logs)

Move your files to a user directory (e.g., `~/documents/`).

## Development

### Using Local waggle

For testing unreleased waggle changes:

```bash
export WAGGLE_DEV_PATH=/path/to/local/waggle
python3 herd_mail.py config
```

This is intentionally opt-in for security.

### Code Quality

- **Type Hints**: Full type annotations for Python 3.8+
- **Logging**: Professional logging infrastructure (not print statements)
- **Error Handling**: Specific exception types with helpful messages
- **Testing**: 95% test coverage with 105 test cases
- **Architecture**: Subcommand dispatch pattern with cmd_* handlers

## CI/CD

GitHub Actions run automatically:

- **Tests** (`test.yml`): Runs the full test suite on every push to `main` and on pull requests. Tests across Python 3.10, 3.12, and 3.14.
- **Release** (`release.yml`): Triggered by pushing a `v*` tag. Runs the test suite first, then creates a GitHub release with auto-generated notes from the commit log.

### Creating a Release

```bash
# 1. Update __version__ in herd_mail.py and version in pyproject.toml
# 2. Commit the version bump
git add herd_mail.py pyproject.toml
git commit -m "Bump version to 3.2.0"

# 3. Tag and push
git tag -a v3.2.0 -m "v3.2.0: short description"
git push origin main v3.2.0
```

The release workflow will run tests and create the GitHub release automatically. If tests fail, the release is not created.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality (maintain 95% coverage)
4. Ensure all tests pass: `python3 -m pytest test_herd_mail.py -v`
5. Submit a pull request

CI will run the test suite automatically on your PR.

## License

MIT — same as waggle

## See Also

- [waggle](https://github.com/jasonacox-sam/waggle-mail) — The underlying email library
- [direnv](https://direnv.net/) — Environment variable management

---

**Status**: ✅ Production Ready | **Version**: 3.1.0 | **Security**: Hardened | **Tests**: 105/105 Passing
