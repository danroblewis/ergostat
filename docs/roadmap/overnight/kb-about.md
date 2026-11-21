# kb-about: an item can say which parts of the model it is about, and explain, check and status point at it
depends-on: []

## Definition of done
- An item kind may declare a field that names parts of the model (`goal.x`, `stock.x`, `flow.x`, `auxiliary.x`,
  `block.x`). The names use the text form claims already use for `about`. This is opt-in per kind and ergostat
  declares no kind of its own (invariant 12). A model where no kind declares the field does no lookup.
- The item index keeps these item→part links with its other links. "Items about goal.x" is one indexed lookup, not a
  scan of every item. Folding works like a relation field: an event that sets `about` to a new list replaces the old
  one, so a part dropped from an item, or an item made again under the same id, no longer points at that part.
- `ergostat explain <part>` (CLI and MCP), when given a project, ends with a line listing the open (not finished)
  items about that part: id, then title or first field, at most 5 with "and N more". Finished items (e.g. a
  `retired` knowledge entry) are not listed. If the index can't be read, it says the knowledge is unknown, not "none".
- A `check` finding whose `about` is a part that has open items about it carries their ids. An item that names a part
  not in the model is itself a finding (`about-missing-part`), never dropped silently.
- `ergostat status`: a loop that is off (the attention line or the loop row) lists the ids of open items about its
  goal or its measured value, at most 3 with "+N".
- The factory: each entry in `dev/knowledge/` may have an *About:* line naming parts of the root model.
  `knowledge.py sync` puts these names on the `knowledge/<id>` item, and the kind in `ergostat.yaml` declares the
  field. At least the lessons about the pipeline name the goals they bear on.
- SPEC §5a and §12 (findings), `docs/AGENT-GUIDE.md` and `dev/knowledge/README.md` say all of this.

## Files to touch
ergostat/spec/ir.py, ergostat/spec/compile.py (the kind's declaration), ergostat/spec/itemindex.py,
ergostat/spec/explain.py, ergostat/spec/findings.py, ergostat/cli/status.py, ergostat/mcp.py (only if explain needs
the project passed), dev/bin/knowledge.py, dev/knowledge/*.md, ergostat.yaml, docs/SPEC.md, docs/AGENT-GUIDE.md,
dev/knowledge/README.md, tests/test_item_about.py, tests/test_factory_knowledge.py

## Risks
- lesson-5: an item remade under the same id, or with `about` changed, keeps pointing at its old part.
- lesson-3: an unreadable index, or a name for a missing part, reads as "no knowledge" or is dropped.
- lesson-8: the docs promise "every item about it is shown" but the output is capped or finished items are filtered.

## Acceptance tests
- `tests/test_item_about.py::test_explain_lists_open_items_about_a_goal`: two open items about `goal.a`, one retired
  one, and one about `stock.b`. explain of `goal.a` lists exactly the two open ones. Six items show 5 and "and 1 more".
- `tests/test_item_about.py::test_about_replaced_not_merged_on_remake`: an item moved from `goal.a` to `goal.b`, and
  an item retired then found again under the same id with a new `about`, each appear only under their current part.
  Fails if the field folds as add (lesson-5).
- `tests/test_item_about.py::test_lookup_is_indexed_not_a_scan`: with 5,000 unrelated items, the lookup reads only the
  link rows (patch the fold read and assert it is not called per item).
- `tests/test_item_about.py::test_unreadable_index_says_unknown`: a corrupt index file makes explain say the knowledge
  is unknown, not "none" (lesson-3).
- `tests/test_item_about.py::test_missing_part_is_a_finding_and_findings_carry_ids`: `about: goal.gone` gives
  `about-missing-part`. A `missing-feedback` finding on `goal.a` carries the ids of items about it.
- `tests/test_item_about.py::test_status_off_loop_points_at_knowledge`: an off loop's status line shows its item ids
  (at most 3, "+N"). A loop that holds shows none.
- `tests/test_factory_knowledge.py::test_sync_carries_about`: an *About:* line reaches the item. Removing it clears
  the field on the next sync.

## Size budget
220 net lines (outside tests/, docs/, dev/).

## Notes from the plan review (answer each)

- Index schema migration (lesson-3): an index built before this change has no item->part links, so lookups would wrongly say 'none'. Bump the index version or rebuild, and add a test that an old index does not report 'none'.
- Unreadable index in check and status (lesson-3): both must report the knowledge as unknown, not as no items, and check must not quietly skip about-missing-part. Test both.
- Malformed or unknown-prefix names (e.g. 'foo.x', 'goal.') and a missing block.x must also give about-missing-part. Add cases to test_missing_part_is_a_finding_and_findings_carry_ids.
- test_lookup_is_indexed_not_a_scan can pass on a scan that reads raw events without the fold. Count every item event/row read, and report that the test failed against a deliberate scan (lesson-9).
- 'A model where no kind declares the field does no lookup' has no test. Add one that patches the index read and asserts it is not called.
- MCP explain with a project is not tested. Add a test that it lists the same items as the CLI.
- Status test: cover an item about the loop's measured value (not only its goal) and both the attention line and the loop row.
- Docs (SPEC section 5a/section 12, AGENT-GUIDE, knowledge README) must state the caps (5 / 3) and that only open items are listed; no 'every item' wording (lesson-8).
- knowledge.py sync with an About: line naming a missing part must surface as a finding. Cover it in test_factory_knowledge.py.

## Where it stopped

Built, round 1: everything in the definition of done. 190 net lines outside tests/, docs/ and dev/ (budget 220).

Decisions taken alone (the most reversible option each time):
- The kind's key is `about: FIELD` (the name of the field holding the parts). It must fold by `replace`; any other
  `fold:` for it, or a relation's name, is the error `bad-about`. Also added to `schema/ergostat.schema.json`.
- The links are rows of the existing `links` table under the relation `@about` (never a relation's name). The links
  to items (`links_from`, `links_to`) leave them out, so precedence, joins and an item's page are unchanged.
- Only **open** items are checked for `about-missing-part`: a retired entry naming a goal since removed is not a
  finding. One finding per missing name, with the ids of the items that hold it.
- A corrupt index file is still healed from the record (as before), so explain answers correctly then. "unknown" is
  said when the index cannot be read even so (healing fails, the record cannot be read). Tests cover both.
- `knowledge.py sync`: an entry found again after it was retired without an *About:* line gets `about: []`, so the
  item does not keep its old parts (lesson-5).

Answers to the plan review's notes:
- Index migration: `VERSION` is 4 (and part of the file's hash, with each kind's `about`). An index of layout 3 is
  folded again: `test_an_index_built_before_the_about_links_is_rebuilt` (fails with VERSION left at 3: checked).
- Unreadable index in check and status: `test_unreadable_index_says_unknown` (explain, and check gives only
  `about-unknown`, no missing-part verdict) and `test_status_with_an_unreadable_index_says_unknown`.
- Malformed names: `foo.x`, `goal.`, `block.nowhere`, `stock.a.main` and `goal.gone` are each
  `about-missing-part` in `test_missing_part_is_a_finding_and_findings_carry_ids`.
- The lookup test counts `Index._item` rows and every raw-event read (`of_items`, `query`, ...), and fails on a fold.
  Run against two deliberate scans: one over the index's items (5002 rows read, failed) and one over the raw events
  with no fold (5001 events read, failed).
- No declaring kind, no lookup: `test_no_kind_declares_about_no_lookup` (index_for and Index.about patched to fail).
- MCP explain: `test_mcp_explain_lists_the_same_items_as_the_cli`.
- Status: an item about the measured value (`stock.a`) is listed; the attention line, the loop row and `--json` are
  checked; a holding loop names none.
- Docs state the caps (5, 3) and "open items only"; no "every item" wording.
- Sync with a missing part: `test_sync_carries_about` folds the synced item into a copy of the root model's record,
  and `check` gives `about-missing-part` for `goal.gone`. `test_every_about_line_names_a_part_of_the_root_model`
  holds the real *About:* lines to the root model.

Mutations run (lesson-9), each failed the test named and was reverted: links not deleted on refold
(`test_about_replaced_not_merged_on_remake`); the lookup made a scan, twice (`test_lookup_is_indexed_not_a_scan`); the
lookup failing open to `{}` (both unknown tests); VERSION left at 3; found-again without clearing `about`
(`test_sync_carries_about`).

Not run here: the whole unit suite and the browser files (the factory runs them after). This clone has no
origin/main to merge; main is already contained in the branch.

After the factory's `unit` suite failed: its tail held only uv's build lines and no pytest output at all (no worker
start-up, no failure, no watchdog JSON line), so no test was named. Run here again, one batch of files at a time,
serially (`-p no:randomly -x`): every unit file outside the four browser files passed, 1,935 passed, 68 skipped, 0
failed (a-c 426, d-g 284, i-m 371, n-r 428, s 289, t-z 137). The files this branch touches also pass with two xdist
workers in random order (104 passed), and the new tests write only under `tmp_path` (`ERGOSTAT_HOME` set per test;
`git status` clean after the runs). No code changed: no failure was found to fix. The whole suite at `-n 8` was not
run here (the rules forbid it). If the next run fails again, its full output, not the tail, is needed to name the test.

After the factory's second `unit` run failed, on `tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere`
(`['expired', 'ack']`, not `['ack']`): this is not caused by this branch, so no code is changed (lesson-13).
- The branch changes nothing on that test's path. Nothing under `ergostat/leases/`, `ergostat/store.py`, the `event`
  command or the engine is touched. The new import of `spec/about.py` in `itemindex.py` brings in only
  `spec/load.py`, which `ergostat/spec/__init__.py` already imports, so every `ergostat event --add` starts no slower.
  The index's VERSION bump rebuilds an index once, and that test's record is new, so nothing is rebuilt there.
- Why it fails: the lease has a TTL of 1 s, and the watchdog's grace is at least 1 s (`leases/terms.py` `grace`). It
  expires only when the run says nothing for about 2 s. The run starts a fresh Python `ergostat event` process for each
  event, and the first one starts right after the take. Under the suite at `-n 8` (290 threads, 118 processes at the
  peak), one start-up can take that long. Then the lease expires as designed, the item is taken again, and the second
  run acks. That is the "fixed time in the test, failing under load" case of lesson-10, not a race in ergostat. The
  watchdog and the fold give the same answer for the same silence.
- Run here alone with `-p no:randomly`: it passed (1 passed in 3.47 s).
- Left for a gap of its own, outside this one: give that test a TTL that covers a CLI start-up under load, or have
  the watchdog's first look wait for the run's first event. This branch does neither.

### Round 2 (after review/kb-about-1)

Main (8eb0fc06) merged in first. The conflicts in `dev/bin/agents.py`, `dev/bin/fac.py`, `dev/factory.toml` and
`ergostat.yaml` keep both sides: the groomer and `[backlog]` from the branch's history, and main's pipeline manager
(its timeout, tools, stand-in, model and session cap, and `situation: [handled, failed]` in `done`). `gap: [merged,
closed]` stays as the branch had it, because `parked` is in `paused` there and a status can't be both done and
paused. The comment on `gap.closed` now names both ways a gap is closed.

Each finding of that review, and what changed:
- **Blocking: the about findings ran in `find()`, so on every model load.** Fixed. `about.findings` is no longer
  called from `spec/findings.find`. It runs only where check's output is built: `cli/spec_cmds.check_yaml`, after
  calibration, `order_unset` and `late`, and MCP's `check` after its `read`. Both run it only when the model has no
  errors. A load (`mdl.load`, `spec.read`, so every CLI command, the engine, coherence and a proposal's trial) never
  opens the item index for it now, and an unreadable index adds `about-unknown` only to check.
  `test_loading_the_model_looks_nothing_up` patches `itemindex.index_for` and `about.open_about` to fail, then loads
  and reads a model that declares `about:` and whose record holds an item naming `goal.gone`. When `about.findings`
  was put back in `find()`, it failed (checked).
- **The claim in round 1's notes is withdrawn.** "Every `ergostat event --add` starts no slower" was false for a
  model that declares `about:`, because the load caught up the index. It is true now: the lookup moved out of the
  load. It was always true of `test_leases.py`'s own models, which declare no `about:`.
- **SPEC §12, "Any finding about a part ... carries their ids".** Narrowed, and now backed by a test. It says a
  finding of `check` (CLI or MCP), with the calibration and extreme-conditions findings, because the ids are added
  last. The coherence report is apart and does not carry them. It also says that these findings are check's alone.
  `test_missing_part_is_a_finding_and_findings_carry_ids` now goes through `ergostat check --json` and MCP's `check`,
  not `read()`. It patches `late` to add a finding about `goal.quiet` and asserts that the finding carries
  `knowledge/fb`. With `about.findings` called before `late`, it failed (`KeyError: 'items'`, checked). With the
  call taken out of `check_yaml`, it failed (checked).
- **`test_sync_carries_about` had an assertion that could not fail** (`... or not [...]`). It is gone. The test now
  also asserts that `read()` alone gives no `about-*` finding, and then applies `about.findings` as check does.
- **Scope, lesson-7: the branch's history holds the backlog merge (2b101c6), which main does not.** Not fixed here,
  and it is the one finding of that review left open. Taking it out means rewriting the branch's history (a rebase
  or a reset), which this session can't do and which is not reversible. The size below is split so that the gap's
  own lines can be judged apart from it. Measured against main (8eb0fc06), outside tests/, docs/ and dev/:
  - The gap's own lines: about 198 net, within the budget of 220. `spec/about.py` 125, `spec/itemindex.py` 19,
    `cli/status.py` 23, `spec/compile.py` 10 (its `about` key), `spec/explain.py` 5, `spec/ir.py` 4, `mcp.py` 4,
    `cli/spec_cmds.py` 3, `schema/ergostat.schema.json` 4, `spec/load.py` 1, `spec/findings.py` 0.
  - The backlog's lines: the other ~135 of the 333 the diff shows (`leases/compile.py`, `dispatch.py`, `ready.py`,
    `numbers/eta.py`, `etamodel.py`, `precedence.py`, `web/static/*`, `order_unset` in `spec_cmds.py`, `paused` in
    `compile.py`).
  - The fix for this is to land backlog on main first, or to rebuild this branch from main without it. Either is
    the coordinator's call.

Tests run, each file alone, serially: `tests/test_item_about.py` 14 passed, `tests/test_factory_knowledge.py` 24
passed. The files that use `check` and MCP's `check` are listed in the report. Ruff is clean. Not run: the whole unit
suite and the browser files (the factory runs them).

After the factory's `unit` run failed on
`tests/test_relations_asof.py::test_an_item_of_no_kind_changed_since_has_no_links_and_the_rest_answers` (both
modes, `'unblocked' == 'ready'`): this comes from the merge, not from kb-about. The backlog merge (2b101c6, still
in this branch's history) renamed the precedence status *ready* to *unblocked* in `ergostat/precedence.py` and
in `tests/test_relations.py`'s assertions. Main's relations-as-of added this test later, using main's word. Keeping
both sides means carrying backlog's rename into the new test, so its two expected statuses now say `unblocked`,
as backlog did for `test_relations.py`. No bound changed, and the test checks the same thing. The code is not
renamed back, because that would break backlog's tests and its Items-tab legend. If backlog is instead taken out
of this branch (the open scope finding above), this test edit goes with it. Run alone: `test_relations_asof.py`
9 passed, `test_relations.py` + `test_item_about.py` 32 passed, ruff clean.

After the factory's third `unit` run failed, on `tests/test_warm.py::test_the_owners_stop_is_said_only_on_the_run_it_stopped`
(the stopped run's replacement process had not written `starts.log` within 5 s): this branch did not cause it, so
no code is changed (lesson-13). Changing code outside the gap is what failed continue-branch's review.
- Nothing on its path is touched. `git diff main HEAD` is empty for `ergostat/daemons/`, `ergostat/costs/`,
  `ergostat/spec/engine.py`, `ergostat/runner.py`, `tests/test_warm.py`, `tests/test_daemons.py` and
  `tests/test_leases.py`. The test's kind declares no `about:`, so the new index code (`k.about` is None) runs
  exactly as before. The only dispatch change the branch carries is backlog's `ordered`, a sort that leaves the
  items as they are when there is no `order:`.
- The path, read through: cancel, then the `done` line, then `charge` sets `recycle`, then the next tick (0.2 s)
  runs `_recycle`, then the next tick spawns. A process marked for recycling is never handed a run (`_room`
  checks `not p.recycle`), so nothing can hold the slot. Nothing here waits on the record or the index. The 5 s
  go on starting a fresh `python3` under the suite at `-n 8` (315 threads, 119 processes at the peak): lesson-10's
  "fixed time in the test" case, not a race found in ergostat.
- Run here alone with `-p no:randomly`: that test passed, and all of `tests/test_warm.py` passed (21 in 24.8 s).
- Left for a gap of its own: give the replacement a bound that covers a start-up under load, or wait on
  `ergostat.daemon.started` rather than on the process's first write.

### Round 3: the size gate

The queue's gate found "333 net lines against 220, with no reason written". The round-2 split was written, but
not as a reason for going over, so the gate did not see it. No code changes in this round. The find() finding of
review/kb-about-1 was already fixed in round 2 (`spec/findings.py:100` returns before any about lookup.
`about.findings` is called only from `cli/spec_cmds.check_yaml` and MCP's `check`).

**Size overrun, the reason:** the branch goes over the budget only because its base holds the backlog merge
(2b101c6), which main does not. The gap's own code stays within 220. Measured now with `git diff --numstat
main...HEAD` outside tests/, docs/, dev/ and ergostat.yaml, the total is +378/-45 = 333 net.
- Files only backlog changes: 117 net. `leases/compile.py` 8, `leases/dispatch.py` 1, `leases/ready.py` 23,
  `numbers/eta.py` 16, `numbers/etamodel.py` 45, `precedence.py` 4, `web/static/pages.js` 12, `relations.js` 4,
  `style.css` 4.
- Shared files, backlog's part: `order_unset` in `cli/spec_cmds.py` (21 of its 24) and `paused` in
  `spec/compile.py`.
- The gap's own lines: about 195-198 net. `spec/about.py` 125, `spec/itemindex.py` 19, `cli/status.py` 23,
  `spec/compile.py` (its `about` key), `spec/explain.py` 5, `spec/ir.py` 4, `mcp.py` 4, `cli/spec_cmds.py` 3,
  `schema/ergostat.schema.json` 4, `spec/load.py` 1, `spec/findings.py` 0.

The base is still not fixed, and this session did not fix it on purpose:
- A reset or rebase rewrites the branch's history. That is not reversible from where the factory sees the branch.
- A `git revert -m 1` of the backlog merge would be worse. Once merged, it would make main treat backlog's commits
  as already in, and backlog would be dropped without a word when it lands later.

What reverses cleanly is one of these, and either is the coordinator's call:
- land backlog on main first, so these 117+ lines leave the diff and the `test_relations_asof.py` word change
  becomes main's own;
- or rebuild this branch from main and cherry-pick the gap's commits (then the `unblocked` edit in
  `tests/test_relations_asof.py`, e7dad319, is dropped, as review/gap-size-3 says it must be on a correct base).

After the factory's fourth `unit` run failed: its output stops at 46% with no failure, no pytest summary and no
`suite_watch` JSON line. `suite_watch.py` prints that line on every way out it handles, its own kills included
(past the limits, a worker past its memory, interrupted). So the whole process group was stopped from outside
(`fac.suite` kills the group with SIGTERM when its caller stops, and the container can end), not by a test failing.
No test is named, so there is nothing to fix, and no code is changed (lesson-13). This is the same as the first
failed run above.
- Checked again here: `tests/test_item_about.py` and `tests/test_factory_knowledge.py`, serially, 38 passed in 63 s.
  The slowest test is `test_brief_carries_knowledge_within_budget` (34-44 s). It runs against the fixture's fake
  ergostat (`FAKE_MORE`), so none of the branch's `ergostat/` code is on its path. Its only change from main on that
  path is the *About:* regex in `knowledge.entries()`, one search per entry. It could not be timed on main here (a
  second worktree was refused).
- Read through again for a hang that would only show under xdist: the new index code takes no lock of its own and
  waits on nothing. `Index.about` is one SELECT. `off_about` and `explain_line` look things up only when a kind
  declares `about:`.
- If the next run fails like this, the cause of the stop is needed (the implementor's log, or the container's exit),
  and so is the output past 46%.

## Where it stopped

Parked by the factory (review/kb-about-2, 2026-11-20 18:39).

Done: the kb-about gap itself. The `about:` kind field (compile.py, ir.py, schema); @about links in the item index (VERSION 4, folded by replace, a remake clears them); spec/about.py with explain's line (5, 'and N more', 'unknown' on an unreadable index), check's ids and about-missing-part / about-unknown (run only in check_yaml and MCP check, after `late`), and status's off-loop ids (3, '+N'); knowledge.py *About:* lines synced and cleared; ergostat.yaml's knowledge kind declares it; SPEC §5a/§12, AGENT-GUIDE and knowledge README updated; acceptance tests and every plan-review note covered. Round 1's findings (lookup on every load, the assertion that couldn't fail, §12 wording) are fixed. Left: the branch is built on a base that contains the unmerged backlog merge 2b101c6, so landing it ships backlog too, and e7dad319 edits main's test_relations_asof.py for backlog's rename. The implementor can't rewrite history, so another fix round would not change this. To continue: either land backlog on main first (then e7dad319 becomes main's own and the diff shrinks to the gap's own lines), or rebuild factory/kb-about from origin/main and cherry-pick 183aaa15, 402a6936, b2f2a69f, 615f1a62, f2ed8964 and the Where-it-stopped commits. Leave out e7dad319, drop any backlog hunks that come with them (e.g. ergostat.yaml's gap kind, `paused` in compile.py/ir.py, order_unset in spec_cmds.py), then run the two acceptance files, the unit suite and the four browser files.
