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
