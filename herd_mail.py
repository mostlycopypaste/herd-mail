#!/usr/bin/env python3
"""
herd-mail: AI-to-AI communication facilitator for the herd.

A secure, user-friendly wrapper for waggle that handles the full lifecycle
of herd email communication: sending, reading, checking, and downloading.

Commands:
    herd_mail.py send --to recipient@example.com --subject "Hello" --body "Message"
    herd_mail.py list [--folder INBOX] [--limit 20] [--unread] [--human]
    herd_mail.py read <uid> [--folder INBOX] [--human]
    herd_mail.py check [--folder INBOX] [--human]
    herd_mail.py download <uid> [--folder INBOX] [--dest-dir .]
    herd_mail.py config

Environment Variables (see .envrc.template):
    WAGGLE_HOST         SMTP host
    WAGGLE_PORT         SMTP port (default: 465)
    WAGGLE_USER         SMTP/IMAP username
    WAGGLE_PASS         SMTP/IMAP password
    WAGGLE_FROM         From email address
    WAGGLE_NAME         Display name
    WAGGLE_TLS          Use TLS (default: true)
    WAGGLE_IMAP_HOST    IMAP host (required for list/read/check/download)
    WAGGLE_IMAP_PORT    IMAP port (default: 993)
    WAGGLE_IMAP_TLS     Use IMAP TLS (default: true)
    WAGGLE_TO           Default test recipient
    WAGGLE_SEND_LOG     Path to send log (for duplicate detection)
    WAGGLE_DEV_PATH     Optional: Path to local waggle for development

Author: O.C.
License: MIT
"""

__version__ = "3.3.0"

import argparse
import datetime
import imaplib
import json
import logging
import os
import re
import ssl
import sys
from email.utils import parseaddr
from pathlib import Path
from typing import Any, Optional

import requests  # noqa: E402

# Constants
DEFAULT_SMTP_PORT = 465
DEFAULT_IMAP_PORT = 993
DEFAULT_DUPLICATE_CHECK_MINUTES = 5
DEFAULT_IMAP_FOLDER = "INBOX"
DEFAULT_NO_BODY_MESSAGE = "(No message body)"
DEFAULT_LIST_LIMIT = 20

ALLOWED_IMAP_FLAGS = {r"\Seen", r"\Answered", r"\Flagged"}

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

# Herd-inbox footer API
HERD_INBOX_URL = os.environ.get("HERD_INBOX_URL", "https://herd.mostlycopyandpaste.com")
HERD_ADMIN_KEY = os.environ.get("HERD_INBOX_ADMIN_KEY", "")


def fetch_footer(category: Optional[str] = None, context: Optional[str] = None, exclude_ids: Optional[list[int]] = None) -> Optional[str]:
    """Fetch a rotating footer message from the herd-inbox API.

    Args:
        category: Filter by category (token_economics, social_proof, fomo, cheeky)
        context: Filter by context (announcement, discussion)
        exclude_ids: Footer IDs to exclude from selection

    Returns:
        Footer text string, or None if the API call fails.
    """
    if not HERD_ADMIN_KEY:
        logger.debug("No HERD_INBOX_ADMIN_KEY set, skipping footer")
        return None

    params: dict[str, Any] = {}
    if category:
        params["category"] = category
    if context:
        params["context"] = context
    if exclude_ids:
        params["exclude"] = ",".join(str(i) for i in exclude_ids)

    try:
        resp = requests.get(
            f"{HERD_INBOX_URL}/api/admin/footer",
            headers={"X-Admin-Key": HERD_ADMIN_KEY},
            params=params,
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("footer")
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch footer from herd-inbox: {e}")
        return None


# Try to import waggle, but don't exit at module level (allows tests to run)
WAGGLE_AVAILABLE = False
WAGGLE_IMPORT_ERROR = None

try:
    from waggle import (
        send_email, check_recently_sent, read_message,
        list_inbox, download_attachments, move_message,
        set_flags, clear_flags,
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

    def move_message(*args, **kwargs):
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


def normalize_imap_flag(flag: str) -> Optional[str]:
    """Normalize an IMAP flag string to canonical form, or return None if invalid."""
    canonical = {f.lower(): f for f in ALLOWED_IMAP_FLAGS}
    normalized = flag if flag.startswith("\\") else f"\\{flag}"
    return canonical.get(normalized.lower())


def validate_imap_flags(flags: list[str]) -> tuple[list[str], list[str]]:
    """
    Validate and normalize IMAP flags against the whitelist.

    Returns:
        Tuple of (normalized_flags, errors). Empty errors means all valid.
    """
    normalized = []
    errors = []
    for flag in flags:
        result = normalize_imap_flag(flag)
        if result:
            normalized.append(result)
        else:
            errors.append(f"Invalid flag: {flag} (allowed: {', '.join(sorted(ALLOWED_IMAP_FLAGS))})")
    return normalized, errors


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


def validate_config(cfg: dict[str, Any], require_smtp: bool = True, require_imap: bool = False) -> bool:
    """
    Validate configuration has required values.

    Args:
        cfg: Configuration dictionary
        require_smtp: Whether to require SMTP settings
        require_imap: Whether to require IMAP settings

    Returns:
        True if valid, False otherwise
    """
    errors = []

    if require_smtp:
        required = ["smtp_host", "smtp_user", "smtp_pass", "from_addr"]
        for key in required:
            if not cfg.get(key):
                errors.append(f"Missing {key} (set WAGGLE_{key.upper()})")

        from_addr = cfg.get("from_addr")
        if from_addr and not validate_email_address(from_addr):
            errors.append(f"Invalid from_addr email format: {from_addr}")

    if require_imap:
        if not cfg.get("imap_host"):
            errors.append("Missing imap_host (set WAGGLE_IMAP_HOST)")

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


def format_quote_block(original: dict[str, Any]) -> str:
    """Format an already-fetched message as an Outlook-style quoted block.

    This avoids relying on waggle's fetch_quoted_body(), which re-fetches
    the message via IMAP SEARCH by Message-ID — a search that fails on
    some providers (e.g., Amazon WorkMail).
    """
    from_raw = original.get("from_raw", "")
    date = original.get("date", "")
    subject = original.get("subject", "")
    body_plain = original.get("body_plain") or ""

    header = (
        f"\n\n-----Original Message-----\n"
        f"From: {from_raw}\n"
        f"Sent: {date}\n"
        f"Subject: {subject}\n"
    )
    if body_plain.strip():
        return header + "\n" + body_plain.strip()
    return header


def resolve_sequence_to_uids(
    cfg: dict[str, Any],
    messages: list[dict[str, Any]],
    folder: str = DEFAULT_IMAP_FOLDER,
) -> list[dict[str, Any]]:
    """
    Replace waggle's sequence-number "uid" fields with actual IMAP UIDs.

    waggle's list_inbox() returns sequence numbers labeled as "uid".
    This function connects via IMAP, fetches all UIDs, builds a
    sequence-number-to-UID mapping, and patches each message dict in place.

    Returns:
        The same messages list with "uid" fields replaced by real UIDs.
        Messages whose sequence numbers can't be mapped are left unchanged.
    """
    if not messages:
        return messages

    wcfg = build_waggle_config(cfg)
    ctx = ssl.create_default_context()

    try:
        if wcfg.get("imap_tls", True):
            conn = imaplib.IMAP4_SSL(
                wcfg["imap_host"], wcfg.get("imap_port", DEFAULT_IMAP_PORT),
                ssl_context=ctx,
            )
        else:
            conn = imaplib.IMAP4(wcfg["imap_host"], wcfg.get("imap_port", DEFAULT_IMAP_PORT))

        try:
            conn.login(wcfg["user"], wcfg["password"])
            status, _ = conn.select(folder, readonly=True)
            if status != "OK":
                logger.warning(f"Could not select folder {folder!r} for UID resolution")
                return messages

            for msg in messages:
                seq = str(msg.get("uid", ""))
                if not seq:
                    continue
                status, data = conn.fetch(seq, "(UID)")
                if status == "OK" and data and data[0]:
                    match = re.search(rb"UID\s+(\d+)", data[0])
                    if match:
                        msg["uid"] = match.group(1).decode()

        finally:
            try:
                conn.logout()
            except Exception:
                pass

    except (OSError, imaplib.IMAP4.error) as e:
        logger.warning(f"Could not resolve UIDs (flags may not work correctly): {e}")

    return messages


def uid_to_sequence_number(
    cfg: dict[str, Any],
    uid: str,
    folder: str = DEFAULT_IMAP_FOLDER,
) -> Optional[str]:
    """
    Convert a real IMAP UID to its sequence number.

    Waggle functions expect sequence numbers, so when the user provides a
    real UID (from our resolved list output), we need to convert it back.

    Returns the sequence number as a string, or None if not found.
    """
    wcfg = build_waggle_config(cfg)
    ctx = ssl.create_default_context()

    try:
        if wcfg.get("imap_tls", True):
            conn = imaplib.IMAP4_SSL(
                wcfg["imap_host"], wcfg.get("imap_port", DEFAULT_IMAP_PORT),
                ssl_context=ctx,
            )
        else:
            conn = imaplib.IMAP4(wcfg["imap_host"], wcfg.get("imap_port", DEFAULT_IMAP_PORT))

        try:
            conn.login(wcfg["user"], wcfg["password"])
            status, _ = conn.select(folder, readonly=True)
            if status != "OK":
                return None

            uid_bytes = uid.encode() if isinstance(uid, str) else uid
            status, data = conn.uid("FETCH", uid_bytes, "(UID)")
            if status == "OK" and data and data[0]:
                match = re.match(rb"^(\d+)\s+\(UID\s+\d+\)", data[0])
                if match:
                    return match.group(1).decode()

            return None

        finally:
            try:
                conn.logout()
            except Exception:
                pass

    except (OSError, imaplib.IMAP4.error) as e:
        logger.warning(f"Could not convert UID {uid} to sequence number: {e}")
        return None


def output_json(data: dict[str, Any]) -> None:
    """Write JSON to stdout. All logging must go to stderr."""
    print(json.dumps(data, indent=2, default=str))


def output_human_list(data: dict[str, Any]) -> None:
    """Write human-readable message list to stdout."""
    messages = data.get("messages", [])
    if not messages:
        print(f"No messages in {data['folder']}.")
        return

    print(f"{'UID':<8} {'From':<30} {'Subject':<40} {'Date':<20} {'Status'}")
    print("-" * 110)
    for msg in messages:
        status = "*" if msg.get("unread") else " "
        from_name = msg.get("from_name", "")
        from_addr = msg.get("from_addr", "")
        # Show name if available, otherwise email; prefer showing the email for clarity
        from_display = f"{from_name} ({from_addr})" if from_name and from_addr else (from_name or from_addr or "")
        subject = msg.get("subject", "(no subject)")
        from_display = from_display[:28] if len(from_display) > 28 else from_display
        subject = subject[:38] if len(subject) > 38 else subject
        date = msg.get("date", "")[:18]
        print(f"{msg['uid']:<8} {from_display:<30} {subject:<40} {date:<20} {status}")


def output_human_read(data: dict[str, Any]) -> None:
    """Write human-readable message to stdout."""
    from_name = data.get("from_name", "")
    from_addr = data.get("from_addr", "")
    from_display = f"{from_name} <{from_addr}>" if from_name else from_addr

    print(f"From: {from_display}")
    print(f"To: {data.get('to', '')}")
    print(f"Date: {data.get('date', '')}")
    print(f"Subject: {data.get('subject', '')}")

    attachments = data.get("attachments", [])
    if attachments:
        names = ", ".join(a.get("filename", "unknown") for a in attachments)
        print(f"Attachments: {names}")

    print("-" * 60)

    body = data.get("body_plain") or data.get("body_html") or "(no body)"
    print(body)


def output_human_check(data: dict[str, Any]) -> None:
    """Write human-readable check result to stdout."""
    count = data.get("unread_count", 0)
    folder = data.get("folder", "INBOX")
    if count == 0:
        print(f"No unread messages in {folder}.")
    else:
        print(f"{count} unread message(s) in {folder}.")


def output_human_flag(data: dict[str, Any]) -> None:
    """Write human-readable flag result to stdout."""
    action = data.get("action", "add")
    prefix = "+" if action == "add" else "-"
    flags_display = " ".join(f"{prefix}{f}" for f in data.get("flags", []))
    uids_display = ", ".join(data.get("uids", []))
    folder = data.get("folder", "INBOX")
    print(f"Flags updated: {flags_display} on UID(s) {uids_display} ({folder})")


def cmd_send(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """Handle the send subcommand."""
    # Handle --dry-run as alias for config command (before email validation)
    if args.dry_run:
        return cmd_config(args, cfg)

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

    # Validate SMTP configuration
    if not validate_config(cfg, require_smtp=True):
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
        body = decode_escape_sequences(args.body)
    else:
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
                    f"Duplicate detected: recently sent to "
                    f"{sanitize_for_display(args.to)} with similar subject"
                )
                logger.info("Use --skip-duplicate-check to override")
                return 0
        except (OSError, ValueError) as e:
            logger.warning(f"Could not check for duplicates: {e}")
            logger.info("Continuing anyway...")

    # Handle reply with threading
    in_reply_to: Optional[str] = None
    references: Optional[str] = None

    if args.message_id:
        try:
            logger.info(f"Fetching original message {args.message_id} for threading...")
            # Convert UID to sequence number for waggle
            seq_num = uid_to_sequence_number(cfg, args.message_id, folder=DEFAULT_IMAP_FOLDER)
            waggle_id = seq_num if seq_num else args.message_id
            original = read_message(
                waggle_id,
                folder=DEFAULT_IMAP_FOLDER,
                config=build_waggle_config(cfg)
            )
            in_reply_to = original.get("message_id")
            references = original.get("reply_references")
            # Append quoted original — waggle's fetch_quoted_body re-fetches
            # via IMAP SEARCH by Message-ID which fails on some providers
            body += format_quote_block(original)
            subject = sanitize_for_display(original.get('subject', 'Unknown'))
            logger.info(f"  Found: {subject}")
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.warning(f"Warning: Could not fetch original message: {e}")
            logger.info("  Continuing without threading headers...")
        except Exception as e:
            logger.warning(f"Unexpected error fetching message: {e}")
            logger.info("  Continuing without threading headers...")

    # Append footer (default: on, unless --no-footer)
    if not args.no_footer:
        footer_text = fetch_footer(
            category=args.footer_category,
            context=args.footer_context,
        )
        if footer_text:
            body = body + "\n\n---\n" + footer_text
            logger.info(f"Appended footer: {footer_text[:60]}...")
        else:
            logger.warning("Footer requested but none available, sending without footer")

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

        logger.info("Email sent successfully!")
        logger.info("  (Saved to Sent folder via waggle)")

        if args.message_id and cfg.get("imap_host"):
            try:
                set_flags(
                    args.message_id,
                    [r"\Seen", r"\Answered"],
                    folder=DEFAULT_IMAP_FOLDER,
                    config=build_waggle_config(cfg),
                )
                logger.info("  (Marked original as Seen+Answered)")
            except Exception as e:
                logger.warning(f"Could not flag original message: {e}")

        return 0

    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        return 1
    except TimeoutError as e:
        logger.error(f"Timeout error: {e}")
        return 1
    except ValueError as e:
        logger.error(f"Invalid input: {e}")
        return 1
    except OSError as e:
        logger.error(f"I/O error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.debug("", exc_info=True)
        return 1


def cmd_config(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """Handle the config subcommand. Validates SMTP and IMAP settings."""
    logger.info(f"herd-mail {__version__}")
    smtp_valid = validate_config(cfg, require_smtp=True, require_imap=False)

    if smtp_valid:
        logger.info("SMTP configuration valid.")
        smtp_user_display = cfg['smtp_user'][:3] + "***" if cfg['smtp_user'] else "***"
        logger.info(f"  SMTP: {smtp_user_display}@{cfg['smtp_host']}:{cfg['smtp_port']}")
        logger.info(f"  From: {cfg['from_name']} <{cfg['from_addr']}>")
    else:
        logger.error("SMTP configuration invalid.")

    if cfg.get("imap_host"):
        logger.info(f"  IMAP: {cfg['imap_host']}:{cfg['imap_port']} (configured)")
    else:
        logger.warning("  IMAP: not configured (set WAGGLE_IMAP_HOST for read commands)")

    return 0 if smtp_valid else 1


def cmd_list(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """Handle the list subcommand."""
    if not validate_config(cfg, require_smtp=False, require_imap=True):
        return 1

    try:
        messages = list_inbox(
            folder=args.folder,
            limit=args.limit,
            config=build_waggle_config(cfg),
        )
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Failed to list messages: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error listing messages: {e}")
        return 1

    # Resolve waggle's sequence numbers to actual IMAP UIDs
    messages = resolve_sequence_to_uids(cfg, messages, folder=args.folder)

    if args.unread:
        messages = [m for m in messages if m.get("unread")]

    data = {
        "folder": args.folder,
        "count": len(messages),
        "messages": messages,
    }

    if args.human:
        output_human_list(data)
    else:
        output_json(data)

    return 0


def cmd_read(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """Handle the read subcommand."""
    if not validate_config(cfg, require_smtp=False, require_imap=True):
        return 1

    # waggle 1.9.12+ uses UID-based IMAP commands (m.uid("FETCH", ...))
    # Pass the real UID directly — no sequence number conversion needed
    try:
        message = read_message(
            args.uid,
            folder=args.folder,
            config=build_waggle_config(cfg),
        )
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Failed to read message {args.uid}: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error reading message: {e}")
        return 1

    if args.human:
        output_human_read(message)
    else:
        output_json(message)

    # Mark as read using UID directly (waggle 1.9.12+ uses UID STORE)
    if not args.no_mark_read:
        try:
            read_message(
                args.uid,
                folder=args.folder,
                mark_read=True,
                config=build_waggle_config(cfg),
            )
            logger.info("  (Marked message as read)")
        except Exception as e:
            logger.warning(f"Could not mark message as read: {e}")

    return 0


def cmd_check(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """
    Handle the check subcommand.

    Exit codes: 0=has unread, 1=no unread, 2=error.
    """
    if not validate_config(cfg, require_smtp=False, require_imap=True):
        return 2

    try:
        messages = list_inbox(
            folder=args.folder,
            config=build_waggle_config(cfg),
        )
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Failed to check messages: {e}")
        return 2
    except Exception as e:
        logger.error(f"Unexpected error checking messages: {e}")
        return 2

    # Resolve waggle's sequence numbers to actual IMAP UIDs
    messages = resolve_sequence_to_uids(cfg, messages, folder=args.folder)

    unread = [m for m in messages if m.get("unread")]

    data = {
        "folder": args.folder,
        "unread_count": len(unread),
        "messages": unread,
    }

    if args.human:
        output_human_check(data)
    else:
        output_json(data)

    return 0 if unread else 1


def cmd_download(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """Handle the download subcommand."""
    if not validate_config(cfg, require_smtp=False, require_imap=True):
        return 1

    # Ensure dest_dir exists
    dest_dir = Path(args.dest_dir)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Cannot create destination directory: {e}")
        return 1

    # Convert UID to sequence number for waggle
    seq_num = uid_to_sequence_number(cfg, args.uid, folder=args.folder)
    waggle_id = seq_num if seq_num else args.uid

    try:
        files = download_attachments(
            waggle_id,
            folder=args.folder,
            dest_dir=str(dest_dir),
            config=build_waggle_config(cfg),
        )
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Failed to download attachments: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error downloading attachments: {e}")
        return 1

    data = {
        "uid": args.uid,
        "folder": args.folder,
        "files": files,
    }

    output_json(data)
    return 0


def cmd_flag(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """Handle the flag subcommand."""
    if not validate_config(cfg, require_smtp=False, require_imap=True):
        return 1

    uid_list = [u.strip() for u in args.uids.split(",") if u.strip()]
    if not uid_list:
        logger.error("No UIDs provided.")
        return 1

    normalized_flags, errors = validate_imap_flags(args.flags)
    if errors:
        for error in errors:
            logger.error(error)
        return 1

    try:
        if args.action == "add":
            set_flags(
                ",".join(uid_list),
                normalized_flags,
                folder=args.folder,
                config=build_waggle_config(cfg),
            )
        else:
            clear_flags(
                ",".join(uid_list),
                normalized_flags,
                folder=args.folder,
                config=build_waggle_config(cfg),
            )
        data = {
            "uids": uid_list,
            "flags": normalized_flags,
            "action": args.action,
            "folder": args.folder,
            "results": [{"uid": u, "status": "ok"} for u in uid_list],
        }
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error(f"Failed to update flags: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error updating flags: {e}")
        return 1

    if args.human:
        output_human_flag(data)
    else:
        output_json(data)

    return 0


def cmd_move(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """Handle the move subcommand."""
    if not validate_config(cfg, require_smtp=False, require_imap=True):
        return 1

    # Convert UID to sequence number for waggle
    seq_num = uid_to_sequence_number(cfg, args.uid, folder=args.folder)
    waggle_id = seq_num if seq_num else args.uid

    try:
        move_message(
            waggle_id,
            args.dest_folder,
            src_folder=args.folder,
            config=build_waggle_config(cfg),
        )
    except (ConnectionError, TimeoutError, OSError, RuntimeError) as e:
        logger.error(f"Failed to move message: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error moving message: {e}")
        return 1

    data = {
        "uid": args.uid,
        "from_folder": args.folder,
        "to_folder": args.dest_folder,
    }

    if args.human:
        print(f"Moved UID {args.uid} from {args.folder} to {args.dest_folder}")
    else:
        output_json(data)

    return 0


def get_folder_stats(
    cfg: dict[str, Any],
    folders: Optional[list[str]] = None,
    days: int = 7,
) -> list[dict[str, Any]]:
    """Collect per-folder message counts via a single IMAP connection.

    For each folder returns total message count, unread (UNSEEN) count, and
    the number of messages received within the last `days` days. Reuses the
    same direct-IMAP pattern as resolve_sequence_to_uids() so it does not
    depend on waggle's listing layer.

    Args:
        cfg: Configuration dictionary.
        folders: Explicit folder list. If None, every folder LIST returns
            (excluding \\Noselect containers) is measured.
        days: Window in days for the "recent" count.

    Returns:
        A list of {folder, total, unread, recent, error} dicts. Folders that
        cannot be selected get an `error` string and zeroed counts.
    """
    wcfg = build_waggle_config(cfg)
    ctx = ssl.create_default_context()
    cutoff = (
        datetime.date.today() - datetime.timedelta(days=days)
    ).strftime("%d-%b-%Y")
    results: list[dict[str, Any]] = []

    try:
        if wcfg.get("imap_tls", True):
            conn = imaplib.IMAP4_SSL(
                wcfg["imap_host"], wcfg.get("imap_port", DEFAULT_IMAP_PORT),
                ssl_context=ctx,
            )
        else:
            conn = imaplib.IMAP4(wcfg["imap_host"], wcfg.get("imap_port", DEFAULT_IMAP_PORT))
    except (OSError, imaplib.IMAP4.error) as e:
        logger.error(f"Could not connect to IMAP for stats: {e}")
        return results

    try:
        conn.login(wcfg["user"], wcfg["password"])

        # Discover folders if not given explicitly.
        if folders is None:
            folders = []
            status, data = conn.list()
            if status == "OK" and data:
                for raw in data:
                    if raw is None:
                        continue
                    line = raw.decode(errors="replace")
                    # Skip containers that cannot hold messages.
                    if "\\Noselect" in line:
                        continue
                    # Folder name is the final token, possibly quoted.
                    if line.endswith('"'):
                        name = line[line.rfind(' "') + 2:-1]
                    else:
                        name = line.split()[-1].strip('"')
                    if name:
                        folders.append(name)

        for folder in folders:
            entry: dict[str, Any] = {
                "folder": folder,
                "total": 0,
                "unread": 0,
                "recent": 0,
                "error": None,
            }
            try:
                status, _ = conn.select(f'"{folder}"', readonly=True)
                if status != "OK":
                    entry["error"] = "could not select"
                    results.append(entry)
                    continue
                status, d = conn.search(None, "ALL")
                entry["total"] = len(d[0].split()) if d and d[0] else 0
                status, d = conn.search(None, "UNSEEN")
                entry["unread"] = len(d[0].split()) if d and d[0] else 0
                status, d = conn.search(None, f"(SINCE {cutoff})")
                entry["recent"] = len(d[0].split()) if d and d[0] else 0
            except (imaplib.IMAP4.error, OSError) as e:
                entry["error"] = str(e)
            results.append(entry)
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    return results


def output_human_stats(data: dict[str, Any]) -> None:
    """Pretty-print folder stats as an aligned table."""
    days = data.get("days", 7)
    rows = data.get("folders", [])
    if not rows:
        print("No folders found.")
        return
    name_w = max((len(r["folder"]) for r in rows), default=6)
    name_w = max(name_w, len("Folder"))
    header = f"{'Folder':<{name_w}}  {'total':>7}  {'unread':>7}  {'last' + str(days) + 'd':>7}"
    print(header)
    print("-" * len(header))
    for r in rows:
        if r.get("error"):
            print(f"{r['folder']:<{name_w}}  {'ERR':>7}  {'-':>7}  {'-':>7}  ({r['error']})")
        else:
            print(
                f"{r['folder']:<{name_w}}  {r['total']:>7}  {r['unread']:>7}  {r['recent']:>7}"
            )


def cmd_stats(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """Handle the stats subcommand: per-folder counts in one IMAP pass."""
    if not validate_config(cfg, require_smtp=False, require_imap=True):
        return 1

    folders = None
    if args.folder:
        folders = [f.strip() for f in args.folder.split(",") if f.strip()]

    rows = get_folder_stats(cfg, folders=folders, days=args.days)

    data = {
        "days": args.days,
        "count": len(rows),
        "folders": rows,
    }

    if args.human:
        output_human_stats(data)
    else:
        output_json(data)

    return 0


def main() -> int:
    """Main entry point with subcommand dispatch."""
    if not WAGGLE_AVAILABLE:
        logger.error("Error: waggle not installed. Run: pip install waggle-mail")
        if WAGGLE_IMPORT_ERROR:
            logger.error(f"Details: {WAGGLE_IMPORT_ERROR}")
        return 1

    # Backward compat: detect old-style invocation (no subcommand, but --to present)
    # Work on a copy to avoid mutating the global sys.argv
    argv = sys.argv[:]
    if len(argv) > 1 and argv[1].startswith('--'):
        if '--to' in argv:
            logger.warning("Deprecation warning: use 'herd_mail.py send --to ...' instead")
            argv.insert(1, 'send')
        elif '--dry-run' in argv:
            logger.warning("Deprecation warning: use 'herd_mail.py config' instead")
            argv.insert(1, 'send')

    parser = argparse.ArgumentParser(
        description="herd-mail: AI-to-AI email communication via waggle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"herd-mail {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # send subcommand
    send_parser = subparsers.add_parser("send", help="Send an email")
    send_parser.add_argument("--to", required=True, help="Recipient email address")
    send_parser.add_argument("--subject", required=True, help="Email subject line")
    send_parser.add_argument("--body", help="Email body (Markdown supported)")
    send_parser.add_argument("--body-file", help="Read body from file (UTF-8)")
    send_parser.add_argument("--attachment", nargs="+", help="File(s) to attach")
    send_parser.add_argument("--cc", help="CC recipients (comma-separated)")
    send_parser.add_argument("--reply-to", help="Reply-To address")
    send_parser.add_argument("--message-id", help="IMAP message ID to reply to (enables threading)")
    send_parser.add_argument("--rich", action="store_true", help="Enable rich HTML formatting")
    send_parser.add_argument("--footer", action="store_true", default=True, help="Append a rotating herd-inbox adoption footer (default: on)")
    send_parser.add_argument("--no-footer", action="store_true", help="Disable footer (overrides default)")
    send_parser.add_argument("--footer-category", choices=["token_economics", "social_proof", "fomo", "cheeky"], help="Footer category filter")
    send_parser.add_argument("--footer-context", choices=["announcement", "discussion"], help="Footer context filter")
    send_parser.add_argument("--skip-duplicate-check", action="store_true", help="Skip duplicate detection")
    send_parser.add_argument("--dry-run", action="store_true", help="Validate config without sending")

    # list subcommand
    list_parser = subparsers.add_parser("list", help="List messages in a folder")
    list_parser.add_argument("--folder", default=DEFAULT_IMAP_FOLDER, help="IMAP folder (default: INBOX)")
    list_parser.add_argument("--limit", type=int, default=DEFAULT_LIST_LIMIT, help="Max messages (default: 20)")
    list_parser.add_argument("--unread", action="store_true", help="Only show unread messages")
    list_parser.add_argument("--human", action="store_true", help="Human-readable output")

    # read subcommand
    read_parser = subparsers.add_parser("read", help="Read a full message by UID")
    read_parser.add_argument("uid", help="IMAP message UID")
    read_parser.add_argument("--folder", default=DEFAULT_IMAP_FOLDER, help="IMAP folder (default: INBOX)")
    read_parser.add_argument("--human", action="store_true", help="Human-readable output")
    read_parser.add_argument("--no-mark-read", action="store_true", help="Don't mark message as read")

    # check subcommand
    check_parser = subparsers.add_parser("check", help="Check for unread messages")
    check_parser.add_argument("--folder", default=DEFAULT_IMAP_FOLDER, help="IMAP folder (default: INBOX)")
    check_parser.add_argument("--human", action="store_true", help="Human-readable output")

    # download subcommand
    dl_parser = subparsers.add_parser("download", help="Download attachments from a message")
    dl_parser.add_argument("uid", help="IMAP message UID")
    dl_parser.add_argument("--folder", default=DEFAULT_IMAP_FOLDER, help="IMAP folder (default: INBOX)")
    dl_parser.add_argument("--dest-dir", default=".", help="Destination directory (default: .)")

    # flag subcommand
    flag_parser = subparsers.add_parser("flag", help="Manage IMAP flags on messages")
    flag_parser.add_argument("action", choices=["add", "remove"], help="Flag operation")
    flag_parser.add_argument("uids", help="Message UID(s), comma-separated for bulk")
    flag_parser.add_argument("flags", nargs="+", help=r"Flags: \Seen \Answered \Flagged")
    flag_parser.add_argument("--folder", default=DEFAULT_IMAP_FOLDER, help="IMAP folder (default: INBOX)")
    flag_parser.add_argument("--human", action="store_true", help="Human-readable output")

    # move subcommand
    move_parser = subparsers.add_parser("move", help="Move a message to another folder")
    move_parser.add_argument("uid", help="Message UID")
    move_parser.add_argument("dest_folder", help="Destination IMAP folder")
    move_parser.add_argument("--folder", default=DEFAULT_IMAP_FOLDER, help="Source folder (default: INBOX)")
    move_parser.add_argument("--human", action="store_true", help="Human-readable output")

    # stats subcommand
    stats_parser = subparsers.add_parser("stats", help="Show per-folder message counts (total/unread/recent)")
    stats_parser.add_argument("--folder", help="Comma-separated folders to measure (default: all folders)")
    stats_parser.add_argument("--days", type=int, default=7, help="Window in days for the recent count (default: 7)")
    stats_parser.add_argument("--human", action="store_true", help="Human-readable table output")

    # config subcommand
    subparsers.add_parser("config", help="Validate configuration")

    args = parser.parse_args(argv[1:])

    if not args.command:
        parser.print_help()
        return 1

    # Load configuration
    try:
        cfg = get_config()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1

    # Dispatch to command handler
    commands = {
        "send": cmd_send,
        "list": cmd_list,
        "read": cmd_read,
        "check": cmd_check,
        "download": cmd_download,
        "flag": cmd_flag,
        "move": cmd_move,
        "stats": cmd_stats,
        "config": cmd_config,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args, cfg)

    logger.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
