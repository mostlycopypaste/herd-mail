# send-email-waggle

A secure, user-friendly CLI wrapper for [waggle](https://github.com/jasonacox-sam/waggle) — the AI-to-AI email library that powers herd communications.

## Features

- **Markdown → HTML**: Write emails in Markdown, get beautiful HTML + plain text
- **Thread-aware Replies**: Auto-fetch original messages for proper threading
- **Attachments**: Send files with security validation
- **Duplicate Prevention**: Checks send log to prevent accidental resends
- **Sent Folder Sync**: Automatically saves to IMAP Sent folder
- **Environment-based**: No hardcoded credentials in scripts

## Quick Start

```bash
# Clone and enter directory
git clone <this-repo>
cd send-email-waggle

# Install dependencies
pip install waggle-mail

# Optional: rich formatting
pip install markdown pygments

# Set up environment
cp .envrc.template .envrc
# Edit .envrc with your credentials
source .envrc

# Send a test email
python3 send_email.py --to friend@example.com --subject "Hello" --body "Hi from waggle!"
```

## Installation

### Prerequisites

- Python 3.8+
- pip

### Install waggle

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

### Security Note

`.envrc` is in `.gitignore` — never commit real credentials! The template shows the structure without exposing secrets.

## Usage

### Send a Simple Email

```bash
python3 send_email.py \
  --to friend@example.com \
  --subject "Hello from waggle" \
  --body "This is a test email!"
```

### Send with Markdown Body from File

```bash
python3 send_email.py \
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
python3 send_email.py \
  --message-id 42 \
  --to sender@example.com \
  --subject "Re: Original Subject" \
  --body "Thanks for your email!"
```

This automatically:
- Fetches the original message from IMAP
- Sets `In-Reply-To` and `References` headers
- Appends quoted original text

### Send with Attachment

```bash
python3 send_email.py \
  --to friend@example.com \
  --subject "Document" \
  --body "See attached" \
  --attachment report.pdf
```

Multiple attachments:

```bash
python3 send_email.py \
  --to friend@example.com \
  --subject "Files" \
  --attachment file1.pdf file2.txt file3.png
```

### Rich HTML Formatting

```bash
python3 send_email.py \
  --to friend@example.com \
  --subject "Code Review" \
  --body-file code-review.md \
  --rich
```

Adds syntax highlighting for code blocks.

### Pipe Body from Stdin

```bash
cat message.txt | python3 send_email.py \
  --to friend@example.com \
  --subject "Hello"
```

### Validate Configuration (Dry Run)

```bash
python3 send_email.py --dry-run
```

Checks that all required environment variables are set without sending.

## Command Line Reference

```
usage: send_email.py [-h] --to TO --subject SUBJECT [-- BODY] [--body-file BODY_FILE]
                     [--attachment ATTACHMENT [ATTACHMENT ...]] [--cc CC]
                     [--reply-to REPLY_TO] [--message-id MESSAGE_ID] [--rich]
                     [--skip-duplicate-check] [--dry-run]

Send emails with Markdown, attachments, and threading via waggle

optional arguments:
  -h, --help            show this help message and exit
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
  --rich                Enable rich HTML formatting (requires markdown,
                        pygments)
  --skip-duplicate-check
                        Skip checking for recent duplicates
  --dry-run             Validate config without sending
```

## Testing

Run the test suite:

```bash
# With pytest (recommended)
pip install pytest
python3 -m pytest test_send_email.py -v

# Without pytest (basic validation)
python3 test_send_email.py
```

Tests mock SMTP/IMAP so they run without real credentials.

## How It Works

1. **Load Configuration**: Read environment variables
2. **Validate**: Check required fields are present
3. **Duplicate Check**: Query send log (optional)
4. **Build Message**: Convert Markdown to HTML + plain text
5. **Fetch Original**: If replying, get threading headers
6. **Send**: SMTP delivery
7. **Save Copy**: IMAP append to Sent folder (optional)
8. **Log**: Record send for duplicate detection

## Troubleshooting

### "Error: waggle not installed"

```bash
pip install waggle-mail
```

### "Configuration errors: Missing smtp_host"

Your `.envrc` file is missing required variables. Check `.envrc.template` for the full list.

### Emails not appearing in Sent folder

- Set `WAGGLE_IMAP_HOST` in your `.envrc`
- Common folder names tried: `"Sent Items"`, `"Sent"`, `"INBOX.Sent"`

### Duplicate detection not working

Set `WAGGLE_SEND_LOG` to a writable path:

```bash
export WAGGLE_SEND_LOG=$HOME/.local/share/waggle-sent.log
mkdir -p $(dirname $WAGGLE_SEND_LOG)
```

## Security Features

This wrapper leverages waggle's security hardening:

- **Path Traversal Protection**: `..` sequences sanitized in attachment filenames
- **Symlink Attack Prevention**: Validates path chain before writes
- **Atomic File Writes**: `tempfile.mkstemp()` + rename pattern
- **Size Limits**: 50MB per file, 200MB per message
- **IMAP Injection Guards**: Control character validation

See [waggle security docs](https://github.com/jasonacox-sam/waggle-mail#security) for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

MIT — same as waggle

## See Also

- [waggle](https://github.com/jasonacox-sam/waggle-mail) — The underlying email library
- [Himalaya](https://github.com/pimalaya/himalaya) — IMAP/SMTP CLI (alternative)
- [direnv](https://direnv.net/) — Environment variable management
