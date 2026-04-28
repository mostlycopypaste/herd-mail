# DPRI Review: herd-mail waggle refactor

## Phase: Implement → Verify

### Changes Summary

**Commit:** `8e19c6a` on `feature/waggle-refactor`

**Files changed:**
- `herd_mail.py` — 3 additions, 44 removals (net: -41 lines)
- `test_herd_mail.py` — 115 additions, 538 removals (net: -423 lines)

### What was removed
1. **`save_to_sent()`** function (91 lines) — replaced by `waggle.send_email(save_sent=True)`
2. **`imap_store_flags()`** function (80 lines) — replaced by `waggle.set_flags()`/`waggle.clear_flags()`
3. **`SENT_FOLDER_CANDIDATES`** constant — no longer needed
4. **Unused imports:** `EmailMessage`, `formatdate`
5. **Test classes:** `TestSaveToSent` (6 tests), `TestImapStoreFlags` (6 tests)

### What was added
1. `set_flags`, `clear_flags` added to waggle import
2. `cmd_send` now uses `send_email(save_sent=True)` (default behavior, no explicit flag needed)
3. `cmd_read` now uses `read_message(mark_read=True)` instead of `imap_store_flags`
4. `cmd_flag` now uses `set_flags()`/`clear_flags()` with comma-separated UIDs
5. Reply marking uses `set_flags(uid, [r"\Seen", r"\Answered"], ...)` instead of `imap_store_flags`

### What was kept
- `resolve_sequence_to_uids()` and `uid_to_sequence_number()` — still needed because `waggle.list_inbox()` returns sequence numbers labeled as "uid" (uses `m.fetch()` not `m.uid()`)
- `imaplib` import — still used by the sequence/UID bridge functions
- All CLI flags and arguments — unchanged

### Test Results
- **92 tests passing** (was 105, removed 13 obsolete tests for deleted functions)
- All command integration tests updated to mock waggle functions instead of removed ones
- `TestWaggleStubs` updated to include `set_flags` and `clear_flags`

### Verification Checklist
- [x] Module imports without error
- [x] All 92 unit tests pass
- [x] No references to `save_to_sent`, `imap_store_flags`, or `SENT_FOLDER_CANDIDATES`
- [x] No unused imports from removed code
- [ ] Manual integration test with AWS WorkMail (send, read, flag, check, list)
- [ ] Daily email filing cron job still works
- [ ] Move command still works (uses `move_message` unchanged)

### Risk Assessment
- **Low risk:** All changes are internal refactoring — no CLI interface changes
- **Medium risk:** `set_flags`/`clear_flags` use real UIDs (not sequence numbers) — need manual verification
- **Low risk:** `send_email(save_sent=True)` is waggle's default behavior — should just work
- **Note:** `read_message(mark_read=True)` calls waggle with the UID we pass, but waggle uses `m.fetch(uid, ...)` which is actually a sequence number fetch. This means we need to pass the *sequence number*, not the real UID, for read_message to work correctly. The `cmd_read` function already does `uid_to_sequence_number()` conversion before calling `read_message()`.

### Recommendation
**Proceed to Merge** after manual integration test. The refactoring is clean, tests pass, and CLI interface is unchanged.