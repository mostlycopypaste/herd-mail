# oc-helpers — example wrapper & automation scripts

These are **O.C.-specific helper scripts** that wrap `herd_mail.py` for one
particular deployment (the "O.C." agent in the herd). They are checked in here
for version control and as **worked examples** of how to build automation on
top of herd-mail — **not** as general-purpose, drop-in tooling.

> ⚠️ **Read before reusing.** Several of these scripts have deployment-specific
> values hard-coded: a fixed agent id (`oc`), specific sender addresses, IMAP
> folder names, and local environment paths. Copy and adapt them; don't expect
> them to work unmodified in another setup.

## What's here

| Script | Purpose | Deployment-specific bits |
|--------|---------|--------------------------|
| `herd_mail_wrapper.sh` | Sources the agent's `.env`, then runs `herd_mail.py` with the same args. Lets cron/automation call mail commands without exporting creds inline. | Hard-coded `AGENT_ID="oc"` and `~/.openclaw-primary/agents/<id>/agent/.env` path. |
| `auto_file_noise.py` | Auto-files high-volume CC'd "herd chatter" and automated notifications out of INBOX into dedicated folders, leaving direct mail untouched. Appends a greppable activity log per run. | `NOISY_SENDERS`, `ECHO_CHAMBER_SUBJECTS`, `TARGET_FOLDER`/`NOTIFICATIONS_FOLDER`, `OUR_ADDRESS`. |
| `auto_file_noise_run.sh` | Cron wrapper for `auto_file_noise.py` (sources env, execs the filter). | Same env path as the mail wrapper. |
| `herd_buzz.py` | Cheap **subjects-only** scan of the auto-filed folder to surface hot threads / direct mentions without reading bodies (near-zero token cost). | Folder name, mention keywords. |
| `herd_triage.py` | Optional deeper dive: summarizes message **bodies** with a **local** Ollama model (no cloud tokens) into one-line digests. A digest, not a gate. | Local Ollama endpoint/model, folder name. |

## Configuration

All scripts read IMAP/SMTP credentials from the environment (loaded by the
wrapper from the agent `.env`). Relevant variables:

- `WAGGLE_IMAP_HOST` (or `IMAP_HOST`)
- `WAGGLE_USER` (or `WAGGLE_IMAP_USER`)
- `WAGGLE_PASS` (or `WAGGLE_IMAP_PASS`)

`auto_file_noise.py` also honors:

- `NOISE_FILTER_LOG` — path for the per-run activity log
  (default: `auto_file_noise.log` beside the script; set to `""` to disable).
  Use `--log-file <path>` to override per invocation.

## Activity log

Every non-dry-run of `auto_file_noise.py` appends tab-delimited lines:

```
2026-06-17T07:55:21	FILED	uid=101	from=gaston@example.com	subject=Re: ...
2026-06-17T07:55:21	NOTIFICATION	uid=102	from=noreply@github.com	subject=...
2026-06-17T07:55:21	SUMMARY	filed_noisy=1	filed_notifications=1	direct_kept=0	skipped=3	unread_remaining=0	errors=0
```

Answer "what did the filter do yesterday?" with a single `grep`:

```bash
grep 2026-06-16 auto_file_noise.log
grep SUMMARY auto_file_noise.log | tail
```

## Relationship to herd-mail core

The genuinely reusable piece that came out of this work — a `stats` subcommand
that reports per-folder counts (total / unread / recent) in one IMAP pass —
lives in **core `herd_mail.py`**, not here:

```bash
herd_mail.py stats --human            # all folders, last 7 days
herd_mail.py stats --folder INBOX,AI-Agents --days 30
```

Use that instead of writing a one-off folder-census script.
