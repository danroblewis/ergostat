# risk-score-from-history: Each change gets a risk score learned from what failed before

Score a change from its history: paths touched and their failure rates, size, author block, gap kind, conflicts. Validate on past batches (did high scores fail more?). The score is a general item measure a model can use to route checks (error-budget-sets-check-level, merge-lanes-in-parallel).
Done: 1. A backtest on the factory record shows calibration (failure rate by score band). 2. The score is on each item and queryable.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.

## Where it stopped

Round 1, 2026-11-24. Built, within the 600-line budget: about 360 net lines outside tests/, docs/ and dev/. The new
module `ergostat/numbers/itemrisk.py` is 264 of them. The rest is `spec/compile.py`, `cli/record.py`, the schema and a
few lines elsewhere. The definition names no acceptance tests and no budget, so I took the house budget (600) and named
the tests below.

What was built:
- **The core option.** A kind declares `risk-score: {at, failed, passed, from, least}`, and nothing runs without it.
  The parts:
  - **Attempts.** An attempt opens each time an item enters `at`, with its `from` fields as they stand then. It fails at
    the first `failed` event, including one after it passed (a revert), and passes on entering a `passed` state.
  - **Order.** The kind's events are replayed by `seq`, so each attempt is scored only from those judged before it.
  - **The score.** Naive Bayes over the fields, each read as `value`, `each` (a list: the riskiest element counts) or
    `size` (bands of powers of two). It is calibrated by Platt scaling fitted to the earlier judged attempts.
  - **What it refuses to assume.** A missing value is learned as `(none)`, never read as safe. Under `least` judged
    attempts there is no score, never 0.
  - **Where it is checked.** Compile refuses a bad declaration (`bad-risk-score`). Library trust refuses the key from
    untrusted templates. The JSON schema lists it.
  - **The kept replay.** It is kept in memory per record and caught up from its last seq, under one lock held across
    the read, the catch-up and the answer (lesson 1). It starts again from nothing when the record is made again at
    the same place: the last event it read is gone, or the record's last seq is behind it (lesson 5).
- **Queryable.** Through three ways in:
  - an item's detail carries `risk_score` (`ergostat item ID --json`, the API and MCP);
  - `ergostat item --kind K --risk-score [--json]` lists every item, highest first, with the fields that moved it;
  - `--backtest` gives the calibration table, the Brier score beside the base rate's, and the AUC.
  - Both new flags are classified as reads for the last-good-model fallback (`goodmodel.READ_FLAGS`, lesson 7).
- **The factory as first user.** `ergostat.yaml` declares it on `gap`:
  - at `approved`; failed by `gap.queue-failed` or `gap.reverted`; passed at `merged`;
  - learning from `paths` (each), `net_lines` (size), `source` (the gap's kind: gaps, request, plan, groom,
    simplifier), `built_by` (the author block), `conflicts` (size) and `failed_gates` (size).
  - Three of those fields are new, recorded from now on:
    - `paths`: implement.py's `gap.built` carries the files the branch changed against its base, the gaps' records
      left out, at most 200;
    - `built_by`: `$ERGOSTAT_AGENT`, the block that built it;
    - `conflicts`: the queue's `refuse()` adds 1 for a merge conflict, folded by sum.

Choices taken alone (the most reversible):
- **Scored at `approved`, judged by the queue and main.** The score is meant to route the checks that come after
  approval. A conflict is not a failure: it is a feature (`conflicts`), and a sent-back gap opens a new attempt when it
  is approved again. A flake retry (`gap.retried`, back to approved) withdraws the open attempt unjudged.
- **"Validate on past batches" is per gap.** A batch's failure is pinned on one gap by the queue's isolation
  (`gap.queue-failed`), so a gap-level backtest is the batch question asked of each change. No batch-level score
  (for example 1 − Π(1 − p) over its gaps) is built. It would be a few lines on top of `scores()`.
- **The score is a new key, not a field.** Gap items already have a `risk` field (backlog grooming), and items are
  folds of their events. So the score is `risk_score` beside the fields, never in them, and no event is written.
- **No page shows it.** The item page renders the detail's fields, not `risk_score`, and the rules forbid new panels.
  It is read through the CLI, the API's and MCP's item detail.

Tests (`tests/test_item_risk.py`, 16):
- Done 1, `test_a_backtest_on_a_factory_record_shows_calibration`. It runs on the factory's own gap and milestone kinds
  (read from `ergostat.yaml`) and a synthetic factory-shaped record: 800 gaps with known chances of failing, some
  failing in the queue and some reverted five gaps after merging. What it shows:
  - each band of 50 attempts or more is within 0.1 of its mean score, and the rate rises with the band;
  - the AUC is 0.69 against the true chances' 0.77, and the Brier score (0.18) is below the base rate's (0.196);
  - the CLI table and its JSON agree.
- Done 2, `test_the_score_is_on_each_item_and_queryable`. It checks:
  - all 202 items scored, highest first, in the CLI's JSON and its table;
  - a change touching the hot file scored above a cold one, with that path named in its why;
  - the score on the detail and on `item ID --json`;
  - the CLI refusing a kind that declares none, and no `risk_score` on such a kind's detail.
- `test_an_attempt_is_scored_from_the_attempts_judged_before_it_in_record_order`: seq beats time, scores are never
  revised, a revert after landing fails the attempt after all, and the kept replay equals a fresh one.
- `test_a_record_made_again_in_the_same_place_is_replayed_from_the_start`.
- `test_a_missing_value_is_learned_as_its_own_and_too_few_gives_no_score`.
- `test_the_factory_records_what_its_score_reads`: a stacked gap's `paths` are its own, not its base's, and
  `built_by` is recorded.
- 9 cases of `test_a_bad_declaration_is_refused`, including `null`, `least: 0` and `least: true`.
- `test_a_score_that_fails_is_said_on_the_detail_never_failing_it` (lesson 3). A replay that raises puts
  `failed: <error>` in `risk_score`, and the detail is still served. Without the catch, the raise is the test's
  failure. That failure was not run separately.
- `tests/test_queue.py::test_a_conflicting_own_gap_ends_in_fix_not_approved` now also asserts `conflicts == 1`.

Seen to fail with the code broken, each put back after:
- the replay sorted by time: the order test failed, with c scored before a and b;
- a revert after passing ignored: the calibration test (bands not rising enough), the queryable test and the order
  test failed;
- the Platt calibration off: the calibration test failed, its 0.2-0.3 band at 0.136 against a mean score of 0.254;
- the replay never started again: the made-again test failed;
- `risk_score` left off the detail: the queryable test failed;
- paths taken against main for a stacked gap: the factory test failed, with `base.py` among them.

The order test first passed with the time-sorted mutation. Its event was fed through the kept replay's catch-up, not
a fresh replay. It now clears the replay first and compares every attempt's score.

Run here, one file at a time:
- tests/test_item_risk.py (16 passed);
- tests/test_spec_schema.py, tests/test_library_trust.py and tests/test_cli_fallback.py (106 passed);
- tests/test_spec_structure.py, tests/test_queue.py and tests/test_item_search.py (41 passed);
- the factory model's three `ergostat check` tests (test_factory.py, test_factory_split_systems.py and
  test_factory_cx_frame.py: no new finding);
- `ruff check ergostat tests scripts`, and ruff on the two dev/bin files: clean.

`main` has not moved past this branch's base, so there was nothing to merge. Not run: the whole unit suite, the four
browser files (no page changed) and `demo_check` (no example touched).

Not done, or not known:
- **Done 1 on the live factory record: not run.** The session has no live instance and must not measure one. The
  coordinator runs `ergostat item --kind gap --risk-score --backtest` there. On today's record no past gap has
  `paths`, `built_by` or `conflicts`, so for those gaps the three read `(none)`. Until new gaps accumulate, the score
  learns only from `net_lines`, `source` and `failed_gates`. Its calibration on the real record is unknown until that
  run, and a gap whose early events were rolled up has its earlier attempts unseen (counted in `rolled_up`).
- **Cost not measured at the factory's size.** The first call replays every gap event in that process, and the web
  server's first item page of a gap pays for it. Later calls only catch up.
- **Nothing routes checks by the score yet.** That is error-budget-sets-check-level's and merge-lanes-in-parallel's
  work.

Round 2, 2026-11-24. The review's one finding was blocking. It is fixed, and there were no others to answer
(lesson 12).

- **The finding.** A flake was learned as the change's failure. The queue says `gap.queue-failed` before triage
  knows it was a flake, so the attempt was already judged failed when `gap.retried` brought the gap back to
  `approved`. Round 1's claim that a flake retry withdraws the attempt unjudged was wider than the code.
- **The fix, in the core option, naming no gaps.** A kind may declare `undone: [TYPES]`: the event types that say a
  failure was not the item's. Of the reviewer's three ways, I took the declared undo events. It is the most
  reversible, and a kind that declares none behaves exactly as in round 1. With `undone` declared, a `failed` event
  on an open attempt is **held** until the item's next change of state:
  - an `undone` event first withdraws the attempt unjudged;
  - any other change of state judges it failed (sent back or parked by triage);
  - a `failed` event after the attempt passed (a revert) is judged at once, as before;
  - while held, the attempt is judged neither way, and the backtest counts it as `held` (within `open`).
  Compile refuses an `undone` that is not a list of event type names, or that shares a type with `failed`. The schema,
  SPEC §5a and the agent guide say it.
- **The factory's declaration.** `undone: [gap.retried]`. Triage says it for a flake, for a failure of quarantined
  tests only, and for a stall under `STALLS_MOST`. Each of these is now withdrawn, never learned.
- **Tests.** The synthetic factory record now has triage's two routes. 196 of the 800 gaps have a flake first
  (queue-failed, `gap.measured`, retried, queued), and hot-file gaps twice as often, so a flake counted as a failure
  skews the hot path. A real queue failure is now followed by triage's `gap.sent-back`. The calibration test asserts
  that all 196 attempts were withdrawn, that 800 were judged, and that none were held.
- **New tests.**
  - `test_a_flake_retried_is_never_the_changes_failure`: on the factory's own kind, queue-failed, retried, merged
    counts one pass and one withdrawal, with the path's counts `[1, 0]`. Queue-failed then sent-back, and queue-failed
    then parked, are failures. Queue-failed alone is held. A fresh replay agrees with the kept one.
  - `test_without_undone_a_failure_is_judged_at_once`.
  - Three more refused declarations: `undone` overlapping `failed`, `undone: null`, and a bad type name.
- **Seen to fail with the code broken, each put back after.** Each of the three breaks below failed the calibration
  test, the queryable test and the flake test:
  - never holding (round 1's behaviour): 0 withdrawn of 196;
  - a held failure never judged: 632 judged of 800;
  - the `undone` event ignored: 0 withdrawn, and the flake's attempt judged failed.
- **Run here, one file at a time.**
  - tests/test_item_risk.py: 21 passed.
  - tests/test_spec_schema.py, tests/test_library_trust.py and tests/test_cli_fallback.py: 106 passed.
  - tests/test_spec_structure.py, tests/test_queue.py and tests/test_item_search.py: 41 passed.
  - test_factory_split_systems.py and test_factory_cx_frame.py: passed.
  - Two `ergostat check` tests from test_factory.py (`test_ergostat_check_on_the_factory_model_reports_no_new_finding`
    and `test_the_time_goals_have_no_check_findings`): passed.
  - Ruff: clean.
- **Not run, and unchanged since round 1.** `main` has not moved past the merge already on this branch. The whole
  unit suite and the four browser files were not run (no page changed). The live backtest was not run either.
- **Size.** About 30 more net lines outside tests/, docs/ and dev/, within the budget.

Round 3, 2026-11-24. The review had two findings, both blocking. Both are answered, and there were no others
(lesson 12).

- **Finding 1: a lease's move ended the hold.** It was right. Round 2's fix held a flake's failure only until the next
  change of state. In the real flow, triage takes the gap under a lease, and `ergostat.lease.taken` moves it from
  queue-failed to leased. That move judged the held failure as failed before `gap.retried` arrived, so every flake,
  quarantined-only failure and stall was still learned as the branch's failure. Round 2's claim was wider than the
  code (lesson 8).
- **The fix, in the core option, naming no gaps.** I took the reviewer's first way, because it is the narrower of
  the two. The replay now keeps each item's own state, the one its own events moved it to. A lease event
  (`ergostat.lease.*`: taken, ended, expired, redriven) still folds the item, but is never a change of state for the
  score. So a lease never judges, withdraws or opens an attempt. That also covers a lease given back to `approved` (a
  nack): before the fix, that return withdrew the open attempt and opened a new one. A kind with no leases behaves
  as before. SPEC §5a, the agent guide, the schema's `undone` description and the module docstring say it.
- **What this leaves out.** A lease that ends in `dead` (attempts used up) does not judge a held failure either. That
  attempt stays held, counted as open and held in the backtest, until the item's own events move it. This is the
  reversible side: a dead letter is the runner's state, not a verdict on the change.
- **Finding 2: the tests had no lease events.** That was also right (lesson 9). The tests now carry them:
  - **The synthetic factory record.** It now has the queue's lease (taken at approved, then acked), and triage's
    lease on each queue failure (taken at queue-failed, then acked after `gap.retried` or `gap.sent-back`). The
    calibration and queryable tests run on it.
  - **The new test, `test_a_lease_moving_the_item_never_judges_or_reopens_an_attempt`.** It replays the reviewer's
    sequence on the factory's own kind: queue-failed, ack, triage's lease taken, measured, retried, ack. A queue lease
    nacked back to approved and taken again follows, then queued, merged and ack. It asserts that the attempt is
    withdrawn, that the one after it passes, and that the path's counts are `[2, 1]` (that pass plus the sent-back gap's
    failure). A sent-back gap under the same leases is judged failed, and a gap still under triage's lease is held.
    A fresh replay agrees with the kept one.
  - `run()` is now a module helper that writes lease steps. The round-2 flake test still runs without leases.
- **Seen to fail on round 2's code, before the fix.** Three tests failed:
  - the calibration test: 0 withdrawn of 196;
  - the queryable test: 258 judged instead of 200;
  - the new test: two more judged and two more failed than expected, with the waiting gap judged failed.
  All 22 pass after the fix.
- **Run here, one file at a time.**
  - tests/test_item_risk.py: 22 passed.
  - tests/test_spec_schema.py, tests/test_library_trust.py and tests/test_cli_fallback.py: 106 passed.
  - tests/test_spec_structure.py, tests/test_queue.py and tests/test_item_search.py: 41 passed.
  - `ruff check ergostat tests scripts`: clean.
- **Not run.** The factory's `ergostat check` tests were not run again, because neither `ergostat.yaml` nor any
  dev/ model changed this round. The whole unit suite, the four browser files (no page changed) and the live backtest
  were not run either. `main` has not moved past the merge already on this branch.
- **Size.** About 10 more net lines outside tests/, docs/ and dev/, within the budget.

Round 4, 2026-11-24. The review had one finding, and it was blocking. It is fixed, and there were no others to
answer (lesson 12).

- **The finding: a refused event still judged or withdrew.** `Learner.feed` read only the event's type and never
  asked whether the fold had refused the event. So a `gap.retried` from a triage run whose lease had ended was fenced,
  and the gap stayed queue-failed, but the attempt was still withdrawn. A refused `failed` event still held or judged
  the attempt too. The reviewer was right (lessons 3 and 8).
- **The fix, in the core option.** I took the reviewer's way. `feed` compares the item's `refused` count before and
  after the fold, and an event the fold refused counts as neither a `failed` nor an `undone` event. That covers
  fencing, a sealed kind, an `if-unchanged` stale read, `moves-from` and `final`. A move the event still made
  (`final`'s mapped state) still counts as a change of state, so the item's own state stays true to its fold.
  - **Choice taken alone: `final` too.** A `failed` event that `final` refuses is not counted either, because the
    item's page shows it as refused. The other way, counting it as a revert, is a one-line change. No kind in the
    factory declares `final` on `gap`.
  - **Where it is said.** SPEC §5a, the agent guide, the schema's `undone` description, the module docstring and the
    entry.
- **The new test.** `test_an_event_the_fold_refused_never_undoes_or_fails_an_attempt` runs on the factory's own kind.
  - **A fenced retry.** Queue-failed, then triage's lease r2 taken and nacked, then r3 taken. Then `gap.retried`,
    caused by r2, which the fold fences. The test asserts the refusal is on the item, and that the attempt is still
    held, not withdrawn.
  - **The real failure after it.** A `gap.sent-back` from r3 then judges the attempt failed: one more judged and one
    more failed.
  - **A fenced `gap.queue-failed`.** One from a nacked queue run fails nothing: the attempt is neither held nor
    judged.
  - **A fresh replay** agrees with the kept one.
  - `run()` now takes `TYPE@RUN` for an event caused by that run.
- **Seen to fail with the code broken, then put back.** With the event's type read alone (round 3's behaviour), the
  new test failed at its first check: the attempt was `withdrawn` where it should have been held. All 23 pass with the
  fix.
- **Run here, one file at a time.**
  - tests/test_item_risk.py: 23 passed.
  - tests/test_spec_schema.py, tests/test_library_trust.py and tests/test_cli_fallback.py: 106 passed.
  - tests/test_spec_structure.py, tests/test_queue.py and tests/test_item_search.py: 41 passed.
  - `ruff check ergostat tests scripts`: clean.
- **Not run.** The factory's `ergostat check` tests were not run (neither `ergostat.yaml` nor a dev/ model changed).
  The whole unit suite, the four browser files (no page changed) and the live backtest were not run either. `main`
  has not moved past the merge already on this branch.
- **Size.** About 5 more net lines outside tests/, docs/ and dev/, within the budget.

## Entry

section: The factory (ergostat on ergostat)

- **Each change gets a risk score learned from what failed before** (done, on `risk-score-from-history`; SPEC §5a,
  *Risk score*). A kind may declare `risk-score:` (off unless declared). An attempt opens each time an item enters a
  state. It fails at the declared events (a revert after passing too) and passes at the declared states. With
  `undone` declared, a failure is held until the item's next change of state by its own events (never a lease's), and
  an `undone` event (a flake retried) first withdraws it unjudged. An event the fold refused (a fenced retry) neither
  fails nor undoes an attempt. It is scored
  from the attempts judged before it, in the record's order: naive Bayes over declared fields (a value, a list's
  riskiest element, a size band), calibrated by Platt scaling, a missing value learned as its own, and no score before
  `least`. It is on each item's detail (`risk_score`) and in `ergostat item --kind K --risk-score [--backtest]`. The
  backtest gives the failure rate per score band, the Brier score and the AUC. The factory declares it on `gap`
  (approved, then failed in the queue or reverted, a flake retried undoing it), from its paths, net lines, source, author block, conflicts and
  failed gates, and now records the first three it lacked. Left: the backtest on the live factory record (not run in
  the session; past gaps lack paths, author and conflicts), and routing checks by it.
