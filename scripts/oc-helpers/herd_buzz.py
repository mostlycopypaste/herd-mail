#!/usr/bin/env python3
"""Lightweight subject-scan of the AI-Agents folder for heartbeat awareness.

After auto_file_noise.py moves CC'd herd chatter to AI-Agents, we go blind to
that folder. This peeks at SUBJECTS + senders ONLY (no bodies) of recent filed
mail so O.C. can notice:
  - Hot threads: a subject thread with many messages in the window (heating up)
  - Mentions: subjects that name O.C. directly

It reuses scripts/herd_mail_wrapper.sh (proven auth) instead of doing its own
IMAP, so it stays robust to credential plumbing. Near-zero token cost: prints a
compact summary, never message bodies.

Usage:
  python3.13 scripts/herd_buzz.py                 # last 24h, default thresholds
  python3.13 scripts/herd_buzz.py --hours 12
  python3.13 scripts/herd_buzz.py --hot-threshold 6 --scan 200

Exit codes: 0=success (buzz or quiet), 1=error
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

FOLDER = "AI-Agents"
OUR_NAMES = ["o.c.", "oc@mostlycopyandpaste.com"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WRAPPER = os.path.join(SCRIPT_DIR, "herd_mail_wrapper.sh")


def normalize_subject(subj: str) -> str:
    """Strip Re:/Fwd: prefixes for thread grouping."""
    s = subj.strip()
    while True:
        m = re.match(r'^(re|fwd|fw)\s*:\s*', s, re.IGNORECASE)
        if not m:
            break
        s = s[m.end():]
    return s.strip().lower()


def fetch_messages(scan: int):
    """Return list of message dicts from AI-Agents via the wrapper (JSON)."""
    out = subprocess.run(
        [WRAPPER, "list", "--folder", FOLDER, "--limit", str(scan)],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        sys.stderr.write(f"herd_buzz: wrapper list failed: {out.stderr.strip()[:200]}\n")
        return None
    # herd_mail list prints JSON by default (no --human)
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        sys.stderr.write("herd_buzz: could not parse wrapper JSON output\n")
        return None
    return data.get("messages", [])


def parse_date(s: str):
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="Scan AI-Agents subjects for hot threads / mentions")
    ap.add_argument("--hours", type=int, default=24, help="Look-back window in hours (default 24)")
    ap.add_argument("--hot-threshold", type=int, default=4,
                    help="Min msgs in a thread within window to flag HOT (default 4)")
    ap.add_argument("--scan", type=int, default=150, help="Max recent messages to scan (default 150)")
    args = ap.parse_args()

    msgs = fetch_messages(args.scan)
    if msgs is None:
        return 1

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    threads = defaultdict(int)
    thread_display = {}
    thread_senders = defaultdict(set)
    mentions = []
    in_window = 0

    for m in msgs:
        subj = (m.get("subject") or "").strip()
        frm = (m.get("from_addr") or m.get("from_raw") or "").strip()
        dt = parse_date(m.get("date", ""))
        if dt is not None and dt < cutoff:
            continue
        in_window += 1
        norm = normalize_subject(subj)
        if not norm:
            continue
        threads[norm] += 1
        thread_display.setdefault(norm, subj)
        if frm:
            thread_senders[norm].add(frm)
        if any(n in subj.lower() for n in OUR_NAMES):
            mentions.append((subj, frm))

    hot = [(thread_display[k], v, sorted(thread_senders[k]))
           for k, v in threads.items() if v >= args.hot_threshold]
    hot.sort(key=lambda x: -x[1])

    if not hot and not mentions:
        print(f"Herd buzz: quiet ({in_window} filed msgs / {len(threads)} threads in last {args.hours}h, none hot)")
        return 0

    print(f"Herd buzz (last {args.hours}h, filed to AI-Agents):")
    for subj, cnt, senders in hot:
        who = ", ".join(s.split("@")[0] for s in senders[:4])
        print(f"  🔥 HOT [{cnt} msgs] {subj}  (from: {who})")
    for subj, frm in mentions:
        print(f"  📛 MENTION: {subj}  (from {frm})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
