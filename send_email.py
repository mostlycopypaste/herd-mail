#!/usr/bin/env python3
"""
send-email-waggle: A secure, user-friendly wrapper for waggle email sending.

Features:
- Markdown to HTML conversion with optional rich formatting
- Thread-aware replies (fetches original for quoting)
- Attachment support with security validation
- Duplicate prevention (checks send log)
- Automatic Sent folder saving via IMAP
- Environment-based configuration (no hardcoded credentials)

Usage:
    # Send simple email
    python3 send_email.py --to recipient@example.com --subject "Hello" --body "Message"

    # Send with body from file
    python3 send_email.py --to recipient@example.com --subject "Hello" --body-file message.md

    # Reply to a message (auto-fetches original for threading)
    python3 send_email.py --message-id 42 --to sender@example.com --subject "Re: Hello"

    # With attachment
    python3 send_email.py --to recipient@example.com --body "See attached" --attachment file.pdf

    # Rich HTML formatting (requires markdown + pygments)
    python3 send_email.py --to recipient@example.com --body-file message.md --rich

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

Author: O.C.
License: MIT
"""

import argparse
import os
import sys
from pathlib import Path

# Add local waggle development path if present
LOCAL_WAGGLE = Path(__file__).parent.parent / "waggle"
if LOCAL_WAGGLE.exists():
    sys.path.insert(0, str(LOCAL_WAGGLE))

try:
    from waggle import send_email, check_recently_sent, read_message
except ImportError as e:
    print(f"Error: waggle not installed. Run: pip install waggle-mail")
    print(f"Details: {e}")
    sys.exit(1)


def get_config():
    """Build configuration from environment variables."""
    return {
        "smtp_host": os.environ.get("WAGGLE_HOST"),
        "smtp_port": int(os.environ.get("WAGGLE_PORT", "465")),
        "smtp_user": os.environ.get("WAGGLE_USER"),
        "smtp_pass": os.environ.get("WAGGLE_PASS"),
        "from_addr": os.environ.get("WAGGLE_FROM"),
        "from_name": os.environ.get("WAGGLE_NAME", ""),
        "use_tls": os.environ.get("WAGGLE_TLS", "true").lower() == "true",
        "imap_host": os.environ.get("WAGGLE_IMAP_HOST"),
        "imap_port": int(os.environ.get("WAGGLE_IMAP_PORT", "993")),
        "imap_tls": os.environ.get("WAGGLE_IMAP_TLS", "true").lower() == "true",
        "send_log": os.environ.get("WAGGLE_SEND_LOG"),
    }


def validate_config(cfg, require_smtp=True):
    """Validate configuration has required values."""
    errors = []
    
    if require_smtp:
        required = ["smtp_host", "smtp_user", "smtp_pass", "from_addr"]
        for key in required:
            if not cfg.get(key):
                errors.append(f"Missing {key} (set WAGGLE_{key.upper()})")
    
    if errors:
        print("Configuration errors:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print("\nSee .envrc.template for required variables.", file=sys.stderr)
        return False
    
    return True


def build_waggle_config(cfg):
    """Convert our config to waggle's expected format."""
    return {
        "host": cfg["smtp_host"],
        "port": cfg["smtp_port"],
        "user": cfg["smtp_user"],
        "password": cfg["smtp_pass"],
        "from_addr": cfg["from_addr"],
        "from_name": cfg["from_name"],
        "tls": cfg["use_tls"],
        "imap_host": cfg.get("imap_host"),
        "imap_port": cfg.get("imap_port", 993),
        "imap_tls": cfg.get("imap_tls", True),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Send emails with Markdown, attachments, and threading via waggle",
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
    
    # Load configuration
    cfg = get_config()
    
    if args.dry_run:
        if validate_config(cfg):
            print("Configuration valid!")
            print(f"  SMTP: {cfg['smtp_user']}@{cfg['smtp_host']}:{cfg['smtp_port']}")
            print(f"  From: {cfg['from_name']} <{cfg['from_addr']}>")
            if cfg.get("imap_host"):
                print(f"  IMAP: {cfg['imap_host']}:{cfg['imap_port']} (Sent folder enabled)")
            return 0
        return 1
    
    # Validate configuration
    if not validate_config(cfg):
        return 1
    
    # Get body content
    body = None
    if args.body_file:
        try:
            with open(args.body_file, "r", encoding="utf-8") as f:
                body = f.read()
        except FileNotFoundError:
            print(f"Error: Body file not found: {args.body_file}", file=sys.stderr)
            return 1
        except UnicodeDecodeError as e:
            print(f"Error: Body file must be UTF-8: {e}", file=sys.stderr)
            return 1
    elif args.body:
        body = args.body
    else:
        # Try reading from stdin
        if not sys.stdin.isatty():
            body = sys.stdin.read()
        else:
            body = "(No message body)"
    
    # Check for duplicates (unless skipped)
    if not args.skip_duplicate_check:
        if check_recently_sent(args.to, args.subject, within_minutes=5, config=build_waggle_config(cfg)):
            print(f"⚠️ Duplicate detected: recently sent to {args.to} with similar subject")
            print("Use --skip-duplicate-check to override")
            return 0  # Not an error, just skipped
    
    # Handle reply with threading
    in_reply_to = None
    references = None
    
    if args.message_id:
        try:
            print(f"Fetching original message {args.message_id} for threading...")
            original = read_message(args.message_id, folder="INBOX", config=build_waggle_config(cfg))
            in_reply_to = original.get("message_id")
            references = original.get("reply_references")
            print(f"  Found: {original.get('subject', 'Unknown')}")
        except Exception as e:
            print(f"Warning: Could not fetch original message: {e}", file=sys.stderr)
            print("  Continuing without threading headers...")
    
    # Send the email
    try:
        print(f"Sending email to {args.to}...")
        
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
        
        print(f"✓ Email sent successfully!")
        if cfg.get("imap_host"):
            print("  (Saved to Sent folder via IMAP)")
        
        return 0
        
    except Exception as e:
        print(f"✗ Failed to send email: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
