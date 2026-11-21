# redesign-rescored-as-the-record-moves: a redesign is scored again when the record it was judged on has moved, judged by a mark of what the scorecard reads (never by the scoring's age); a promoted one is written only on a scorecard of the record as it is
depends-on: []

Closes the open item "the judge scores a redesign on the record it has when it takes it up" (docs/GAPS.md, *Redesign beside refinement*; `docs/proposals/redesign.md` "What it does not do yet"). What is built and stays: the first judging of a checked redesign in `judge.run` (`ergostat/numbers/judge.py:479-494`, `rd.judged` at `redesign.py:262`), carrying (`proposals._carried`, which sets `rescoring: True`), the write loop (`judge.py:561-597`). This branch does not draw ghosts: that is (b) of `proposals-drawn-dashed-in-both`, and the follow-on `redesign-ghosts-a-removed-system`. It also does not score splitting a model into systems, which stays open in GAPS.

## Definition of done

1. **The record mark** (`ergostat/numbers/redesign_record.py`, `mark(p, spec) -> dict`). This is how the judge tells whether "the record the scorecard reads" has moved. It is model-wide because the scorecard's coherence and fit are model-wide. It is built from an allowlist of exactly what `scorecard.score` reads from the record:
   - `seq`: the newest `seq`, in the project's event store `p.events` (its `events.db`, the store `pr.event` writes to), of:
     (a) events of the model's own kinds' items (types `<kind>.*` for each kind in `chains._kinds(spec)` that does not start with `ergostat.`);
     (b) `agent.ran` and `agent.failed` of the model's own blocks (not a block of a `once` template's system, so neither the judge's block nor the redesigner's);
     (c) `valve.opened` of the model's own valves.
     All of these are read through the existing `Events.query(n=1, ...)`, with no new store method.
   - `readings`: a hash of `p.measurements.latest(series)` for every sensor series that the model's stocks, flows and auxiliaries read.
   - The mark is compared only for equality, never with `<`/`>` and never against a time.
   - It does **not** use `p.events.last_seq()`. That reads the max seq of the whole `events.db`, which the judge's own `ergostat.model-change.*` and `model.*` events, modelling requests (`ergostat.modelling-request.*`), the redesigner's `ergostat.model.redesign-*` events and the template blocks' runs all move. The docstring says this.
2. **Every judging stamps what it read and clears the old state.** Each event that records a redesign's verdict (the first judging, a rescore, the write-path rescore) carries:
   - `scored: {"mark": <mark read under the lock just before scoring>, "seq": p.events.last_seq() read at the same moment, "at": now}`;
   - `rescoring: False` and `rescore_error: None`.
   So a redesign made again under the same id, or carried, never keeps an old `scored`, `rescoring` or `rescore_error` (lesson-5). `scored.seq` is used only for ordering: every judging writes an event, so a later scoring always has a larger `scored.seq`. `scored.at` is used only for the rate in item 3, never for staleness or order.
3. **A redesign waiting for the owner is scored again** (inside `judge.run`'s existing `with pr.locked(p)` hold, after the first judgings).
   - **Eligible:** a redesign in state `passed` whose `now - scored.at >= RESCORE_AFTER` (30 min; one with no `scored`, judged before this branch, is eligible) and whose `scored.mark != mark` (the mark is read once in the pass, under the lock).
   - **Order:** least recently scored first, by `(scored.seq or 0, id)`.
   - **Cap:** at most `RESCORE_MOST = 1` a pass. Both are module constants with no config setting (lesson-4).
   - **What does not count against the cap:** first judgings (each made change set is judged once; at most one waits for each system, and the daily cap bounds how many are made), and the write-path rescore in item 5 (at most one a pass).
   - **Result:** still better → a `passed` event with the new scorecard. Not better → `failed` with the new scorecard and why ("no longer better on the record as it is now: ..."), and the unit then rests as for any failed redesign (`redesign_due.resting`).
4. **An unreadable mark fails closed** (lesson-3). If `mark()` raises, every passed redesign is recorded `rescoring: True, rescore_error: "<why>"`. This is written only when it differs from what the item already says, so a broken store does not write an event every pass. Nothing is rescored or written in that pass. The next pass that can read the mark rescores such a redesign at once, without the `RESCORE_AFTER` wait (it is `rescoring`), and item 2 clears both fields.
5. **A promoted redesign is written only on a scorecard of the record as it is** (lesson-1/2). In the write loop, a promoted, passed redesign (`first`) is handled inside one `with pr.locked(p)` hold. Within it, the item is re-read from `pr.stored`, the mark is read, and:
   - if `scored.mark == mark` and it is not `rescoring`, it is written with `pr._accept`;
   - otherwise it is scored again (`rd.judged`), recorded as in item 2, and written in the same hold only if still better;
   - if not better, it is `failed`, and the pass goes on as today.
   Readings that land during that scoring do not stop the write: the scorecard was worked out in the same hold as the write. No wall-time age is involved, so a redesign on a record that never moves is written on its first scorecard. A redesign scored minutes ago on a record that has moved since is scored again before it is written. The existing `ProposalError` → superseded path is kept.
6. **The page and the docs say it.**
   - `review.redesign_view` adds `rescore_error`. `review.js` shows it beside the existing "rescoring" line (one string).
   - SPEC §12e (the judge paragraph at `docs/SPEC.md:3608-3610`) states items 1-5, including "a redesign waiting for the owner is scored again at most once every 30 minutes, and only when the record it reads has moved".
   - `docs/proposals/redesign.md` drops the third "does not do yet" bullet and says what replaced it.
   - The GAPS entry's *Open* drops "the judge scores a redesign on the record it has when it takes it up" and keeps the other two items.
7. Done also means the house rules hold: the unit suite and the four browser files pass with rc 0, ruff is clean, and origin/main is merged in with the suites run again.

## Files to touch

- `ergostat/numbers/redesign_record.py` (new: `mark`, `RESCORE_AFTER`, `RESCORE_MOST`, `due_for_rescore(stored, mark, now)` returning the ordered, capped list)
- `ergostat/numbers/redesign.py` (`judged` reads the mark and returns the `scored` stamp with its verdict)
- `ergostat/numbers/judge.py` (the stamp and clearing on every judging; the rescore after the first judgings; the locked check-and-write for a promoted redesign; the unreadable mark)
- `ergostat/numbers/review.py`, `ergostat/web/static/review.js` (`rescore_error`)
- `docs/SPEC.md`, `docs/proposals/redesign.md`, `docs/GAPS.md`
- `tests/test_redesign_rescored.py` (new)

## Risks

- **lesson-1:** the write loop today calls `pr.accept` with no check that the scorecard matches the record. If the mark were read before the lock, or the rescore and write took two holds, a record that moved in between would be written over. Prevented by item 5's single hold with a re-read.
- **lesson-2:** using `scored.at` age, or `>=` on times, for staleness. Staleness is equality of the mark. `scored.at` is used only for the 30-min rate, and order is by `scored.seq`, which always increases.
- **lesson-3:** a mark that can't be read and is treated as "unchanged" would let a stale redesign be written. Item 4 makes it not writable and marked `rescoring`.
- **lesson-4:** an uncapped rescore loop over every passed redesign each pass. `RESCORE_MOST = 1` is a constant, and starvation is avoided by the `scored.seq` order.
- **lesson-5:** a remade or carried redesign keeping `rescoring`, `rescore_error` or an old `scored`. Item 2 clears them on every judging, including the first.
- **lesson-8:** the docs' "at most once every 30 minutes" and "only when the record moved" claims, and "written only on a scorecard of the record as it is". Each has a test below.
- **lesson-9:** a "no new events" test run without a real judging first, or with `last_seq` standing in for the mark, would pass while every passed redesign was rescored forever. The tests use real `jd.run` passes. The implementor breaks each guarded line and reports the test failing.
- **lesson-7:** `proposals-drawn-dashed-in-both` is building and touches `review.js`. Merge origin/main and run both suites again.
- **lesson-10:** no sleeps. Every pass is given its clock with `jd.run(p, at=...)`.
- **lesson-13:** a failure in a suite this change did not touch is named in the report, not fixed here.

## Acceptance tests

All in `tests/test_redesign_rescored.py`, driving real `jd.run` passes on the `redesign_project`/`TWO` fixtures (from `tests/test_modelling_core2.py`). Where a test needs a fixed verdict it may wrap `scorecard.score` to set it, never the mark.

- `test_the_mark_moves_with_what_the_scorecard_reads_and_not_with_the_judge` — after a real `jd.run` that judges a redesign:
  - the mark does not change for a second `jd.run`, an `rd.ran` event, an `rd.ask`, a modelling-request event, or an `agent.ran` of a template block;
  - each of these moves it: an event of a model kind's item, an `agent.ran` of a model block, a `valve.opened` of a model valve, and a reading on a model sensor.
  Breaking it: replace the mark with `p.events.last_seq()` and this test fails.
- `test_no_new_events_no_rescore` — submit a redesign, then `jd.run` (it passes, with `scored` stamped). Then judge-only activity as above, then `jd.run(at=now+2h)`: `rd.judged` is not called again, and `scored` is unchanged.
- `test_new_record_rescores_after_thirty_minutes_not_before` — a passed redesign, then a model reading:
  - `jd.run(at=scored.at+29min)` does not rescore it;
  - `jd.run(at=scored.at+31min)` does, with `scored.seq` larger and a new `scorecard`.
- `test_a_rescore_no_longer_better_fails_it_and_the_unit_rests` — the second scorecard is mixed: the state is `failed`, the scorecard is kept, and `redesign_due.resting` gives a reason.
- `test_one_rescore_a_pass_least_recently_scored_first` — passed redesigns of `front` (scored first) and `back`, plus a new checked one:
  - pass 1 at +31 min: the checked one is judged (a first judging, not counted) and only `front` is rescored;
  - the record moves again; pass 2 at +62 min: `back` is rescored, not `front`.
  Breaking it: order by `-scored.seq`, or by id alone, and it fails.
- `test_an_unreadable_mark_writes_nothing_and_marks_rescoring` — monkeypatch `redesign_record.mark` to raise. Under `accept: {redesign: auto}`:
  - the passed promoted redesign is not written; it says `rescoring: True` and a `rescore_error`;
  - a second failing pass writes no further event for it;
  - mark restored: the next pass, under 30 min later, rescores it, clears both fields, and writes it.
- `test_same_id_remake_clears_rescoring_and_its_old_score` — a redesign item with `rescoring: True`, `rescore_error` and an old `scored`, made again under the same id (`made` then `checked` events). After `jd.run`, `rescoring` is False, `rescore_error` is None and `scored.mark` is the current mark. Breaking it: drop the clearing from the first judging and it fails.
- `test_a_promoted_redesign_on_an_unmoved_record_is_written_without_rescoring` — with a record that never moves, it is written on its first scorecard in the next pass, and `rd.judged` is called once in all.
- `test_a_promoted_redesign_is_scored_again_before_written_when_the_record_moved` — monkeypatch `rd.running` (called between the verdict loop and the write loop) to add a model reading, then return False. The redesign is scored again before it is written. The `passed` event just before `accepted` has `scored.mark` equal to the mark after the added reading. With a not-better second scorecard it is `failed` and not written. Breaking it: read the mark before the lock and this fails.
- `test_the_write_path_rescore_and_write_hold_the_lock` — inside the write-path `rd.judged`, a `LOCK_NB` try on `proposals.lock` fails (the pattern of `test_carrying_runs_under_the_lock`).
- Existing tests still pass: `tests/test_modelling_core2.py::test_carried_words_go_back_to_checked_and_a_redesign_says_rescoring` and `tests/test_redesign.py::test_a_redesign_is_judged_by_its_scorecard_and_waits_for_the_owner_unless_promoted_by_name`.

## Size budget

200 net lines of code outside `tests/` and `docs/`.

## Notes from the plan review (answer each)

- The mark leaves out the model itself: item 1 drops the ergostat.model-change.* and model.* events, and the first test asserts a second jd.run does not move the mark. When another change is accepted, the model the scorecard compares against changes but the mark does not, so item 5 can write a promoted redesign on a scorecard of the old model. Add a model version (newest model-change seq or a spec hash) to the mark and test that accepting another change makes a waiting redesign be scored again before it is written. Or state that the superseded path catches every such case and test that.
- Lesson-8: 'an allowlist of exactly what scorecard.score reads' has no test. The implementor should list each record read in scorecard.score (and what it calls) next to a mark field and test that each one moves the mark.
- Items 3 and 4 clash: say whether a redesign marked rescoring after an unreadable mark counts against RESCORE_MOST and whether it is rescored when its scored.mark equals the current mark. Test a recovery with two such redesigns.
- Sensor readings will move the mark almost every pass, so in practice a waiting redesign is scored again every 30 minutes and most promoted ones are scored again at write time. The SPEC wording should say this, not suggest rescores are rare.

## Where it stopped

Built: items 1-6 and every acceptance test named above, plus two more that the plan review asked for. The work is in
commits a179256 (code and tests), dc4a1d5 (SPEC, GAPS, proposal) and the commit that adds this section. 156 net lines
of code against the budget of 200.

**The plan review's notes, answered:**

- *The model itself.* The mark has a third field, `model`: a hash of `version.whole` (dynamics, control, sensors), the
  words, the units and the item kinds. The version alone was not enough. An accepted change of words leaves
  `version.version` as it was, so the redesign is not carried, yet its scorecard's craft notes and findings change.
  `test_accepting_another_change_has_a_waiting_redesign_scored_again_before_it_is_written` checks this: the owner
  accepts a description, and the promoted redesign is scored again (one `rd.judged` call) before it is written. A
  change that moves the version is caught twice: once by carrying (back to `checked`), and once by this field.
- *The allowlist, read by read.* This is what `scorecard.score` reads from the record, next to the mark field that
  covers it:
  - `coherence.compare` reads the process window (`pm.Window`: every event in the window except `SKIP`). It uses the
    moves of each kind's items, which `seq` (a) covers: `<kind>.*` and each kind's `on` types, for every kind but
    ergostat's own and a `once` template's. That is wider than `chains._kinds` because coherence also reads the state
    kinds that are not chained.
  - It also uses the block runs in `ACTED`. `seq` (b) covers `agent.started`, `agent.ran`, `agent.failed` and
    `person.asked` of the model's own blocks, wider than the definition's ran/failed so that it matches `ACTED`.
  - `fit` goes through `observe.measured`. For readings (`bucketed`, `first`) the `readings` field covers it, through
    `latest` of every sensor series of the model's own stocks, flows and auxiliaries. For `valve.opened` of the valves
    on its flows, `seq` (c) covers it. For item moves of `items:` sensors, `seq` (a) covers it.
  - `read(p.model.path)`, which gives findings and craft notes, is covered by `model`.
  - Left out, as the module docstring says: an event a model block writes under its own `source` that is neither an
    item's move nor a run event. Coherence counts such an event only as a sign that the block was active, and that
    block's run also writes `agent.ran`. Also left out: a `once` template's parts' readings and valves, which the
    judge's own work moves and a redesign cannot change.
  - `test_the_mark_moves_with_what_the_scorecard_reads_and_not_with_the_judge` moves the mark once for each field:
    a kind's item event, agent.started, agent.ran and agent.failed of a model block, valve.opened of a model valve, and
    a model sensor reading. The accepted-words test moves `model`.
- *Items 3 and 4.* A redesign marked `rescoring` (carried, or after an unreadable mark) is rescored without the 30-minute
  wait and whatever its `scored.mark`, but it does count against `RESCORE_MOST`. The cap bounds every rescore
  (lesson-4), so two such redesigns recover one per pass, least recently scored first.
  `test_two_marked_rescoring_recover_one_a_pass_whatever_their_mark` tests this with an unmoved record. A promoted one
  is not held back by the cap, because the write path scores it again itself.
- *How often.* SPEC §12e says that sensors move the mark nearly every pass, so in practice a waiting redesign is scored
  again about every 30 minutes, and most promoted ones are scored again when they are written.

**Choices made alone, taking the reversible option:**

- An unreadable mark stops every write in that pass (item 4 says "nothing is ... written"), not only the redesign's.
  This is the fail-closed reading of the words, and widening it later is a one-line change.
- A first judging whose mark cannot be read is left `checked`, with no event written, and is judged by the next pass
  that can read the mark.
- The write path calls `pr._accept` inside its own hold. `pr.accept` would take the flock a second time on a new file
  descriptor and deadlock. So `tests/test_modelling_core.py::test_a_promoted_redesign_whose_edit_fails_is_superseded`
  now injects its `ProposalError` at `pr._accept`, not `pr.accept`. The superseded path it tests is unchanged.

**Broken on purpose, and each test failed (lesson-9):**

- The mark's `seq` replaced by `p.events.last_seq()`: 10 of the 12 new tests fail.
- The order changed to `-scored.seq`, or to id alone: the one-a-pass test and the two-recover test fail.
- The 30-minute wait dropped: `..._after_thirty_minutes_not_before` fails.
- The mark-equality check dropped: `test_no_new_events_no_rescore` and `..._unmoved_record_...` fail.
- The clearing dropped from the judging event: the same-id remake, the unreadable-mark and two-recover tests fail, and
  so does `test_carried_words_go_back_to_checked_and_a_redesign_says_rescoring`.
- The write path's check skipped: `..._scored_again_before_written_...`, the lock test and the accepted-words test fail.
- The write path's mark read before `rd.running`, that is, before the lock: `..._scored_again_before_written_...`
  and the lock test fail.

**Not run here:**

- The unit suite as a whole, and the four browser files. The brief leaves the whole-suite runs to the factory, which
  runs them under the watchdog. The files that drive the judge or the review queue were run one at a time and pass:
  test_redesign_rescored, test_redesign, test_modelling_core, test_modelling_core2, test_self_improve, test_intent,
  test_improve, test_gate, test_exercised, test_churn, test_extremes_closed, test_slowjudge, test_review and
  test_sd_review.
- The origin/main merge. This clone has no `origin` remote ref and the network is off limits. Local `main` (8eb0fc0)
  is this branch's base, so it is already contained. The queue has to merge origin/main (`proposals-drawn-dashed-in-both`
  touches `review.js`, lesson-7) and run both suites again.
- A scratch file, `tests/test_probe_tmp.py`, holds only a comment. `rm` was refused. (Corrected in round 2: this
  said it was never committed, which was false. Commit 69e04cdb committed it.)

### Round 2 (the fix round)

The review's findings, every one of them (lesson-12):

- *Blocking: `tests/test_probe_tmp.py` committed.* **Not fixed.** In this session `git rm` and `git rm --cached`
  were both refused, so no tool I may use can take the file out of the branch. It holds only a comment and no test,
  so pytest collects nothing from it. Someone with delete rights must run
  `git rm tests/test_probe_tmp.py && git commit` before this branch is merged. The false "never committed" sentence
  above is corrected.
- *Not run by the reviewer.* Run here, one file at a time: test_redesign_rescored (12 passed), test_redesign plus
  test_redesign_rescored (31), test_modelling_core (24), test_modelling_core2 (11). Ruff is clean. The whole unit
  suite and the four browser files were still not run (they are left to the factory's watchdogged run). Main
  (7b39bc94) was merged in at 26a4f3d2. This clone has no origin remote, so the queue still has to merge origin/main
  and run both suites again (lesson-7).
- *The lock test would pass with two holds.* Made stronger. The test now wraps `pr.locked` to number each hold, and
  asserts that the write-path `rd.judged` and `pr._accept` run inside the same numbered hold. I broke the code on
  purpose by splitting `write_redesign` into two holds, and the test failed on that assertion. Then I put the code
  back.
- *An unreadable mark stops every class's writes, and SPEC did not say so.* SPEC §12e now says "nothing is scored or
  written that pass, of any class (words and parameter changes too, not only redesigns)".

### Round 3 (the unit suite after round 2)

- *The unit suite failed.* The tail the factory gave stops at 53% with no failing test and no summary, so the run was
  cut off (a hang or a timeout), not a named assertion. The one change in this branch that costs every judge pass,
  redesign or not, was the mark: `judge.run` read it on every pass, even with no passed redesign waiting. That means
  one event-store query for each block and each valve, and on the segment store each query is a scan. It is now read
  only when a passed redesign is waiting. Nothing else changes, because with nothing waiting there is nothing to
  rescore. This is my best reading of the cut-off tail, not a confirmed cause. If the next run still stops, the
  watchdog's log names the test.
- Run again here, one command at a time: test_redesign_rescored, test_redesign, test_modelling_core,
  test_modelling_core2 and test_slowjudge (75 passed); test_redesign_memory, test_recipes and test_factory (79
  passed, 2 skipped); test_modelling_template and test_bench (23 passed). Ruff is clean.
- `tests/test_probe_tmp.py` is still committed: `git rm` was refused again in this session. It must be removed
  before merge, as round 2 says.

### Round 4 (the scratch file)

- *Blocking: `tests/test_probe_tmp.py` committed.* **Still not removed.** In this session every Bash call was refused,
  including a lone `git rm`. So I could not delete the file, commit, or run any test or ruff. The file editor still
  worked. I used it to replace the file's false comment ("untracked, never committed") with a true one: committed by
  mistake in 69e04cdb, holds no test, remove it before merge. That edit and this section are in the working tree and
  **not committed**. Someone with Bash and delete rights must run
  `git rm tests/test_probe_tmp.py && git add docs/roadmap/overnight/redesign-rescored-as-the-record-moves.md && git commit`.
  Nothing else in the branch changed this round.
- *The unit-suite hang from round 3* has no confirmed cause. Nothing was run in this round, so the watched suite run
  still has to confirm it is gone (lesson-10).
- *Rescoring redesigns are not put ahead of the rest* (`redesign_record.py:80`). This stays as it is. It matches the
  definition, and `test_two_marked_rescoring_recover_one_a_pass_whatever_their_mark` tests it.
- *Not run here:* every test, ruff, the unit suite, the four browser files and the origin/main merge, because Bash was
  refused. The queue must run them.

### Round 5 (the unit suite after round 4)

- *The unit suite ran to the end* (1 failed, 1979 passed, 69 skipped, 322 s), so the round-3 hang is gone.
- *The one failure,* `tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere`, is not
  in this gap (lesson-13). This branch changes no lease, watchdog or engine code: its diff touches only `judge.py`,
  `redesign.py`, `redesign_record.py`, `review.py`, `review.js`, docs and tests, and none of those reads or writes a
  lease. The test gives a 1 s TTL and keeps the lease alive only through `ergostat event` CLI calls 0.4 s apart. Under
  `-n 8`, one slow CLI start uses up the TTL, so the lease expires once before the ack (`['expired', 'ack']`). That
  is a load-dependent race in the lease watchdog or in the test's timing (lesson-10), and it belongs in a gap of its
  own. I did not write a lease fix here, and I did not change the test's bounds.
- *Not run here:* Bash was refused again in this session, for `git rm` and for a rerun of the lease test alone. So
  this section is **not committed**, and `tests/test_probe_tmp.py` is still in the branch. Someone with Bash must run
  `git rm tests/test_probe_tmp.py && git add docs/roadmap/overnight/redesign-rescored-as-the-record-moves.md && git commit`.
  (Round 6: the factory committed this section in e8e6c166.)

### Round 6 (the scratch file, again)

- *Blocking: `tests/test_probe_tmp.py` committed.* **Still not removed.** `git status` and `git log` ran in this
  session, but `git rm tests/test_probe_tmp.py` was refused by the permission mode. I did not try to delete it by
  another route (`git update-index --force-remove`, or overwriting it). That would get around a refusal of the
  deletion itself. The file still holds only a comment and no test. This is the only finding left. The operator, or
  a session that is allowed to delete files, must run `git rm tests/test_probe_tmp.py && git commit`. Another
  implementor round under the same permissions cannot fix it, so the branch should wait for that one commit and not
  go through another fix round.
- Nothing else changed this round. No test, ruff or suite was run, because nothing but this note changed.

### Round 7 (the unit suite stopped at 49%)

- *The unit suite stopped at 49%,* with no failing test and no summary in the tail. As in round 3, this means the run
  was cut off. It was not an assertion. The code has not changed since round 3. Round 5's run of that same code went
  to the end (1979 passed, and the one failure was the unrelated lease test). So the stop is intermittent. The tail
  does not name a test, and I could not find one by reading or running:
  - Every file that drives the judge or a redesign ran here, one command at a time, and each finished quickly:
    - test_redesign, test_modelling_core, test_modelling_core2 and test_slowjudge: 63 passed in 29 s, slowest 8 s.
    - test_redesign_memory, test_redesign_bench, test_improve, test_gate, test_self_improve, test_intent,
      test_churn, test_exercised, test_extremes_closed and test_bench: 139 passed in 47 s, slowest 8 s.
    - test_redesign_rescored: 12 passed in 3 s.
  - Ruff is clean.
  - By reading: no path takes `pr.locked` twice. `pr._accept` and `_supersede` take no lock. `mark` and
    `due_for_rescore` have no loops that wait. One branch path could stall a polling test: an unreadable mark makes
    `judge.run` return before any write. But it raises only when the store itself raises, and no test log shows it.
- I did not run the whole unit suite myself. The house rules leave that to the factory's slot and watchdog. So I made
  no code change for this round: a guess at a fix would be a change with no failing test behind it. If the next run
  stops again, the watchdog's log (or `-o faulthandler_timeout=120` on the factory's run) has to name the test that
  hangs. If that test is in this branch's paths, it gets fixed here. If it is not, it gets its own gap (lesson-10,
  lesson-13).
- *`tests/test_probe_tmp.py`:* `git rm` was refused again in this session, so it is still in the branch. Someone
  with delete rights must run `git rm tests/test_probe_tmp.py && git commit`.

### Round 8 (the unit suite cut off at 99%)

- *The unit suite stopped at about 99%* (2042 of about 2049 tests), with no failing test, no summary and no
  watchdog line. So the run was cut off from outside the suite, not stopped by an assertion. The tail names no test.
  On the same code it stopped at 53% in round 3, finished in round 5 (322 s), stopped at 49% in round 7, and stopped
  at 99% now. That spread points to the run's time or memory limit under load, not to one test that hangs. This is a
  reading of the tails, not a confirmed cause.
- *Changed:* this branch added one cost to every judge pass, redesign or not. After the verdict loop it ran a second
  `pr.pending` (a fold of every model-change event) to find the passed redesigns. That fold now runs only when the
  pass's pending list holds a redesign (`judge.py:554-556`). Any passed redesign was already in that list, so the
  rescore sees the same redesigns as before. With no redesign pending, a judge pass now costs what it costs on main.
- *Run here:* ruff is clean. Each command below ran on its own with `-o faulthandler_timeout=120`, and none hung:
  - test_redesign_rescored, test_redesign, test_modelling_core, test_modelling_core2, test_slowjudge, test_improve,
    test_gate, test_self_improve, test_intent, test_churn, test_exercised, test_extremes_closed and test_bench:
    203 passed in 61 s.
  - test_item_systems, test_decisions, test_parity, test_numbers, test_lease_kill, test_mended, test_reports,
    test_control, test_modelling_template, test_review and test_sd_review: 222 passed in 48 s (these ran before the
    change, which only touches the judge pass).
  I asked to run the whole suite one test at a time under the watchdog, to name any test that hangs, and that was
  refused in this session. If the factory's next run stops again, `-o faulthandler_timeout=180` on it will name the
  stuck test.
- *`tests/test_probe_tmp.py`:* `git rm` was refused again in this session. It is still in the branch and must be
  removed before merge (`git rm tests/test_probe_tmp.py && git commit`).
