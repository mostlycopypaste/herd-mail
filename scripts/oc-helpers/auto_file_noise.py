#!/usr/bin/env python3
"""Auto-file noisy CC'd emails and automated notifications.

Three filter categories:
1. Noisy senders (Gaston, Colette, Nova): CC'd emails → AI-Agents folder
   Direct emails (To: oc@) stay in inbox for processing.
2. GitHub notifications → Notifications folder
3. Bounce/delivery failure notices → Notifications folder

Exit codes: 0=success (or nothing to do), 1=error
"""

import argparse
import datetime
import imaplib
import json
import os
import re
import socket
import sys

socket.setdefaulttimeout(60)

# Default activity log: each run appends a summary line (and one line per filed
# message) so "what did the noise filter do?" is answerable from a single tail.
# Override with --log-file or the NOISE_FILTER_LOG env var; set to "" to disable.
DEFAULT_LOG_FILE = os.environ.get(
    "NOISE_FILTER_LOG",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto_file_noise.log"),
)


def _log_lines(log_file: str, lines: list[str]) -> None:
    """Append lines to the activity log. Never raises — logging must not break filing."""
    if not log_file:
        return
    try:
        with open(log_file, "a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")
    except OSError as e:
        print(f"Warning: could not write log {log_file}: {e}", file=sys.stderr)

# Senders whose CC'd emails get auto-filed (the "noisy trio")
# Bob Ross (email changed May 7)
NOISY_SENDERS = [
    "gaston@bluemoxon.com",
    "colette@pilatesmuse.co",
    "nova@digitalnoise.net",
]

# Patterns for automated notifications (GitHub, bounces, etc.)
NOTIFICATION_SENDERS = [
    "noreply@github.com",
    "notifications@github.com",
]

# GitHub notification subjects that should stay in inbox (not auto-filed)
# These are actionable — PR reviews, issue comments, direct mentions on our repos
# Also keep GitHub notifications from mostlycopypaste/ org or @oc-mostlycopy (actionable)
GITHUB_KEEP_PATTERNS = [
    "mostlycopypaste/",  # Our org repos
    "@oc-mostlycopy",    # Direct mentions
    "pull request review",
    "requested your review",
]
NOTIFICATION_SUBJECT_PATTERNS = [
    "undelivered mail returned",
    "mail delivery failed",
    "delivery status notification",
    "returned mail",
    "bounce",
]
NOTIFICATION_SENDER_PATTERNS = [
    "amazonses.com",
    "mailer-daemon",
    "postmaster@",
    "bounce@",
]

# Subject patterns for known echo chamber threads — auto-file regardless of sender
# These are threads that generate high volume with near-zero actionable content
ECHO_CHAMBER_SUBJECTS = [
    "name question for the herd",
    "nova status update",
    "daily essay",
]

# Our address — if we're in To:, it's direct; if only in CC:, it's noise
OUR_ADDRESS = "oc@mostlycopyandpaste.com"

TARGET_FOLDER = "AI-Agents"
NOTIFICATIONS_FOLDER = "Notifications"


def is_direct_to_us(headers: str) -> bool:
    """Check if our address is in the To: header (direct email).
    
    If To: contains multiple recipients (including us), it's a broadcast/CC'd herd thread.
    If To: has only us (or us + 1 other), it's direct.
    """
    to_match = re.search(r'^To:\s*(.+)$', headers, re.MULTILINE | re.IGNORECASE)
    if not to_match:
        return False
    to_line = to_match.group(1).lower()
    
    # Count email addresses in To: header
    emails = re.findall(r'[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}', to_line)
    
    # If only 1-2 recipients including us, it's direct
    # If 3+ recipients, it's a broadcast herd thread (treat as CC'd)
    if len(emails) >= 3:
        return False
    
    return OUR_ADDRESS in to_line


def main():
    parser = argparse.ArgumentParser(description="Auto-file noisy CC'd emails and notifications")
    parser.add_argument("--dry-run", action="store_true", help="Preview without moving")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show each email")
    parser.add_argument("--format", choices=["human", "json"], default="human")
    parser.add_argument(
        "--log-file",
        default=DEFAULT_LOG_FILE,
        help="Append a run summary + per-message lines here (default: auto_file_noise.log beside this script; \"\" disables)",
    )
    args = parser.parse_args()

    # Connect to IMAP
    try:
        host = os.environ.get("WAGGLE_IMAP_HOST") or os.environ.get("IMAP_HOST")
        user = os.environ.get("WAGGLE_USER") or os.environ.get("WAGGLE_IMAP_USER")
        passwd = os.environ.get("WAGGLE_PASS") or os.environ.get("WAGGLE_IMAP_PASS")

        if not all([host, user, passwd]):
            print("Error: IMAP credentials not found in environment", file=sys.stderr)
            sys.exit(1)

        conn = imaplib.IMAP4_SSL(host)
        conn.login(user, passwd)
    except Exception as e:
        print(f"Error: Could not connect to IMAP: {e}", file=sys.stderr)
        sys.exit(1)

    conn.select("INBOX")

    # Search for unread emails
    status, data = conn.uid("SEARCH", None, "UNSEEN")
    if not data[0]:
        if args.format == "human":
            print("No unread emails in inbox.")
        conn.logout()
        sys.exit(2)

    uids = data[0].decode().split()
    if args.format == "human":
        print(f"Scanning {len(uids)} unread emails for noisy senders and notifications...")

    noisy_count = 0
    notif_count = 0
    direct_count = 0
    skipped_count = 0
    errors = []
    email_details = []

    for uid in uids:
        try:
            # Fetch full headers to check To:, CC:, and From:
            status, data = conn.uid("FETCH", uid, "(BODY.PEEK[HEADER])")
            if not data or not data[0]:
                continue

            header_data = data[0][1] if isinstance(data[0], tuple) else data[0]
            headers = header_data.decode("utf-8", errors="ignore")

            # Extract sender — anchor to From: header to avoid matching Message-ID etc.
            from_line_match = re.search(r"^From:\s*(.+)$", headers, re.MULTILINE | re.IGNORECASE)
            from_line = from_line_match.group(1).lower() if from_line_match else ""
            sender_match = re.search(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", from_line)
            sender = sender_match.group(0) if sender_match else ""

            # Extract subject for logging
            subject_match = re.search(r"^Subject:\s*(.+)$", headers, re.MULTILINE | re.IGNORECASE)
            subject = subject_match.group(1).strip() if subject_match else "(no subject)"
            subject_lower = subject.lower()

            # === Check 1: Notification (GitHub, bounce, etc.) → Notifications folder ===
            is_notification = False

            # GitHub notification senders
            if any(ns in sender for ns in NOTIFICATION_SENDERS):
                is_notification = True

            # Bounce/delivery failure senders
            if any(ns in sender for ns in NOTIFICATION_SENDER_PATTERNS):
                is_notification = True

            # Bounce/delivery failure subjects
            if any(pat in subject_lower for pat in NOTIFICATION_SUBJECT_PATTERNS):
                is_notification = True

            if is_notification:
                # Keep GitHub notifications about our repos in inbox — they're actionable
                if any(ns in sender for ns in NOTIFICATION_SENDERS) and any(
                    kp in subject for kp in GITHUB_KEEP_PATTERNS
                ):
                    skipped_count += 1
                    if args.verbose:
                        print(f"  KEEP (GitHub actionable): UID {uid} from {sender}: {subject[:60]}")
                    continue
                if args.verbose:
                    print(f"  FILE (notification): UID {uid} from {sender}: {subject[:60]}")

                email_details.append({
                    "uid": uid,
                    "from": sender,
                    "subject": subject,
                    "action": "notification",
                })

                if not args.dry_run:
                    # Mark as Seen
                    conn.uid("STORE", uid, "+FLAGS", "(\\Seen)")

                    # Copy to Notifications folder
                    status, _ = conn.uid("COPY", uid, NOTIFICATIONS_FOLDER)
                    if status != "OK":
                        errors.append(f"Failed to COPY UID {uid} to {NOTIFICATIONS_FOLDER}")
                        continue

                    # Delete from INBOX
                    conn.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
                    conn.select("INBOX")

                notif_count += 1
                continue

            # === Check 2: Echo chamber subject patterns → AI-Agents folder ===
            if any(pat in subject_lower for pat in ECHO_CHAMBER_SUBJECTS):
                if args.verbose:
                    print(f"  FILE (echo chamber): UID {uid} from {sender}: {subject[:60]}")

                email_details.append({
                    "uid": uid,
                    "from": sender,
                    "subject": subject,
                    "action": "echo_chamber",
                })

                if not args.dry_run:
                    conn.uid("STORE", uid, "+FLAGS", "(\\Seen)")
                    status, _ = conn.uid("COPY", uid, TARGET_FOLDER)
                    if status != "OK":
                        errors.append(f"Failed to COPY UID {uid} to {TARGET_FOLDER}")
                        continue
                    conn.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
                    conn.select("INBOX")

                noisy_count += 1
                continue

            # === Check 3: Noisy sender CC'd → AI-Agents folder ===
            if not any(ns in sender for ns in NOISY_SENDERS):
                skipped_count += 1
                continue

            # Check if this is a direct email (To: us) or CC'd
            if is_direct_to_us(headers):
                direct_count += 1
                if args.verbose:
                    print(f"  KEEP (direct): UID {uid} from {sender}: {subject[:60]}")
                continue

            # This is a CC'd email from a noisy sender — auto-file it
            if args.verbose:
                print(f"  FILE (CC'd): UID {uid} from {sender}: {subject[:60]}")

            email_details.append({
                "uid": uid,
                "from": sender,
                "subject": subject,
                "action": "filed",
            })

            if not args.dry_run:
                # Mark as Seen first
                conn.uid("STORE", uid, "+FLAGS", "(\\Seen)")

                # Copy to target folder
                status, _ = conn.uid("COPY", uid, TARGET_FOLDER)
                if status != "OK":
                    errors.append(f"Failed to COPY UID {uid} to {TARGET_FOLDER}")
                    continue

                # Delete from INBOX
                conn.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
                conn.select("INBOX")

            noisy_count += 1

        except Exception as e:
            errors.append(f"Error processing UID {uid}: {e}")
            continue

    # Expunge deleted messages
    if not args.dry_run and (noisy_count + notif_count) > 0:
        conn.select("INBOX")
        conn.expunge()

    # Get remaining counts
    conn.select("INBOX")
    status, data = conn.uid("SEARCH", None, "UNSEEN")
    unread_remaining = len(data[0].decode().split()) if data[0] else 0

    conn.logout()

    # === Activity log: one line per filed message + a run summary line ===
    # Skipped (not-noisy) messages are intentionally NOT logged to keep the log
    # focused on actions taken. Dry runs are tagged so they are distinguishable.
    if not args.dry_run:
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        log_lines = []
        for d in email_details:
            log_lines.append(
                f"{ts}\t{d['action'].upper()}\tuid={d['uid']}\tfrom={d['from']}\tsubject={d['subject'][:120]}"
            )
        log_lines.append(
            f"{ts}\tSUMMARY\tfiled_noisy={noisy_count}\tfiled_notifications={notif_count}"
            f"\tdirect_kept={direct_count}\tskipped={skipped_count}"
            f"\tunread_remaining={unread_remaining}\terrors={len(errors)}"
        )
        _log_lines(args.log_file, log_lines)

    # Output
    if args.format == "json":
        result = {
            "filed_noisy": noisy_count,
            "filed_notifications": notif_count,
            "direct_kept": direct_count,
            "skipped_not_noisy": skipped_count,
            "unread_remaining": unread_remaining,
            "errors": errors,
            "dry_run": args.dry_run,
            "details": email_details,
        }
        print(json.dumps(result, indent=2))
    else:
        prefix = "📋 DRY RUN — " if args.dry_run else ""
        print(f"\n{prefix}Noisy sender filter complete:")
        print(f"   Filed (CC'd from noisy trio → AI-Agents): {noisy_count}")
        print(f"   Filed (notifications → Notifications): {notif_count}")
        print(f"   Kept (direct To: us): {direct_count}")
        print(f"   Skipped (not from noisy senders): {skipped_count}")
        print(f"   Unread remaining in inbox: {unread_remaining}")
        if errors:
            print(f"   ⚠️  Errors: {len(errors)}")
            for err in errors[:5]:
                print(f"      - {err}")

    if errors:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()