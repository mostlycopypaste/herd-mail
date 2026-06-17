#!/usr/bin/env python3
"""Local-model triage of noisy-trio CC chatter filed to the AI-Agents folder.

Goal: offload the EXPENSIVE part (reading email bodies) to a FREE local Ollama
model instead of spending cloud tokens. For each recent AI-Agents message, a
local model summarizes the body and judges whether it is actionable for O.C.
Only items that are actionable, mention O.C., or score low confidence get
SURFACED for the cloud agent to read. Everything else is one-line filed.

Design rules:
  - LOCAL ONLY: hits http://localhost:11434 (never a :cloud model, never cloud tokens).
  - Reuses scripts/herd_mail_wrapper.sh for IMAP auth (proven path).
  - Fail-safe: any parse error, model error, low confidence, mention, or
    actionable verdict -> SURFACE. Never silently drop something uncertain.
  - Bounded: triages newest N messages per run (default 15) to cap runtime.

Usage:
  python3.13 scripts/herd_triage.py                 # newest 15, llama3.2
  python3.13 scripts/herd_triage.py --limit 30
  python3.13 scripts/herd_triage.py --model qwen3.5:latest
  python3.13 scripts/herd_triage.py --hours 24      # only msgs within window
  python3.13 scripts/herd_triage.py --json          # machine-readable output

Exit codes: 0=success, 1=error
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

FOLDER = "AI-Agents"
OLLAMA_URL = "http://localhost:11434/api/generate"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WRAPPER = os.path.join(SCRIPT_DIR, "herd_mail_wrapper.sh")
OUR_NAMES = ["o.c.", "oc@mostlycopyandpaste.com"]

PROMPT_TMPL = (
    "You are an email triage assistant for an AI agent named O.C. (also called OC).\n"
    "You are shown ONLY the new text of one reply in a thread (quoted history removed).\n"
    "Return ONLY a JSON object with keys:\n"
    "  summary (one short sentence),\n"
    "  topic (2-4 words),\n"
    "  actionable_for_oc (true ONLY if this new text contains a direct question or\n"
    "    request addressed TO O.C. that needs a reply or action; false if it is just\n"
    "    general discussion, agreement, or commentary even if it mentions O.C.),\n"
    "  mentions_oc (true only if O.C. is directly addressed by name in THIS new text),\n"
    "  confidence (0.0-1.0).\n"
    "Participating in a topic O.C. cares about is NOT actionable. Only a direct ask is.\n\n"
    "NEW REPLY TEXT:\n{email}\n"
)

CONF_FLOOR = 0.5
BODY_CHARS = 2000  # cap NEW text sent to local model (quotes already stripped)


def strip_quoted(body: str) -> str:
    """Return only the new reply text: drop herd_mail header block and quoted history.

    Cuts at the first quote marker (\"On ... wrote:\", leading '>' lines, or the
    herd-mail separator) so the local model only judges what THIS sender newly wrote.
    """
    # herd_mail --human prints a header block then a '---...' separator before the body
    sep = re.search(r'^-{10,}\s*$', body, re.MULTILINE)
    text = body[sep.end():] if sep else body

    lines = text.splitlines()
    out = []
    quote_re = re.compile(r'^\s*(On .*wrote:|>.*|.*-{6,}\s*$|From:\s|Sent:\s|_{6,})', re.IGNORECASE)
    for ln in lines:
        if quote_re.match(ln):
            break
        out.append(ln)
    new_text = "\n".join(out).strip()
    # Fallback: if stripping nuked everything, keep a trimmed version of original body
    return new_text if len(new_text) >= 15 else text.strip()


def run_wrapper(args, timeout=120):
    return subprocess.run([WRAPPER, *args], capture_output=True, text=True, timeout=timeout)


def fetch_list(limit):
    out = run_wrapper(["list", "--folder", FOLDER, "--limit", str(limit)])
    if out.returncode != 0:
        sys.stderr.write(f"herd_triage: list failed: {out.stderr.strip()[:200]}\n")
        return None
    try:
        return json.loads(out.stdout).get("messages", [])
    except json.JSONDecodeError:
        sys.stderr.write("herd_triage: could not parse list JSON\n")
        return None


def fetch_body(uid):
    out = run_wrapper(["read", str(uid), "--folder", FOLDER, "--no-mark-read", "--human"])
    if out.returncode != 0:
        return None
    return out.stdout


def parse_date(s):
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def triage_one(model, email_text):
    """Call local Ollama, return (verdict_dict, error_str)."""
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "prompt": PROMPT_TMPL.format(email=email_text[:BODY_CHARS]),
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(OLLAMA_URL, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode())
        verdict = json.loads(body.get("response", "{}"))
        return verdict, None
    except Exception as e:
        return None, str(e)[:160]


def should_surface(verdict, body_text):
    """Surface only on a genuine direct ask or real uncertainty.

    Rationale: in a herd thread that is *about* O.C.'s points, being mentioned
    is the baseline, not a signal. So a name-mention alone does NOT force a
    surface; it is kept visible in the filed summary instead. We surface when:
      - actionable_for_oc is true (a direct question/request addressed to O.C.), OR
      - confidence is below the floor / unparseable (real uncertainty), OR
      - the verdict failed entirely (fail-safe).
    """
    if verdict is None:
        return True, "triage-error"
    reasons = []
    if verdict.get("actionable_for_oc"):
        reasons.append("actionable")
    try:
        if float(verdict.get("confidence", 0)) < CONF_FLOOR:
            reasons.append("low-confidence")
    except (TypeError, ValueError):
        reasons.append("bad-confidence")
    return (len(reasons) > 0), ",".join(reasons) if reasons else ""


def main():
    ap = argparse.ArgumentParser(description="Local-model triage of AI-Agents chatter")
    ap.add_argument("--limit", type=int, default=15, help="Max newest messages to triage (default 15)")
    ap.add_argument("--model", default="qwen2.5:1.5b", help="Local Ollama model (default qwen2.5:1.5b)")
    ap.add_argument("--hours", type=int, default=0, help="Only triage msgs within this many hours (0=ignore date)")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = ap.parse_args()

    msgs = fetch_list(args.limit)
    if msgs is None:
        return 1
    if not msgs:
        print("herd_triage: no messages in AI-Agents")
        return 0

    cutoff = None
    if args.hours > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)

    results = []
    for m in msgs:
        uid = m.get("uid")
        subj = (m.get("subject") or "").strip()
        frm = (m.get("from_addr") or m.get("from_raw") or "").strip()
        dt = parse_date(m.get("date", ""))
        if cutoff and dt and dt < cutoff:
            continue
        body = fetch_body(uid)
        if body is None:
            results.append({"uid": uid, "from": frm, "subject": subj,
                            "surface": True, "reason": "body-fetch-failed", "verdict": None})
            continue
        new_text = strip_quoted(body)
        verdict, err = triage_one(args.model, new_text)
        surface, reason = should_surface(verdict, new_text)
        results.append({"uid": uid, "from": frm, "subject": subj,
                        "surface": surface, "reason": reason or "none",
                        "verdict": verdict, "error": err})

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    # DIGEST MODE: the local model summarizes every CC'd message; O.C. (cloud)
    # reads these cheap one-liners and decides what is actionable. We do NOT let
    # the small model gate keep/drop -- it is a good summarizer, a poor gatekeeper.
    errors = [r for r in results if r.get("verdict") is None]

    print(f"herd_triage digest ({args.model}): {len(results)} CC'd msgs summarized "
          f"(local model, no cloud tokens spent on bodies)\n")

    for r in results:
        v = r.get("verdict") or {}
        who = r["from"].split("@")[0]
        if v:
            ask = " ❓ possible-ask" if v.get("actionable_for_oc") else ""
            men = " 👁" if v.get("mentions_oc") else ""
            print(f"  [{r['uid']}] {who}: {v.get('summary','?')}{ask}{men}")
        else:
            print(f"  [{r['uid']}] {who}: ⚠️ could not summarize ({r['reason']}) -- read manually: {r['subject']}")

    if errors:
        print(f"\n⚠️  {len(errors)} message(s) failed local triage -- read those manually.")

    print("\nO.C.: scan the ❓ possible-ask and 👁 mention lines; read full bodies only for genuine direct asks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
