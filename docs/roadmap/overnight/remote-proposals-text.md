# remote-proposals-text: a change the modelling loop finds for a remote's part is written as text for that remote's owner, under the remote's own names, against the remote version it read. It is never applied here.
depends-on: []

## What exists (not to be built again)

- `ergostat/numbers/yamledit.py::own` refuses any edit to a part whose `where` is a `RemoteVia`. It says "proposed to that ergostat's owner, as text, never written here", but no text is written. Today `proposals.make` still makes a parameter proposal or an equation proposal for a remote part, with `edit: {"error": ...}`. The proposal sits in the review queue and accept refuses it only because the edit is an error.
- `ergostat/remote/compose.py::one` records `info["parts"][local_ref] = True` and `info["version"]` for each remote. Parts are renamed `{remote}-{n}`. Stand-ins (`_stand_in`) also register in `info["parts"]`.
- `ergostat/remote/cache.py::refresh` writes `<state>/remotes/NAME/model.json`, and the version inside it, without a lock.
- `proposals.locked(p)` (`proposals.lock`, fcntl) is held by `accept` and `supersede`. It is not held across `make()`'s `stored()` … `admit` … `save()`.
- Model-change items fold by id, and a later `made` event merges into the old fields. The model's history is the `ergostat.model.changed` events, which no later model-change event alters.
- Every path that applies a proposal goes through `proposals.accept`: the CLI `ergostat accept` (`cli/numbers.py:257`), the web `proposals/ID/accept` (`web/numbers_api.py:779`), the judge's auto-accept (`numbers/judge.py:581`), the inbox answer (`inbox/answer.py:60`) and the bench adapter (`bench/adapter.py:67`).
- `goodmodel.READS` is classified by topic. `remote` is not a read topic.

## Definition of done

1. **What becomes for-remote.** In `proposals.make`, a found parameter proposal or equation proposal becomes a for-remote proposal when every part it would edit has a `RemoteVia` of one remote. For a parameter, those parts are `parameter.*` of `parameters`. For an equation, the part is its `target` flow. Every other found proposal stays as it is today:
   - one touching local and remote parts, or parts of two remotes, keeps `edit: {"error": …}` and is refused on accept as now;
   - structural proposals, redesigns, block-proposed changes and the owner's what-if are unchanged (still refused through `own`). SPEC says so.
2. **Name lookup.** `compose.one` also keeps `info["names"] = {local_ref: remote_ref}` for each served part (from `parts()`: `parameter.incidents-rate → parameter.rate`). Stand-ins are never put in it.
   - Every part a for-remote text names is looked up there: the target, the causes, the series it was fitted to, and the parts whose equations use a parameter.
   - When any lookup misses, nothing is recorded for that proposal. The local name is never used as a stand-in for the remote one.
   - New parameter names in an equation's text are built from the remote names (`{remote-flow}-per-{remote-cause}`, `time-in-{remote-stock}`) and made free against the remote's parameter names.
3. **The record.** A for-remote record holds exactly these fields: `kind` (`parameter` | `equation`), `title`, `text`, `evidence`, `for_remote`, `subject`, `made_by`, `created`, `made`. This is an allowlist, `remote_text.FIELDS`.
   - `for_remote = {"remote": NAME, "version": V, "parts": {local_ref: remote_ref}}`.
   - `evidence = {"points": n, "window": seconds, "read": [remote refs]}`.
   - `text` says what to change in the remote's names: a parameter's value from → to, ± one standard error; or a flow's equation and the value of each new parameter. It also gives the evidence: points, window and series. It makes no fit claim (no R², no error falling, no gate).
   - The record stores no fit field. None of `fit_before`, `fit_after`, `gate`, `neighbourhood`, `objective`, `estimate`, `predicted`, `fit_gained`, `held_before`, `held_after`, `edit`, `previous`, `parameters` or `version` (the local version) is present with a value.
   - Its state is `checked`. `pending()` excludes any record with `for_remote`, so the review queue, the judge, the inbox entries, MCP and the Model page never offer it.
4. **Recording (lesson-1, lesson-3).** `remote_text.record(p, spec, xs)` runs under `proposals.locked(p)`, and inside that under the remote's cache lock `<state>/remotes/NAME/model.lock` (fcntl, exclusive). Holding both, it:
   - reads the version in `model.json`;
   - compares it with `spec.remotes[NAME]["version"]`, the version the evidence was computed on;
   - appends the events.

   It refuses (records nothing) when either version is missing, empty or unreadable (no file, bad JSON, no `version`) or when they differ. `cache.refresh` takes the same cache lock around reading `have` and writing `model.json`. The lock order is always proposals.lock, then model.lock. Nothing is done under model.lock except the version read and the event append; no model load happens there.
5. **Currency (lesson-3, lesson-2).** `remote_text.current(x, spec)` is true only when `x.for_remote.version` and `spec.remotes[NAME].version` are both non-empty strings and equal. A record version that is missing, a remote absent from the spec, a spec version that is missing, or both missing: each is not current. Versions are compared for equality, never by time.
   - `_supersede` (already under `locked`) reads the cache version under the cache lock. It supersedes an open for-remote record when both versions are read and differ, with why `remote NAME's model moved from A to B since it was written`.
   - A version that can't be read supersedes nothing, but the record is listed as *not current* with the reason.
6. **Same-id remakes (lesson-5).** A for-remote proposal has the id the local one would have (`_id(kind, scope|flow, subject)`).
   - **Local → for-remote.** When the stored record is local, whatever its status (accepted, dismissed and refused included), the remake records `superseded` (why: `its part is now remote NAME's: written as text for its owner`), then `made`. The folded record then has only `FIELDS`: no `status` decision, `by`, `decided`, `applied`, `dismissed_*`, `revisions`, `verdict` or `edit`. Every old key outside `FIELDS` is removed by the made event (a changeset remove, or the fold's equivalent; the folded `stored()` record must not carry the key with a value).
   - **For-remote → local.** The same happens the other way. The local record that `admit` makes has no `for_remote`, `text` or `evidence`.
   - **Same kind.** A for-remote record found again at the same remote version with the same text is left alone. A dismissed one is not written again.
   - **Under the lock.** `make()`'s `stored()` … `admit` … `save()` moves under `locked(p)`, so the for-remote → local remake is serialized with accept. The implementor confirms by grep that no caller of `make` already holds the lock.
7. **Never applied (lesson-8).** `_accept` refuses any record with `for_remote` first, before any other check, with `ProposalError("proposal ID is text for remote NAME's owner: it is never applied here; ergostat remote proposals NAME prints it")`. The refusal is there, not in the UI. Each path listed under "What exists" refuses, and leaves the YAML unchanged. `dismiss` works on a for-remote record.
8. **Sends nothing.** No code sends a for-remote proposal anywhere. Making one and listing one cause only the existing `client.get` GETs, none with a body, and none carries the text. SPEC says "never sent by ergostat: sending it is the owner's act" and nothing wider.
9. **CLI.** `ergostat remote proposals [NAME] [--json]` lists the open for-remote records (all remotes, or one) and the dismissed ones. Each shows id, remote, the version it was written against, current or not current (with why), and the text in full.
   - `--json` gives the same as a list of records.
   - An unknown NAME exits with rc 2 and names the remotes.
   - A remote whose version can't be read gets the line `remote NAME: its model's version can't be read, so nothing is written for it`.
   - Listing never writes: it takes no lock and runs no supersede.
   - `ergostat proposals` adds one line: `N written for remotes' owners: ergostat remote proposals`.
10. **Read-only fallback (lesson-7).** `goodmodel` gains `READ_WHAT = {"remote": ("proposals",)}`. `reads(args)` is true for topic `remote` only when `args.what` is in it and no acting flag is set. `revoke` joins `ACTS`. Every other `remote` subcommand (token, tokens, events, refresh, status) still refuses on a broken YAML. `test_every_flag_of_a_read_topic_is_called_acting_or_read_only` covers `READ_WHAT` topics too.
11. **Docs.** These are kept current with the change:
    - SPEC §4c gets a paragraph, "Proposals for its owner", stating 1 through 10 as built, including what is not made for-remote;
    - `docs/proposals/remote-systems.md` §6: "the fit it would give" is removed; the evidence is the points, window and series;
    - `docs/GAPS.md`: this item moves from *Left* to *Done*;
    - `docs/AGENT-GUIDE.md`: one line on reading `ergostat remote proposals`.
12. **Merge and suites.** origin/main is merged in. Branches leased in the same area are likely to conflict in `compose.py` and `cli/remote.py`: remote-of-remotes, remote-box-measures and remote-items-record. After the merge, the unit suite, the four browser files and ruff are run again, all green.

## Files to touch

- `ergostat/numbers/remote_text.py` (new): `owner_of(spec, refs)`, `lookup`, `text_of(spec, x)` returning a record or a refusal, `FIELDS`, `record`, `current`, `listing`
- `ergostat/numbers/proposals.py`: the split in `make` and its lock, the cross-kind remake in `admit`/`save`, the exclusion in `pending`, the for-remote branch of `_supersede`, the refusal in `_accept`
- `ergostat/remote/cache.py`: `locked(d)`, used in `refresh`, and `version(d)` (returns None when it can't be read)
- `ergostat/remote/compose.py`: `info["names"]`
- `ergostat/cli/remote.py`: the `proposals` subcommand
- `ergostat/cli/numbers.py`: the one line in `ergostat proposals`
- `ergostat/goodmodel.py`: `READ_WHAT`, `reads`, `revoke` in `ACTS`
- `tests/test_remote_proposals.py` (new); `tests/test_cli_fallback.py`
- `docs/SPEC.md`, `docs/proposals/remote-systems.md`, `docs/GAPS.md`, `docs/AGENT-GUIDE.md`

## Risks

- **lesson-1.** Three read-decide-write paths need the lock held across the read, the compare and the write:
  - recording: the cache version is read, compared with the spec's, and the record is written;
  - superseding: the version is read, the record is superseded;
  - the cross-kind remake and accept: both read `stored()`, decide, and write events.

  Without both locks, a refresh lands a new version between the read and the append, or a remake writes a for-remote record that accept's `save` then marks accepted. `make()`'s unlocked `stored`/`save` is the existing gap the remake would fall through, so it moves under the lock.
- **lesson-3.**
  - When recording: the version is missing in the spec or the cache file, or the file is bad.
  - When checking currency: `None == None` would count as current.
  - When looking up names: a missed lookup falling back to the local `incidents-x` name, or a stand-in treated as served.

  Each one refuses, or counts as not current.
- **lesson-5.** The fold merges fields under a reused id: a remade for-remote record could inherit `status: accepted`, `by` or `applied`, and a local record remade from a for-remote one could inherit `for_remote` and its version.
- **lesson-8.**
  - "Never applied" could be true only of the button: there are five paths into `accept`.
  - "Sends nothing" could be untested.
  - "No fit" could hold for the text but not the record.

  An allowlist of fields, not a denylist.
- **lesson-7.** A new `remote proposals` subcommand left unclassified for the fallback, or classified at the topic level so that `remote token` would run on the last good model. There are also merge conflicts with the leased remote-* branches in `compose.py` and `cli/remote.py`.
- **lesson-9.** The race tests must put the competing write inside the window, by monkeypatching the step between. The currency test must include the both-missing case.
- **lesson-13.** Failures outside these files are reported, not fixed here.

## Acceptance tests

All are in `tests/test_remote_proposals.py` unless named otherwise. They use the `served_into`-style cached remote from `tests/test_remote.py`, with mirrored readings written to the series store. For each test, the report says which code was broken and that the test then failed.

1. `test_an_estimate_of_a_remote_parameter_is_written_as_text_for_its_owner`: `make()` on a remote parameter with `estimate: true` and readings. Shows:
   - one record whose `for_remote` is `{"remote": "incidents", "version": <served version>, "parts": {"parameter.incidents-rate": "parameter.rate", …}}`;
   - its text names `parameter.rate`, never `incidents-rate`, and gives the value from → to ±;
   - it is absent from `pending()` and from `inbox.entries`.
2. `test_an_equation_for_a_remote_flow_is_written_in_the_remotes_names`: every ref in the text is in the remote's served model, the new parameter names are built from the remote names, and no `incidents-` name appears.
3. `test_a_for_remote_record_stores_no_fit_field`: the `made` event's data keys are a subset of `FIELDS`. The `stored()` record has none of the fit or edit keys of point 3 with a value. The text has no `R²`, `%` of variation, `fit` or `error`. (Fails if `fit_before` is copied over.)
4. `test_a_proposal_of_local_and_remote_parts_or_two_remotes_is_not_written_for_remote`: such a proposal keeps its `edit.error` and gets no `for_remote`, and accept refuses it as before.
5. `test_recording_refuses_when_the_remotes_version_cannot_be_read`: four cases record no event for the id: the remote never read (spec version None); `model.json` removed after the find; `model.json` without a `version`; and spec and file versions that differ.
6. `test_a_name_lookup_miss_refuses_and_never_uses_the_local_name`: one part is dropped from `info["names"], and separately a stand-in ref is used. No record is made, and no event's text contains `incidents-`.
7. `test_current_needs_both_versions_read_and_equal`: `current` is false for record None, spec None, both None, remote absent, and versions differing. It is true only for equal strings. (Fails with a plain `==`.)
8. `test_a_moved_remote_version_supersedes_and_an_unreadable_one_only_marks_not_current`: the cache version moves, so `supersede` marks the record superseded with both versions in why. With the file removed, the record is not superseded and is listed as not current with the reason.
9. `test_recording_holds_both_locks_across_read_compare_write`: the step after the version read (`remote_text`'s compare) is monkeypatched to start a thread running `cache.refresh` with a fake `client.get` serving version B. At the moment the event is appended (`p.events.add` wrapped), `model.json` still says A and the thread is still blocked. After the join, the record is not current. (Fails without the cache lock in `record` or in `refresh`.)
10. `test_superseding_a_for_remote_record_holds_both_locks`: the same thread is started between `_supersede`'s version read and its event. The superseded event's `version_now` equals the file's version at the moment it is written.
11. `test_an_accept_racing_a_remake_as_for_remote_under_the_same_id`: a local pending proposal with id I. Inside `_accept`'s window (`ft.compute` monkeypatched) a thread runs `remote_text.record` for the same id I, the same proposal turned for-remote because its part is now remote. Shows:
    - the thread does not write until accept's `save` and `written` are done;
    - afterwards the folded I is for-remote, with no `status: accepted`, `by`, `decided`, `applied` or `edit`;
    - the model's history (`accepted(p)`) still has the accept.

    (Fails without `locked` in `record`.)
12. `test_a_local_accepted_proposal_remade_as_for_remote_keeps_no_decision`: the same for dismissed (no `dismissed_because`) and refused.
13. `test_a_for_remote_proposal_remade_as_local_loses_for_remote_and_its_version`: the remake goes through `make()`, which is also run under the lock: a racing `record` in `admit`'s window is blocked until `save`.
14. `test_cli_accept_refuses_a_for_remote_proposal`: rc ≠ 0, the message names the remote, and the YAML is byte for byte unchanged.
15. `test_the_web_accept_endpoint_refuses_a_for_remote_proposal`: a POST to `proposals/ID/accept` answers 409 and the YAML is unchanged; dismiss answers 200.
16. `test_the_judges_auto_accept_never_applies_a_for_remote_proposal`: policy `accept: auto` with the record's state forced to `passed`. The judge's pass leaves it unaccepted, and a direct `pr.accept` raises.
17. `test_the_inbox_answer_refuses_a_for_remote_proposal`: `answer` with approve raises `AnswerError` with the refusal.
18. `test_the_bench_adapter_accept_refuses_a_for_remote_proposal`
19. `test_ergostat_sends_nothing_for_a_for_remote_proposal`: `urllib.request.urlopen` is recorded, the cache is made due, then `make()` and `ergostat remote proposals` are run. Every request is a GET, with no data, under `/remote/v1/`, and none contains the text.
20. `test_remote_proposals_lists_text_and_json`: text and `--json` output, the NAME filter, rc 2 on an unknown NAME, the line for an unreadable version, and the line in `ergostat proposals`. Listing writes no event, and no lock file is created.
21. `tests/test_cli_fallback.py::test_remote_proposals_reads_on_the_last_good_model_and_remote_token_does_not`: with a broken YAML and a kept snapshot, `remote proposals --json` exits 0 with the records. `remote token x`, `remote refresh` and `remote proposals --revoke` refuse with the "acts" message.
22. `tests/test_cli_fallback.py::test_every_flag_of_a_read_topic_is_called_acting_or_read_only`: extended to the `READ_WHAT` topics.
23. `test_a_dismissed_for_remote_proposal_is_not_written_again_at_the_same_remote_version`

Risk to test: lesson-1 → 9, 10, 11, 13; lesson-3 → 5, 6, 7, 8; lesson-5 → 11, 12, 13, 23; lesson-8 → 3, 14–19; lesson-7 → 21, 22, plus the suites run again after the merge; lesson-9 → the break-and-fail check in the report for each test.

## Size budget

400 net lines of code outside `tests/` and `docs/`: `remote_text.py` about 220, `proposals.py` about 60, `cache.py` about 25, `compose.py` about 5, `cli/remote.py` and `cli/numbers.py` about 70, `goodmodel.py` about 10.

## Notes from the plan review (answer each)

- Lock re-entrance: make() holds locked(p) across stored..admit..save and record() also takes locked(p); state how record is reached from make (outside make's locked region, or a lock-held variant) so the same process doesn't deadlock on a second fd, and confirm the lock is a per-fd flock (not POSIX lockf) so threads in one process block each other; otherwise tests 9, 10, 11 and 13 cannot fail.
- Tests 9/10 determinism: before the append, the monkeypatched step must wait until the refresh thread has reached the cache-lock acquire (signal or join(timeout) then is_alive), so 'still blocked' and 'model.json still says A' would fail without the lock rather than pass because the thread had not yet run.
- Lesson-5 at a new version: a superseded or dismissed for-remote record re-found at version B under the same id must fold to open with no old status/why/dismissed_* fields (or state that dismissed stays dismissed across versions); add a test.
- A lookup miss records nothing: state what happens to an existing local edit.error record under that id (left pending or superseded), and test it.
- FIELDS has no state/status/id, yet the record is 'checked' and test 3 requires made-event keys to be a subset of FIELDS: add state to FIELDS or state that the fold derives it.
- Same kind, same version, different text: say whether it is remade (all FIELDS overwritten) and whether a dismissed one stays dismissed.
- Lesson-11: the remote NAME used to build <state>/remotes/NAME/model.lock must be validated against ^[a-z0-9][a-z0-9-]{0,63}$ and the resolved path confirmed under <state>/remotes.
- Test 16 is satisfied by the pending() exclusion alone; also drive the judge's accept step directly on the record so the _accept refusal is what is exercised.

## Where it stopped

Round 1 is built: points 1 to 11, every acceptance test (1 to 23, plus five more listed below), and 380 net lines of
code outside tests and docs (budget 400). Point 12 is only partly done: this clone has no `origin`. Local `main` is
this branch's base (9c9140ec), so there was nothing to merge here. The queue must merge origin/main and run the suites
again. Expect conflicts in `compose.py` and `cli/remote.py` with remote-of-remotes, remote-box-measures and
remote-items-record.

**Not run here:** the four browser files and the whole unit suite (the factory runs them after this). Run here, one
file at a time: tests/test_remote_proposals.py (30 passed), test_cli_fallback.py (18), test_remote.py (12),
test_numbers.py (55), test_churn.py (7), test_review.py (22), test_inbox.py (17), test_improve.py (28),
test_bench.py (17) and test_remote_pair.py (1). ruff is clean. No example was touched, so demo_check does not apply.

**What exists that the definition got wrong.** `make()` already held `locked(p)` across `stored()` … `admit` …
`save()` on main (proposals.py, the `with locked(p)` before `current_now`). The text is now recorded inside that same
region. The only callers of `make` are `cli/numbers.py:143` and `web/numbers_api.py:752`, and neither holds the lock
(checked by grep).

**Answers to the plan review**
- *Lock re-entrance.* `make` calls `remote_text._record`, which assumes the proposals' lock is held, inside its own
  locked region. `record` takes the lock itself, for every other caller. Both locks are `fcntl.flock` on a fresh
  `open()` each time. Such a lock belongs to the open file description, so two threads of one process block each
  other. Tests 9, 10, 11 and 13 were each seen to fail with the lock taken away.
- *Tests 9/10 determinism.* The patched step starts the refresh thread, then `join(0.5)`, then checks `is_alive()`.
  The fake `client.get` answers at once, so without the lock the thread is done inside that window, and the test
  fails (seen).
- *Lesson-5 at a new version.* A dismissed text at version A that is found at version B is made again: open, with no
  `dismissed_*`, `decided` or `why` (test 23). A superseded one is out of `stored()` and is made again the same way.
- *A lookup miss.* Nothing is written. What is under the id is left exactly as it was: a local `edit.error` record
  stays pending, as on main (test 6). A version refusal leaves it the same way.
- *FIELDS and state.* The fold works out the state (`checked`) from the `made` and `checked` events. On a new record,
  the made event's keys are a subset of `FIELDS` (test 3). When a record is made again, the made event also sets each
  old key outside `FIELDS` to None, which is how `save` clears them on main.
- *Same kind, same version, other text.* It is made again: one made event that overwrites every field in `FIELDS`,
  then checked (test `..._found_again_with_another_text_is_remade`). A dismissed one stays dismissed at the same
  version, whatever its text.
- *Lesson-11.* `remote_text.folder` checks the name against `^[a-z0-9][a-z0-9-]{0,63}$`. It also checks that the
  resolved path is directly under `<state>/remotes` and equal to the `dir` that compose recorded. Otherwise nothing
  is locked or written (test `test_a_bad_remote_name_never_builds_a_lock_path`).
- *Test 16.* It also calls `pr.accept(..., policy=...)` on the record, as the judge's accept step does, and that
  raises the refusal.

**Choices made alone (each the more reversible one)**
- `make`'s "no longer found" pass never lets a text go. Texts carry no calibration scope (the `FIELDS` allowlist), so
  they are superseded only when the remote's version moves, or made again.
- The refresh holds `model.lock` from reading `have` to writing `model.json`, as point 4 says. That includes the GET,
  which is bounded by its 3 s timeout.
- The text says "± one standard error of the estimate", as point 3 asks. So test 3 checks for "error" only after
  removing "standard error".
- Made again from a local record: superseded, then made, then checked. Made again from an older text: made, then
  checked (no superseded).
- `ergostat remote proposals --revoke` exits with rc 2. On the last good model it is refused as an act.

**Break-and-fail (lesson-9).** Each guard below was broken, the tests named after it failed, and then the code was put
back:
- the cache lock in `_record`: test 9;
- the lock in `refresh`: tests 9 and 10;
- the cache lock in `moved`: test 10;
- `pr.locked` in `record`: tests 11 and 13;
- `make`'s lock: test 13;
- `_same` as a plain `==`: test 7;
- the `pending()` exclusion: tests 1 and 17;
- the `_accept` refusal: tests 14 to 18;
- clearing the old keys: tests 11, 12 and 23;
- a lookup that falls back to the local name: test 6;
- the version check in `_record`: test 5, all four cases (the change is made at the step just before the record's
  lock);
- the dismissed check: test 23;
- an empty `READ_WHAT`: test 21;
- a fit field copied into the record: test 3;
- a GET that carries the text: test 19 (it decodes the URL before searching it);
- the new names not made free against the remote's: test 2 and the names test.

Tests added beyond the 23 named: equation names built from the remote's names, a text found again with another text,
the bad-name lock path, a local record remade from a text folding without `for_remote`, and the four cases of test 5,
each one its own parametrised test.
