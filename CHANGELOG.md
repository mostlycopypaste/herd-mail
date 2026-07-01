# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **UID→sequence-number resolution (#14):** Removed the remaining
  `uid_to_sequence_number()` / `resolve_sequence_to_uids()` round-trips from
  `send --message-id`, `list`, `check`, `download`, and `move`. waggle 1.9.12+
  uses UID-based IMAP commands and `list_inbox()` already returns real UIDs, so
  the conversion mapped valid UIDs to stale sequence numbers — silently dropping
  `In-Reply-To`/`References` threading headers on replies and raising
  `Invalid messageset` on list/flag. All commands now pass the real UID directly
  (mirrors the 3.1.1 `cmd_read` fix).

## [3.3.0] - 2026-06-17

### Added

- **`stats` subcommand:** Reports per-folder message counts — total, unread, and received within the last N days — in a single IMAP connection. Use `herd_mail.py stats --human` for an aligned table over all folders, `--folder A,B` to limit, and `--days N` to set the recent window (default 7). JSON output by default; `--human` for a table. Replaces the need for one-off folder-census scripts.
- **`scripts/oc-helpers/`:** Version-controlled, deployment-specific example wrappers and automation built on top of herd-mail (mail wrapper, noise auto-filer, subjects-only buzz scan, local-model triage digest). See `scripts/oc-helpers/README.md`. These are examples to adapt, not general-purpose tooling.
- **Noise-filer activity log:** `auto_file_noise.py` now appends a tab-delimited, greppable log (one line per filed message + a per-run SUMMARY line). Configurable via `--log-file` / `NOISE_FILTER_LOG`; logs are gitignored.

### Fixed

- **`auto_file_noise.py --format json` crash:** `json` was used but never imported. Added the import.
- **`requests` import crash:** v3.2.0 made `requests` a hard top-level import, which broke the CLI (and CI) anywhere `requests` wasn't installed. It is now a guarded optional import — the rotating footer degrades gracefully when `requests` is absent — and is declared as a real dependency in `pyproject.toml`.

### CI / packaging

- Declared `requests>=2.28` in `pyproject.toml` dependencies.
- CI now installs the package itself (`pip install -e .[dev]`) so test dependencies stay in sync with `pyproject.toml` instead of a hardcoded list.

## [3.2.0] - 2026-05-14

### Added

- **Rotating adoption footer:** `send` can append a rotating footer fetched from the herd-inbox API (`--footer`, on by default; `--no-footer` to disable; `--footer-category`/`--footer-context` to filter). Requires `HERD_INBOX_ADMIN_KEY`; silently skipped if unset or the API is unreachable.

### Dependencies

- Adds `requests` (used by the footer fetch).

## [3.1.1] - 2026-04-28

### Fixed

- **UID-based IMAP operations:** Removed `uid_to_sequence_number()` conversion in `cmd_read()` to align with waggle 1.9.12+, which now uses `m.uid("FETCH", ...)` and `m.uid("STORE", ...)` instead of sequence-number-based commands. Fixes "Message N not found" and "Invalid messageset" errors.
- **Sent folder detection:** Now works with waggle 1.9.12+ Sent folder auto-detection for AWS WorkMail ("Sent Items").

### Dependencies

- **waggle-mail:** Now requires `>=1.9.12` (up from `>=1.8.7`)

## [3.1.0] - 2026-04-28

### Changed

- **waggle refactor:** Replaced internal `save_to_sent()` and `imap_store_flags()` functions with waggle native APIs (`waggle.send_email(save_sent=True)`, `waggle.set_flags()`, `waggle.clear_flags()`).
- **Code reduction:** -538 lines net (removed 13 obsolete tests).
- **Dependencies:** Updated to waggle-mail>=1.8.7.

### Fixed

- **Auto-mark-read:** Uses waggle's native `read_message(mark_read=True)` instead of manual flag workaround.

## [3.0.0] - Earlier

- Initial stable release.
- Full IMAP/SMTP email CLI for AI agent communication.
- Support for sending, reading, listing, flagging, moving emails.
- `--rich` Markdown-to-HTML formatting.
- `batch_file_emails.py` for daily email filing.
