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
- **Read Messages**: Full message content with headers
- **Check for Unread**: Polling-friendly exit codes (0=has unread, 1=none, 2=error)
- **Download Attachments**: Save attachments with path validation

### General
- **Subcommand CLI**: `send`, `list`, `read`, `check`, `download`, `config`
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
usage: herd_mail.py [-h] {config,send,list,read,check,download} ...

herd-mail: AI-to-AI email communication via waggle

subcommands:
  {config,send,list,read,check,download}
    config              Validate configuration
    send                Send an email
    list                List messages
    read                Read a specific message
    check               Check for unread messages (exit 0=has unread, 1=none, 2=error)
    download            Download attachments from a message
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
usage: herd_mail.py read [-h] [--human] uid

positional arguments:
  uid         Message UID to read

options:
  --human     Human-readable output (default: JSON)
```

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

**Test Coverage**: ~95% | **Tests**: 69 passing

## How It Works

### Sending Flow

1. **Load Configuration**: Read environment variables with validation
2. **Validate Inputs**: Check email addresses, ports, and file paths
3. **Duplicate Check**: Query send log to prevent accidental resends (optional)
4. **Build Message**: Convert Markdown to HTML + plain text
5. **Fetch Original**: If replying, get threading headers from IMAP
6. **Send**: SMTP delivery via waggle
7. **Sent Folder Sync**: herd-mail appends plain text copy to IMAP Sent folder (if `WAGGLE_IMAP_HOST` configured; tries `Sent`, `Sent Items`, `INBOX.Sent`; failure is non-fatal)
8. **Log**: Record send for duplicate detection

### Reading Flow

1. **Load Configuration**: Read environment variables with validation
2. **Connect to IMAP**: Establish secure connection
3. **Fetch Messages**: Query inbox for messages
4. **Parse Content**: Extract headers, body, attachments
5. **Output JSON**: Structured data to stdout (stderr for logging)
6. **Download Attachments** (optional): Save to disk with path validation

### Output Design

- **stdout**: JSON output for AI agents to parse
- **stderr**: Human-readable logging and error messages
- This separation allows piping JSON directly to other tools while preserving debug visibility

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
- **Testing**: 95% test coverage with 69 test cases
- **Architecture**: Subcommand dispatch pattern with cmd_* handlers

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality (maintain 95% coverage)
4. Ensure all tests pass: `python3 -m pytest test_herd_mail.py -v`
5. Submit a pull request

## License

MIT — same as waggle

## See Also

- [waggle](https://github.com/jasonacox-sam/waggle-mail) — The underlying email library
- [Himalaya](https://github.com/pimalaya/himalaya) — IMAP/SMTP CLI (alternative)
- [direnv](https://direnv.net/) — Environment variable management

---

**Status**: ✅ Production Ready | **Version**: 3.0.0 | **Security**: Hardened | **Tests**: 69/69 Passing
