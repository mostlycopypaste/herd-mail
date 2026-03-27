#!/usr/bin/env python3
"""
herd-mail: AI-to-AI communication facilitator for the herd.

A secure, user-friendly wrapper for waggle that handles the full lifecycle
of herd email communication: configuration, threading, duplication prevention,
and sent-folder synchronization.

Features:
- Markdown to HTML conversion with optional rich formatting
- Thread-aware replies (fetches original for quoting)
- Attachment support with security validation
- Duplicate prevention (checks send log)
- Automatic Sent folder saving via IMAP
- Environment-based configuration (no hardcoded credentials)

Usage:
    # Send simple email
    python3 herd_mail.py --to recipient@example.com --subject "Hello" --body "Message"

    # Send with body from file
    python3 herd_mail.py --to recipient@example.com --subject "Hello" --body-file message.md

    # Reply to a message (auto-fetches original for threading)
    python3 herd_mail.py --message-id 42 --to sender@example.com --subject "Re: Hello"

    # With attachment
    python3 herd_mail.py --to recipient@example.com --body "See attached" --attachment file.pdf

    # Rich HTML formatting (requires markdown + pygments)
    python3 herd_mail.py --to recipient@example.com --body-file message.md --rich

Environment Variables (all optional, see .envrc.template):
    WAGGLE_HOST         SMTP host
    WAGGLE_PORT         SMTP port (default: 465)
    WAGGLE_USER         SMTP username
    WAGGLE_PASS         SMTP password
    WAGGLE_FROM         From email address
    WAGGLE_NAME         Display name
    WAGGLE_TLS          Use TLS (default: true)
    WAGGLE_IMAP_HOST    IMAP host (for Sent folder)
    WAGGLE_IMAP_PORT    IMAP port (default: 993)
    WAGGLE_TO           Default test recipient
    WAGGLE_SEND_LOG     Path to send log (for duplicate detection)
    WAGGLE_DEV_PATH     Optional: Path to local waggle for development

Author: O.C.
License: MIT
"""

import argparse
import logging
import os
import re
import sys
from email.utils import parseaddr
from pathlib import Path
from typing import Any, Optional

# Constants
DEFAULT_SMTP_PORT = 465
DEFAULT_IMAP_PORT = 993
DEFAULT_DUPLICATE_CHECK_MINUTES = 5
DEFAULT_IMAP_FOLDER = "INBOX"
DEFAULT_NO_BODY_MESSAGE = "(No message body)"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Add local waggle development path ONLY if explicitly enabled via env var
# This prevents arbitrary code execution from hardcoded paths
WAGGLE_DEV_PATH = os.environ.get("WAGGLE_DEV_PATH")
if WAGGLE_DEV_PATH:
    dev_path = Path(WAGGLE_DEV_PATH)
    if dev_path.exists() and dev_path.is_dir():
        sys.path.insert(0, str(dev_path))
        logger.info(f"Using development waggle from: {dev_path}")
    else:
        logger.warning(f"WAGGLE_DEV_PATH set but path doesn't exist: {dev_path}")

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
    # Don't exit here - allow module to be imported for testing
    # We'll check in main() before actually trying to use waggle

    # Create stub functions so tests can mock them
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


def validate_email_address(email: str) -> bool:
    """
    Validate email address format.

    Args:
        email: Email address to validate

    Returns:
        True if valid, False otherwise
    """
    if not email or not isinstance(email, str):
        return False

    # Check for suspicious characters that could indicate header injection
    # (check BEFORE parseaddr, which might strip them)
    suspicious_chars = ['\n', '\r', '\0', '\t']
    if any(char in email for char in suspicious_chars):
        return False

    # Use email.utils.parseaddr for basic validation
    name, addr = parseaddr(email)

    # Check for basic email structure: has @ and domain
    if not addr or '@' not in addr:
        return False

    local, domain = addr.rsplit('@', 1)

    # Basic sanity checks
    if not local or not domain:
        return False

    if '.' not in domain:
        return False

    return True


def validate_email_list(emails: str) -> bool:
    """
    Validate comma-separated list of email addresses.

    Args:
        emails: Comma-separated email addresses

    Returns:
        True if all valid, False otherwise
    """
    if not emails:
        return True  # Empty is ok

    for email in emails.split(','):
        if not validate_email_address(email.strip()):
            return False

    return True


def sanitize_for_display(text: str, max_length: int = 200) -> str:
    """
    Sanitize text for terminal display to prevent escape sequence injection.

    Args:
        text: Text to sanitize
        max_length: Maximum length to display

    Returns:
        Sanitized text
    """
    if not text:
        return ""

    # Remove ANSI escape sequences (ESC followed by [ and control codes)
    # Pattern matches: ESC [ ... (any chars between @ and ~)
    ansi_escape = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
    sanitized = ansi_escape.sub('', text)

    # Remove other control characters except newline and tab
    sanitized = ''.join(
        char for char in sanitized
        if char.isprintable() or char in ('\n', '\t')
    )

    # Truncate if too long
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."

    return sanitized


def validate_file_path(file_path: str, must_exist: bool = True) -> Optional[Path]:
    """
    Validate and resolve file path with security checks.

    Args:
        file_path: Path to validate
        must_exist: Whether file must exist

    Returns:
        Resolved Path object if valid, None otherwise
    """
    try:
        path = Path(file_path).resolve()

        # Check if path exists (if required)
        if must_exist and not path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        # Check if it's a file (not directory)
        if must_exist and not path.is_file():
            logger.error(f"Path is not a file: {file_path}")
            return None

        # Prevent reading from sensitive system directories
        # Include both standard Linux paths and macOS equivalents
        sensitive_dirs = [
            '/etc', '/private/etc',  # System config (macOS: /etc -> /private/etc)
            '/sys',                   # System info (Linux)
            '/proc',                  # Process info (Linux)
            '/dev',                   # Device files
            '/var/log',               # System logs
        ]
        for sensitive in sensitive_dirs:
            if str(path).startswith(sensitive):
                logger.error(f"Access to sensitive path denied: {file_path}")
                return None

        return path

    except (ValueError, OSError) as e:
        logger.error(f"Invalid file path: {file_path} ({e})")
        return None


def decode_escape_sequences(text: str) -> str:
    """
    Decode common escape sequences from command line input.

    Args:
        text: Text with potential escape sequences

    Returns:
        Text with escape sequences decoded
    """
    # Handle common escape sequences
    replacements = {
        '\\n': '\n',
        '\\r': '\r',
        '\\t': '\t',
        '\\\\': '\\',
        '\\"': '"',
        "\\'": "'",
    }

    result = text
    for escaped, actual in replacements.items():
        result = result.replace(escaped, actual)

    return result


def parse_port(port_str: str, default: int, port_name: str = "port") -> int:
    """
    Parse port number from string with validation.

    Args:
        port_str: Port as string
        default: Default port if parsing fails
        port_name: Name for error messages

    Returns:
        Valid port number

    Raises:
        ValueError: If port is invalid
    """
    try:
        port = int(port_str)
        if not (1 <= port <= 65535):
            raise ValueError(f"{port_name} must be between 1 and 65535")
        return port
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid {port_name}: {port_str} ({e})")


def get_config() -> dict[str, Any]:
    """
    Build configuration from environment variables.

    Returns:
        Configuration dictionary

    Raises:
        ValueError: If port configuration is invalid
    """
    # Parse ports with validation
    try:
        smtp_port = parse_port(
            os.environ.get("WAGGLE_PORT", str(DEFAULT_SMTP_PORT)),
            DEFAULT_SMTP_PORT,
            "SMTP port"
        )
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise

    try:
        imap_port = parse_port(
            os.environ.get("WAGGLE_IMAP_PORT", str(DEFAULT_IMAP_PORT)),
            DEFAULT_IMAP_PORT,
            "IMAP port"
        )
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise

    return {
        "smtp_host": os.environ.get("WAGGLE_HOST"),
        "smtp_port": smtp_port,
        "smtp_user": os.environ.get("WAGGLE_USER"),
        "smtp_pass": os.environ.get("WAGGLE_PASS"),
        "from_addr": os.environ.get("WAGGLE_FROM"),
        "from_name": os.environ.get("WAGGLE_NAME", ""),
        "use_tls": os.environ.get("WAGGLE_TLS", "true").lower() == "true",
        "imap_host": os.environ.get("WAGGLE_IMAP_HOST"),
        "imap_port": imap_port,
        "imap_tls": os.environ.get("WAGGLE_IMAP_TLS", "true").lower() == "true",
        "send_log": os.environ.get("WAGGLE_SEND_LOG"),
    }


def validate_config(cfg: dict[str, Any], require_smtp: bool = True) -> bool:
    """
    Validate configuration has required values.

    Args:
        cfg: Configuration dictionary
        require_smtp: Whether to require SMTP settings

    Returns:
        True if valid, False otherwise
    """
    errors = []

    if require_smtp:
        required = ["smtp_host", "smtp_user", "smtp_pass", "from_addr"]
        for key in required:
            if not cfg.get(key):
                errors.append(f"Missing {key} (set WAGGLE_{key.upper()})")

        # Validate from_addr is a valid email
        from_addr = cfg.get("from_addr")
        if from_addr and not validate_email_address(from_addr):
            errors.append(f"Invalid from_addr email format: {from_addr}")

    if errors:
        logger.error("Configuration errors:")
        for error in errors:
            logger.error(f"  - {error}")
        logger.error("\nSee .envrc.template for required variables.")
        return False

    return True


def build_waggle_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """
    Convert our config to waggle's expected format.

    Args:
        cfg: Our configuration dictionary

    Returns:
        Configuration in waggle's format
    """
    return {
        "host": cfg["smtp_host"],
        "port": cfg["smtp_port"],
        "user": cfg["smtp_user"],
        "password": cfg["smtp_pass"],
        "from_addr": cfg["from_addr"],
        "from_name": cfg["from_name"],
        "tls": cfg["use_tls"],
        "imap_host": cfg.get("imap_host"),
        "imap_port": cfg.get("imap_port", DEFAULT_IMAP_PORT),
        "imap_tls": cfg.get("imap_tls", True),
    }


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    # Check if waggle is available (unless we're just validating imports for tests)
    if not WAGGLE_AVAILABLE:
        logger.error("Error: waggle not installed. Run: pip install waggle-mail")
        if WAGGLE_IMPORT_ERROR:
            logger.error(f"Details: {WAGGLE_IMPORT_ERROR}")
        return 1

    parser = argparse.ArgumentParser(
        description="Send herd emails with Markdown, attachments, and threading via waggle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --to friend@example.com --subject "Hello" --body "Hi there!"
  %(prog)s --to friend@example.com --subject "Hello" --body-file message.md
  %(prog)s --message-id 42 --to sender@example.com --subject "Re: Hello"
  %(prog)s --to friend@example.com --body "See attached" --attachment doc.pdf
        """
    )

    parser.add_argument("--to", required=True,
                        help="Recipient email address")
    parser.add_argument("--subject", required=True,
                        help="Email subject line")
    parser.add_argument("--body",
                        help="Email body (Markdown supported)")
    parser.add_argument("--body-file",
                        help="Read body from file (UTF-8)")
    parser.add_argument("--attachment", nargs="+",
                        help="File(s) to attach")
    parser.add_argument("--cc",
                        help="CC recipients (comma-separated)")
    parser.add_argument("--reply-to",
                        help="Reply-To address")
    parser.add_argument("--message-id",
                        help="IMAP message ID to reply to (enables threading)")
    parser.add_argument("--rich", action="store_true",
                        help="Enable rich HTML formatting (requires markdown, pygments)")
    parser.add_argument("--skip-duplicate-check", action="store_true",
                        help="Skip checking for recent duplicates")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate config without sending")

    args = parser.parse_args()

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

    # Load configuration
    try:
        cfg = get_config()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1

    if args.dry_run:
        if validate_config(cfg):
            logger.info("Configuration valid!")
            # Don't expose full username in output for security
            smtp_user_display = cfg['smtp_user'][:3] + "***" if cfg['smtp_user'] else "***"
            logger.info(f"  SMTP: {smtp_user_display}@{cfg['smtp_host']}:{cfg['smtp_port']}")
            logger.info(f"  From: {cfg['from_name']} <{cfg['from_addr']}>")
            if cfg.get("imap_host"):
                logger.info(f"  IMAP: {cfg['imap_host']}:{cfg['imap_port']} (Sent folder enabled)")
            return 0
        return 1

    # Validate configuration
    if not validate_config(cfg):
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
        # Decode common escape sequences from command line
        body = decode_escape_sequences(args.body)
    else:
        # Try reading from stdin
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
                    f"⚠️  Duplicate detected: recently sent to "
                    f"{sanitize_for_display(args.to)} with similar subject"
                )
                logger.info("Use --skip-duplicate-check to override")
                return 0  # Not an error, just skipped
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

        logger.info("✓ Email sent successfully!")
        if cfg.get("imap_host"):
            logger.info("  (Saved to Sent folder via IMAP)")

        return 0

    except ConnectionError as e:
        logger.error(f"✗ Connection error: {e}")
        return 1
    except TimeoutError as e:
        logger.error(f"✗ Timeout error: {e}")
        return 1
    except ValueError as e:
        logger.error(f"✗ Invalid input: {e}")
        return 1
    except OSError as e:
        logger.error(f"✗ I/O error: {e}")
        return 1
    except Exception as e:
        logger.error(f"✗ Unexpected error: {e}")
        logger.debug("", exc_info=True)  # Full traceback in debug mode
        return 1


if __name__ == "__main__":
    sys.exit(main())
