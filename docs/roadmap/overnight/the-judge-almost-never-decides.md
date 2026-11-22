# the-judge-almost-never-decides: a change whose replay is exactly the model's, on a record that exercised what it touches, is judged by the structural scorecard (findings, chains, coherence, craft notes; fit only against it), not left to wait for record that can never tell it apart
depends-on: []

## Where this starts (on main, not rebuilt)

`slowjudge` built the pooled confidence sequence, "needs about N more record", the horizon and the rule that a change whose replay is the same as the model's waits (`ergostat/numbers/judge.py:404-408`, `decide`). The redesign scorecard exists (`ergostat/numbers/scorecard.py`, `score`/`verdict`), and so does its use for change sets (`redesign.judged`, `judge.run` lines 479-494). Today a structural, wiring or parameter change that cannot move the replay waits until `horizon(needs)` (a day at least) and then ends inconclusive, which happens to nearly every such change on the work model. This branch gives that case a verdict from structural measures.

Not in this branch, and still open in GAPS: the information limit of a slow record (a fifth off a day-long drain still needs more than a week), and carrying a change over edits elsewhere (gap `proposals-superseded-by-any-edit`).

## Definition of done

1. **"Identical" is exact.** `judge.compare` returns `same: True` only when both replays follow the same set of stocks and every reading of every such stock is equal as a float between the model as it is and the model with the change, over the whole record held out. There is no tolerance. A change that moves any stock by any amount is judged by the record through the bound, as it is today, and never by structure.
2. **It cannot move the replay only on a record that exercised what it touches.** A change takes the structural path when `same` holds, `held >= needs` (the record it needs), and at least one stock in `nd["stocks"]` (or, when that is empty, any stock both replay) is read on the record held out and is not in `exercised.quiet(...)` over that record. When none is exercised, or the record of them is missing, the change keeps today's behaviour: it waits for record in which they move, then is inconclusive at the horizon. A missing input never counts as exercised (lesson-3).
3. **The structural verdict** (new module `ergostat/numbers/unmoved.py`, called from `judge.run` inside the existing `with pr.locked(p)` block, and counted against `MOST` like any judged change):
   - The model the change leaves is compiled from the files with findings (`tr.compiled(..., findings=True)`, as `redesign.judged` does). If any error is reported, the change is **failed** ("the model it leaves no longer compiles"), with no scorecard.
   - Otherwise `scorecard.score(..., fit_counts=False)` is worked out for the model as read from disk and the model after the change.
   - **better**: the change is **passed**. Only findings resolved, chains joined, coherence mismatches fewer or coherence up, and craft notes closed can make it better.
   - **mixed**, or **no better** with anything worse: the change is **failed**, as `redesign.judged` fails anything not better.
   - **No measure moved, every measure measured**: the change is **inconclusive** at once ("no structural measure moves, and the record cannot tell it from the model as it is").
   - **No measure moved, and coherence or the fit unmeasurable**: the change stays **under test**. Its `testing` event's `undecided` names what could not be measured and why. At `horizon(needs)` it is inconclusive, naming the same.
   - The verdict event carries `verdict.on = "structure"`, `verdict.scorecard` and `verdict.version`. The scorecard lives inside `verdict`, which is replaced whole by every verdict event, so nothing structural lives as a top-level field.
4. **The fit can only count against it.** With `fit_counts=False`, `scorecard.verdict` never counts "the fit made measurable" (or any fit improvement) as good. "The fit worse" and "behaviour lost" still count as bad. The redesign path keeps `fit_counts=True`, so its behaviour is unchanged by this.
5. **Unmeasurable never counts for a change (lesson-3).** In `scorecard.score`, when `coherence()` returns `error` on either side, or no kind is compared on either side, the coherence card is marked `measurable: False` and its `says` gives the reason. Mismatches and per-kind shares then count neither way: before this change, an error on the after side with mismatches before read as "N mismatches fewer", which made a change better. A fit that cannot be worked out before or after is `measurable: False` and counts neither way, as now.
6. **Locks and versions (lesson-1/2).**
   - The structural scoring runs inside `pr.locked(p)` (the judge's pass already holds it), and `pr.accept`, the owner's write through ergostat, takes the same lock. So no Accept, supersede or carry can come between the scorecard's read and the verdict event.
   - A hand edit of the model files takes no lock. To cover it, `unmoved` stamps `ver.version()` of the model **it read from disk** for the scorecard, not of `p.model.spec` taken at the start of the pass. If that version is not equal to `x["version"]`, it records no verdict, and the change is left for `supersede` on the next pass.
   - The window still left: a hand edit after the scorecard's read and before the event is written. The verdict is then stamped with the version it read. It is never acted on for the newer model: `pending()` and `pr.accept` compare `x["version"]` with the model as it is, and the judge never writes a structure-only pass (point 7).
7. **A pass on structure alone is the owner's.** `judge.owners(x)` is true when `(x.get("verdict") or {}).get("on") == "structure"`, so the `auto` policy never writes it, whatever the kind. It waits in the review queue with its scorecard beside it, as redesigns do.
8. **Docs.**
   - SPEC §12e and the `judge.py` docstring say points 1-7.
   - The GAPS entry moves "judged by structural measures" from *Left* to *Done*, with what was measured.
   - `docs/roadmap/overnight/the-judge-almost-never-decides.md` is this definition, with "Where it stopped" appended.
   - The measurement: on the `slow_world` of `tests/test_slowjudge.py`, the share of unmoved structural changes that end decided after a week of record, before and after, reported as measured (lesson-8). The no-difference case of the slowjudge table (k 0.05 → 0.0501) must still read 0/0/20 inconclusive.

## Files to touch

- `ergostat/numbers/unmoved.py` (new): `exercised_now(...)`, `judged(p, x, spec, nd, since, now) -> (verdict|None, why, card|None, version)`
- `ergostat/numbers/judge.py`:
  - `compare` adds `same`;
  - `run` routes to `unmoved` after `decide` would wait or give up on an unmoved change;
  - `owners` checks `verdict.on`;
  - the docstring.
- `ergostat/numbers/scorecard.py`: `fit_counts` in `score` and `verdict`; the coherence `measurable` flag and its use in `verdict`
- `docs/SPEC.md` (§12e), `docs/GAPS.md`, `docs/roadmap/overnight/the-judge-almost-never-decides.md`
- `tests/test_unmoved.py` (new); `tests/test_redesign.py`, only if a test named the old coherence-error behaviour

## Risks

- **lesson-1:** the scorecard reads the model files, decides, and then writes the verdict. Points 1-6 hold `pr.locked(p)` across all three against ergostat's writers, and use a version stamp for hand edits. Test: `test_a_model_edited_before_the_scorecard_reads_gets_no_verdict`.
- **lesson-2:** using the pass's `spec` (read at the start of `run`) as "the version judged". Stamp and compare, for equality, the version actually read. Tests: `test_a_model_edited_before_the_scorecard_reads_gets_no_verdict`, `test_a_verdict_carries_the_version_the_scorecard_read`.
- **lesson-3:** several inputs can be missing:
  - the coherence record (an error on either side),
  - the fit (unmeasurable),
  - the stocks' readings (exercised or not),
  - the compile (errors).

  Each must fail closed: count neither way, wait, or fail. Tests: `test_coherence_that_cannot_be_compared_never_makes_it_better`, `test_a_fit_unmeasurable_before_and_after_never_makes_it_better`, `test_an_unmeasurable_scorecard_stays_under_test_and_says_why`, `test_a_change_leaving_the_model_uncompilable_is_failed`, `test_a_record_that_did_not_exercise_it_still_waits`.
- **lesson-5:** parameter ids come from their subject, so a remade change could keep an old `verdict.on` or scorecard. Both live inside `verdict` and are replaced whole. Test: `test_a_remade_change_keeps_no_structural_pass`.
- **lesson-8:** the claims that "only structural measures pass it", "identical is exact" and "never written by the policy" each need a test that fails if the claim is false. Tests: `test_a_fit_only_improvement_is_inconclusive`, `test_identical_means_exactly_equal`, `test_a_pass_on_structure_is_never_written_by_auto`. The measured numbers are reported as measured.
- **lesson-9:** for each test below, the report names the guarded line broken and the test seen failing.
- **lesson-12:** the report lists all five points of the earlier plan review against points 1-6 here.
- **lesson-13:** a suite failure in code this change does not touch is named and left alone.
- **lesson-4:** no new count. Structural judging is bounded by the existing `MOST`, with no new loop or concurrency.

## Acceptance tests

All in `tests/test_unmoved.py` unless named otherwise, on a small model with a fixed `at` (no sleeps: lesson-10).

- `test_an_unmoved_change_that_answers_a_finding_is_passed_on_structure`: a structure change (e.g. a flow that joins two pieces of a kind's chain without changing any replayed stock), on a record that exercises its stocks, ends **passed** at its first decided look, with `verdict.on == "structure"` and a scorecard. It fails on main, which leaves the change testing and then inconclusive. Break: route `same` back to the wait.
- `test_an_unmoved_change_that_is_structurally_worse_is_failed`: one that introduces a finding (or splits a chain) ends **failed**, its why naming it. Break: map mixed or worse to inconclusive.
- `test_measured_and_unchanged_is_inconclusive`: nothing moves, and coherence and the fit are both measured, so the change is **inconclusive** at once with "no structural measure moves". Break: return under test instead.
- `test_a_fit_only_improvement_is_inconclusive`: the only thing the scorecard sees move is the fit made measurable or improved. Through the judge, the change is not passed. Directly, `scorecard.verdict(card, fit_counts=False)` is not "better". Break: remove the `fit_counts` guard in `verdict`.
- `test_coherence_that_cannot_be_compared_never_makes_it_better`, in two cases:
  - (a) no kind is compared before or after;
  - (b) coherence raises on the after side while the before side had mismatches (monkeypatch `coherence.compare`).

  Neither may be "better", and the card says `measurable: False`. Break: drop the error check, after which (b) reads "mismatches fewer" and passes.
- `test_a_fit_unmeasurable_before_and_after_never_makes_it_better`: with both fits `None` and nothing else moving, the verdict is not "better", and the change stays under test (see next). Break: count `measurable_after` as good.
- `test_an_unmeasurable_scorecard_stays_under_test_and_says_why`: coherence errors, the fit is unmeasurable and nothing moves. The change stays **testing**, with `undecided` naming coherence and the fit. At `horizon(needs)` it is inconclusive, naming them. Break: return inconclusive at once.
- `test_a_change_leaving_the_model_uncompilable_is_failed`: an unmoved change whose model fails to compile is **failed**, and no scorecard is worked out. Break: skip the error check, after which the scorecard runs or the change passes.
- `test_identical_means_exactly_equal`: a parameter change that moves one stock's replay by about 1e-9 is judged by the bound (no `verdict.on`), and the same change with an exactly equal replay takes the structural path. Break: compare with a tolerance (`math.isclose`).
- `test_a_record_that_did_not_exercise_it_still_waits`: `same` holds, but what the change touches is quiet (or has no readings). The change waits with today's "waits for record in which it moves" and gets no scorecard. Break: drop the exercised check.
- `test_a_model_edited_before_the_scorecard_reads_gets_no_verdict`: monkeypatch the step in `unmoved` that reads the model from disk so that it first writes a hand edit to the model file. No verdict event is recorded, and the next pass supersedes the change. Break: stamp `ver.version(spec)` from the pass start.
- `test_a_verdict_carries_the_version_the_scorecard_read`: monkeypatch so that a hand edit lands after the read and before the event. The verdict's `version` is the one read, `pr.accept` then refuses the change ("the model has changed"), and the judge does not write it. Break: stamp after the event.
- `test_a_pass_on_structure_is_never_written_by_auto`: with `accept: {structure: auto, parameter: auto}`, a change passed on structure stays passed and is not accepted; `owners(x)` is true. Break: remove the `verdict.on` check in `owners`.
- `test_a_remade_change_keeps_no_structural_pass`: a parameter change passed on structure is superseded, made again under the same id, then passed by the record under `auto`. It is written, and no `verdict.on` survives. Break: store `on` or the scorecard top-level, outside `verdict`.
- These must still pass:
  - all of `tests/test_slowjudge.py` (the no-difference case stays inconclusive);
  - `tests/test_redesign.py`;
  - `tests/test_bench.py::test_the_judge_never_writes_a_worse_or_neutral_change`;
  - the judge's tests in `tests/test_improve.py` and `tests/test_gate.py`.
- Done also needs: the unit suite and the four browser files at rc 0 with no page test skipped for want of a port, ruff clean, and origin/main merged in with the suites run again (lesson-7).

## Size budget

200 net lines of code outside `tests/` and `docs/`: `unmoved.py` about 110, `judge.py` about 40, `scorecard.py` about 30, with 20 to spare. An overrun is written with its reason.

## Notes from the plan review (answer each)

- Point 5 fails open (lesson-3). A coherence error or fit that is unmeasurable only on the after side counts 'neither way', so a change that breaks coherence while resolving one finding is passed on structure. A measure measurable before and unmeasurable after must count as worse (mixed, so failed), or at least block 'better' and stay under test naming it. 'Neither way' applies only when it is unmeasurable on both sides. Add test_coherence_lost_after_the_change_blocks_a_pass (finding resolved plus coherence error after only, so not passed; break: treat a one-sided error as neutral) and the same test for the fit.
- Point 1: state that NaN in a replay makes same false (fail-closed) and test it.
- Reword the break for test_a_verdict_carries_the_version_the_scorecard_read to 're-read ver.version() at event write'.
- Point 2: define nd['stocks'] for a flow-only structure change. The fallback 'any stock both replay' can count unrelated busy stocks as exercised, so narrow it or justify it.
- test_a_fit_only_improvement_is_inconclusive should assert inconclusive, not only 'not passed'.
- Say whether the scorecard under test is recomputed every pass until the horizon or cached by version.

## Where it stopped

Built, round 1: points 1-8, every acceptance test named above, the two the plan review added, and the measurement.
108 net lines of code outside `tests/` and `docs/` (`unmoved.py` 70, `judge.py` +21, `scorecard.py` +17), within
the 200 budget.

**What runs.** `judge.compare` returns `same` (both replays follow the same set of stocks, the same buckets of each,
every reading equal by float `==`; empty replays are never `same`; a NaN is never equal). `judge.run` routes to
`unmoved.judged` when `same`, `held + 1 s >= needs` (the same second of grace `due` gives) and
`unmoved.exercised_now` names a stock; otherwise `decide` runs as before. `unmoved.judged` reads the model from disk
(`_read`), stamps `ver.version` of what it read and records nothing when that is not `x["version"]`; compiles the
model it leaves with findings (an error fails it, no scorecard); scores with `fit_counts=False`; maps better to
passed, anything else that moved to failed, nothing moved and all measured to inconclusive, nothing moved with
coherence or the fit unmeasurable to under test (inconclusive at `horizon(needs)`). The verdict holds `on`,
`scorecard` and `version`, inside `verdict` only. `owners` is true for `verdict.on == "structure"`.

**Choices made alone (the most reversible, each one line to change):**
- *Point 2's fallback is narrowed* (the review's note): only `nd["stocks"]` counts. A change whose neighbourhood holds
  no stock is never taken as exercised and waits as today; "any stock both replay" would let a busy stock elsewhere
  vouch for it. For a flow-only structure change `nd["stocks"]` is `gate.stocks_of` of the flow in the model as it is
  and with the change: the flow's own stocks, one link on (in the tests, a flow out of an unread stock is exercised
  only through `stock.queue`, named in its `parts`). A stock read fewer than 12 times in the record held out is not
  exercised (`exercised.quiet` leaves such a stock out, which would otherwise read as exercised: lesson-3).
- *A one-sided loss counts against* (the review's first note). Coherence unmeasurable on either side
  (`coherence()` error, or no kind compared) is `measurable: False` with `says`, and no coherence gain (mismatches
  fewer, coherence up) counts; a kind compared before and not after is still "coherence down", so a change that
  resolves a finding and loses coherence is mixed, so failed. The fit measurable before and not after was already
  "the fit worse". Only unmeasurable on both sides (or on the before side alone) counts neither way. For the fit's
  "measured" in the inconclusive/under-test choice, both sides must be measurable: a fit made measurable alone keeps
  the change under test, it never passes it.
- *The scorecard under test is worked out again at each due look* (the review's last note), not cached: the looks are
  `due`'s (the record it needs, then a quarter more each time), bounded by `MOST` a pass, and the record and
  coherence change between looks.
- *Two existing tests named the old path* and were updated (not in "Files to touch"; the slowjudge branch did the
  same): `test_improve.py::test_a_structural_change_waits_for_the_owner_even_passed` (was "answers 2 findings", now
  passed on structure, better, and `owners`) and `test_gate.py::test_a_simpler_change_no_worse_passes` (was "simpler,
  and no worse", now passed on structure, better, a part removed). Both changes still pass and still wait for the
  owner.

**The plan review's notes, answered:**
1. One-sided unmeasurable: counts against (above); `test_coherence_lost_after_the_change_blocks_a_pass` and
   `test_the_fit_lost_after_the_change_blocks_a_pass`.
2. NaN: makes `same` false, stated in `compare`'s docstring and SPEC, tested in `test_identical_means_exactly_equal`.
3. The break of `test_a_verdict_carries_the_version_the_scorecard_read` was run as "re-read `ver.version()` at event
   write".
4. `nd["stocks"]` for a flow-only change: defined, and the fallback narrowed (above).
5. `test_a_fit_only_improvement_is_inconclusive` asserts inconclusive through the judge, and directly that the same
   card is "better" with `fit_counts=True` and "no better" with it off.
6. Recomputed at each due look, not cached (above).

**Lesson-9, each guarded line broken and the test seen failing** (each break reverted; `git diff` empty after):
- `same` routed back to the wait (`if False and ev["same"]`): 14 of 16 failed, among them
  `test_an_unmoved_change_that_answers_a_finding_is_passed_on_structure` (no `verdict.on`).
- mixed or worse mapped to inconclusive: `test_an_unmoved_change_that_is_structurally_worse_is_failed` and the two
  one-sided-loss tests failed.
- unchanged and measured returned under test: `test_measured_and_unchanged_is_inconclusive`,
  `test_a_fit_only_improvement_is_inconclusive`.
- the `fit_counts` guard removed in `verdict`: `test_a_fit_only_improvement_is_inconclusive` (the direct check).
- the coherence `measurable` check dropped in `verdict`: `test_coherence_that_cannot_be_compared_never_makes_it_better`
  (b) read "2 coherence mismatches fewer".
- a one-sided coherence error treated as neutral (`coh_down` cleared too): `test_coherence_lost_after_the_change_blocks_a_pass`
  passed the change. The fit measurable before and not after taken as not worse: `test_the_fit_lost_after_the_change_blocks_a_pass`.
- the fit taken as measured when it is not: `test_a_fit_unmeasurable_before_and_after_never_makes_it_better`,
  `test_an_unmeasurable_scorecard_stays_under_test_and_says_why`. Inconclusive at once instead of at the horizon:
  the same two.
- the compile check skipped: `test_a_change_leaving_the_model_uncompilable_is_failed`.
- `math.isclose` in `same`: `test_identical_means_exactly_equal`, both through the judge (the 1e-9 change took the
  structural path) and directly. (Its first version caught it only directly: its "structure" assertion could not see
  "structural"; tightened, and seen failing through the judge too.)
- the exercised check dropped: `test_a_record_that_did_not_exercise_it_still_waits`.
- `ver.version(spec)` of the pass start stamped: `test_a_model_edited_before_the_scorecard_reads_gets_no_verdict`.
- `ver.version()` re-read at event write: `test_a_verdict_carries_the_version_the_scorecard_read`.
- the `verdict.on` check removed in `owners`: `test_a_pass_on_structure_is_never_written_by_auto` (and the two
  version/remade tests, written by `auto`).
- `on` and the scorecard stored top-level with `owners` reading them there: `test_a_remade_change_keeps_no_structural_pass`
  (the remade change was not written).

**Measured** (`tests/test_unmoved.py::test_measured_on_the_slow_world`: the slow queue of `test_slowjudge.py`, 5
records each, a week of record after each change, the judge every 6 hours; "before" is this branch with the
structural path switched off, which leaves main's path exactly):

| change (its replay the model's) | before: passed / failed / inconclusive / undecided | after |
|---|---|---|
| answers a finding (`served` no longer fills an undrained stock) | 5 / 0 / 0 / 0, at 24 h, by "answers a finding" on the record | 5 / 0 / 0 / 0, at 24 h, on structure |
| makes a finding (`served` fills a stock nothing drains) | 0 / 5 / 0 / 0, at 24 h, by "makes a new finding" | 0 / 5 / 0 / 0, at 24 h, on structure |
| moves no measure (a described stock and its outflow) | 0 / 0 / 0 / 5 | 0 / 0 / 0 / 5 |
| answers a finding, opens a note, removes nothing | 5 / 0 / 0 / 0, at 24 h | 5 / 0 / 0 / 0, at 24 h, on structure |
| no difference, k 0.05 → 0.0501 (moves the replay; 20 records, hourly) | | 0 / 0 / 20 inconclusive |

So on this record the share of unmoved structural changes decided within a week did not change: 10 of 20 both ways.
What changed is what they are decided on and who writes them. Before, a change whose replay is the model's was
passed by the record's "no worse, and it answers a finding" (a bound of zero width, since nothing moved), so under
`accept: {structure: auto}` main's `owners` would not have held the fourth row's change back from being written
(read from the code; the measurement ran with the default `owner` policy). Now it is passed on the
scorecard and waits for the owner. The definition's "it fails on main, which leaves the change testing and then
inconclusive" is not what main does with a change that answers a finding: main passes it. The test still fails on
main, on its `verdict.on` assertion. A change that moves no measure stays undecided after a week both ways here:
this model has no items, so coherence is never measurable, and the last look in a week (150 h) comes before the
horizon (168 h). The path that decides such a change at once (every measure measured: inconclusive) is shown only
with coherence and the fit measured by monkeypatch (`test_measured_and_unchanged_is_inconclusive`), not on a real
record.

**The window left (point 6).** In the same pass the judge's model is the one it loaded, so the protection against a
hand edit between the scorecard's read and the event is `owners` (point 7): the judge never writes a pass on
structure. The owner's Accept, on the model read again, refuses it ("the model has changed"), and the next pass
supersedes it. Both are tested.

**Not run, or not clean:**
- The whole unit suite and the four browser files were not run here: the run instructions leave the fast suites to
  the factory, and this session's permissions refused `scripts/suite_watch.py`. Run here, one file set at a time:
  `tests/test_unmoved.py` (17 passed), `test_slowjudge.py`, `test_redesign.py`, `test_improve.py`, `test_gate.py`,
  `test_bench.py` (all), and every other file that runs the judge or the scorecard (`test_churn`, `test_exercised`,
  `test_extremes_closed`, `test_intent`, `test_modelling_core`, `test_modelling_core2`, `test_parity`,
  `test_redesign_bench`, `test_redesign_memory`, `test_self_improve`): 171 passed, 0 failed.
- `demo_check`: no example touched.
- origin/main (lesson-7): this clone has no `origin` remote; the local `main` is an ancestor of the branch (nothing
  to merge). The factory should merge the real origin/main and run the suites again.
- A `scratch_probe.py` was left at the worktree's root (a probe that could not be run; this session could not delete
  it). This said it was not committed, which was false: the factory's commit 6bd6c9f8 ("work the session left
  uncommitted") committed it. See round 2.

### Round 2 (answering review/the-judge-almost-never-decides-1)

Every finding of the review, blocking and not (lesson-12):

1. **Blocking: `scratch_probe.py` is committed** (6bd6c9f8). It must not reach main. This round could not remove it:
   the session's permissions refused `git rm scratch_probe.py` (and every other way of deleting a file), and a
   revert of 6bd6c9f8 would be the same deletion by another route, so it was not tried. The false sentence above is
   corrected. **Left:** whoever runs this branch next must `git rm scratch_probe.py` and commit it before the
   merge. Nothing in `ergostat/` or `tests/` imports it.
2. **`held + 1.0 >= nd["needs"]`** (`judge.py:554`), a second earlier than the definition's `held >= needs`: kept (it
   is the grace `due` gives, so a look due at the record it needs is not put off by a rounding), and SPEC §12e now
   says so.
3. **A version read that is not the change's, or a `TrialError`, takes a `MOST` slot each pass with no event**
   (`judge.py:559-560`): kept as it is. `run` supersedes at the start of every pass on `p.model.spec`, so on the next
   pass, with the model read again, the change is superseded and takes no slot. Not counting it against `MOST` would
   let such changes be scored without a bound (lesson-4), which is worse than spending a look. SPEC §12e now says it
   takes one of the pass's looks until then. Not tested further here: a model loaded once and never read again by
   the caller would keep spending the slot, as the review says; that is the caller's model cache, not this gap.
4. **Coherence unmeasurable on the before side only** (`scorecard.py:263`) counts neither way, apart from more
   mismatches after, which count against it (`verdict`: `net_m = min(net_m, 0)`). It can never make a change better,
   so it fails closed. The claim is narrowed to the accurate one: SPEC §12e says unmeasurable coherence "never counts
   for the change", a kind compared before and not after counts against it, and unmeasurable before only never makes
   it better while mismatches after still count against it. The "a one-sided loss counts against" line above holds
   for the after side (the plan review's case); for the before side it is "never for", as this item says.

No code changed in this round, so the size stays at 108 net lines.

### After round 2: the factory's `unit` run failed

The factory reported `unit` failed. The tail it gave stops at 32% with no failing test, no error and no summary
line, which is what a run that was stopped looks like (a kill by the watchdog or the slot), not a test that failed.
What this session could check:

- The whole unit suite, run serially here (`uv run python -m pytest -q -x -p no:randomly`; this session's
  permissions refused `scripts/suite_watch.py`, and the house rules forbid running it in parallel by hand):
  **1948 passed, 69 skipped, 0 failed, in 22 min 53 s**. The slowest test is `test_reload_soak.py` (124 s);
  this branch's `test_measured_on_the_slow_world` takes 9.4 s alone, under the `slow` mark's 10 s.
- `uv run ruff check ergostat tests scripts`: clean.

So no failing test was found, and no code changed. Not known: why the parallel run stopped. The watchdog's JSON
line (peaks, and whether it killed the run) was not in the tail. If it was a kill on threads or memory, this
branch's tests start no threads or servers. They hold more than 60 small worlds in one test, which is memory and
not threads. Run under the watchdog, its peaks would say. **Left:** the factory should run `unit` again under
`suite_watch.py` and read its last line. If a test fails there, it should be named here.

`scratch_probe.py` is still committed. This session's permissions refused `git rm scratch_probe.py` again, run on
its own, so the round-2 blocking finding is still open. Whoever can delete files must run `git rm scratch_probe.py`
and commit it before the merge.

### Round 3 (the one blocking finding: `scratch_probe.py`)

The queue's only blocking finding is that `scratch_probe.py` is still committed. This round tried
`git rm -q scratch_probe.py` first, and this session's permissions refused it, as in rounds 1 and 2. It was not
worked around: overwriting the file with nothing would still leave a scratch file at the root, and a revert of
6bd6c9f8 is the same deletion. No code changed, so the size stays at 108 net lines and the suites' results above
stand. **Left, and it blocks the merge:** a session or person allowed to delete files runs
`git rm scratch_probe.py && git commit -m "the-judge-almost-never-decides: remove the scratch probe"`. Nothing in
`ergostat/` or `tests/` imports it, so no test changes with it. Still also left: the factory's `unit` run under
`suite_watch.py`, the four browser files, and the merge of the real origin/main (this clone has no `origin`).

### Round 4 (the same blocking finding)

Checked again: nothing in `ergostat/`, `tests/` or `scripts/` imports `scratch_probe.py`. `git rm -q scratch_probe.py`
was refused by this session's permissions for the fourth time, and it was not worked around by another route
(revert, `--cached`, emptying the file): that would get around the same refusal. No code changed. The branch should
not go to a fifth implementor round on this finding alone. A session or person who is allowed to delete files must
run `git rm scratch_probe.py` and commit it. The merge queue also needs to run the unit suite under
`suite_watch.py`, the four browser files and the real origin/main merge.

## Where it stopped

Parked by the factory (review/the-judge-almost-never-decides-4, 2026-11-20 19:15).

The implementation is done and, read without running it, meets the definition of done: exact `same` in compare; the structural path in unmoved.py under pr.locked with a version stamp read from disk; fit_counts and coherence `measurable` in scorecard.py; owners() checks verdict.on; every acceptance test present by name, including the plan review's one-sided coherence and fit tests; about 134 of 200 lines. Left: (1) `git rm scratch_probe.py` and commit, which the factory session cannot do (four rounds refused); (2) the merge queue runs tests/test_unmoved.py, the regression files, the unit suite, the four browser files and ruff after merging origin/main. It stops because another automated fix round will hit the same permission refusal: a person must delete the file. After that the branch can go straight to review for merge.

### Resumed, round 1 (2026-11-21, after main merged in at fdf27b73)

- `git rm -q scratch_probe.py` was tried first and refused by this session's permissions (the fifth refusal). It was
  not worked around by another route. **Still left, and it blocks the merge:** a person or a session allowed to delete
  files runs `git rm scratch_probe.py` and commits. Nothing imports it.
- Run here on the branch with main merged in, one file set at a time: `tests/test_unmoved.py` (17 passed);
  `test_slowjudge.py`, `test_redesign.py`, `test_improve.py`, `test_gate.py`, `test_bench.py` (93 passed, 0 failed);
  `uv run ruff check ergostat tests scripts` clean. No code changed in this round.
- Not run here: the whole unit suite and the four browser files under `suite_watch.py` (left to the factory). This
  clone has no `origin`, so the real origin/main merge is also left to the merge queue.

### Resumed, round 2 (2026-11-21)

- Checked again: nothing in `ergostat/`, `tests/` or `scripts/` names `scratch_probe.py`.
- `git rm -q scratch_probe.py` was refused by this session's permissions (the sixth refusal). Other routes (a revert,
  `--cached`, emptying the file) were not tried: they would get around the same refusal. No code changed, no test was
  re-run (nothing changed since resumed round 1).
- **Still blocking the merge, and only a person can do it:** `git rm scratch_probe.py && git commit`. Every factory
  session so far has been refused file deletion, so another automated round will not clear it. After that commit,
  the branch can go to review for merge, and the merge queue runs the suites under `suite_watch.py` after merging the
  real origin/main.

### After resumed round 2: the factory's `unit` run "failed"

- The tail it gave is only uv's build lines ("Built ergostat", "Installed 1 package") with no pytest output: not one
  dot, no failing test, no error, no summary. The run stopped before pytest printed anything, so it was stopped from
  outside (the slot or the watchdog) or failed to start. It was not a test failing. `pyproject.toml` has
  `testpaths = ["tests"]`, so `scratch_probe.py` (at the root, not named `test_*`) is not collected and did not cause it.
- Run here again, one file set at a time: `tests/test_unmoved.py` 17 passed; `test_slowjudge.py`, `test_redesign.py`,
  `test_improve.py`, `test_gate.py`, `test_bench.py` 93 passed; ruff clean. The last whole serial unit run (round 2)
  was 1948 passed, 0 failed. No failing test was found, so no code changed. The tests' bounds were not touched.
- `git rm -q scratch_probe.py` was refused again (the seventh refusal), and no other route was tried.
- **Left:** the factory runs `unit` again under `suite_watch.py` and reads the watchdog's last JSON line (whether it
  killed the run, and its peaks). A person runs `git rm scratch_probe.py` and commits.

### Resumed, round 3 (2026-11-21)

This session was refused every Bash call, starting with the first one (`git rm -q scratch_probe.py`). So it could not
delete the file, commit, run a test or run ruff. It did not try another route around that. Only file edits were
possible, and these edits are **not committed** by this session.

Review/the-judge-almost-never-decides-5 and -6, every finding (lesson-12):
1. **Blocking: `scratch_probe.py` is committed.** Still there, eighth refusal. Only a person can clear it:
   `git rm scratch_probe.py && git commit`. Nothing imports it.
2. **The reviewers did not run the suites.** Not run here either (no Bash). The last runs are the ones above (17 and
   93 passed, ruff clean, the serial unit run 1948 passed). The merge queue runs them under `suite_watch.py` after
   merging origin/main.
3. **`judge.py:556-560`, a `TrialError` from `un.judged` goes to waiting with no event.** I did not change it. A
   code change that nobody can test or commit this round would reach the branch unverified, and the review called it
   non-blocking. The most reversible fix, for the next session that can run tests: in the `except`, set
   `v = x.get("version")`. The change then takes the `verdict is None` branch and records a `testing` event whose
   `undecided` names the error. It is still bounded by `MOST`, and a hand edit is still caught on the next pass by
   `supersede`. It needs a test that monkeypatches `tr.compiled` to raise `TrialError` and checks the testing event.
4. **Docs should say the scorecard under test is recomputed, not cached.** SPEC §12e already said "worked out again
   at each look". GAPS now says it too.
5. **The narrowing of point 2's fallback should be named as a deliberate departure.** SPEC §12e and GAPS now name it:
   a change whose neighbourhood holds no stock is never taken as exercised, which is narrower on purpose than "any
   stock both replay".
6. **`held + 1.0 >= needs`.** The review called it harmless, and SPEC already says it. Unchanged.

No code changed, so the size stays as it was. **Left:** the person deletes `scratch_probe.py` and commits these doc
edits with it; finding 3 above, if the review wants it before the merge; the suites under `suite_watch.py` after the
origin/main merge.

### Resumed, round 3 (2026-11-21, the factory's scratch-file gate)

- The gate refused the build on `scratch_probe.py` alone. Checked again: nothing in `ergostat/`, `tests/` or
  `scripts/` names it.
- `git rm -q scratch_probe.py` was refused by this session's permissions (the eighth refusal), and no other route
  was tried: they would get around the same refusal. No code changed and no test was run.
- **Left, and only a person can do it:** `git rm scratch_probe.py`, then commit it together with this file's
  uncommitted doc edits. Another automated round will be refused the same way.
- Tried once more in the same round: every Bash call was refused (the ninth refusal), so nothing was deleted,
  committed or run. Nothing in `ergostat/`, `tests/` or `scripts/` names `scratch_probe.py` (checked by search).

### Resumed, round 4 (2026-11-21)

- The first Bash call (`git rm -q scratch_probe.py`) was refused by this session's permissions: the tenth refusal.
  No other route was tried (a revert, `--cached`, emptying the file), since each would get around the same refusal.
  So nothing was deleted, committed or run. This edit is **not committed** by this session.
- Checked again by search: nothing in `ergostat/`, `tests/` or `scripts/` names `scratch_probe.py`.
- No code changed, so the size and the last test results stand (17 and 93 passed, ruff clean, the serial unit run
  1948 passed). The non-blocking finding about `TrialError` at `judge.py:556-560` stays as resumed round 3 describes.
- **Left, and only a person can do it:** `git rm scratch_probe.py && git commit`. Ten automated rounds have been
  refused the same way, so this item should not get another implementor round. After that commit the merge queue
  merges origin/main and runs the suites under `suite_watch.py`.

### Resumed, round 4, the scratch-file gate again (2026-11-21)

- The gate refused the build on `scratch_probe.py` again. `git rm -q scratch_probe.py` was refused by this session's
  permissions, the eleventh time ("don't ask" mode refuses every Bash call). No other route was tried. Nothing was
  deleted, committed or run, and this edit is **not committed** by this session.
- Search again: nothing in `ergostat/`, `tests/` or `scripts/` names `scratch_probe.py`. No code changed.
- **Left, and only a person can do it:** `git rm scratch_probe.py && git commit`, along with this note.
- Same gate, the next round: `git rm -q scratch_probe.py` was refused a twelfth time ("don't ask" mode). Nothing
  deleted, committed or run; this line is not committed by this session.

### Resumed, round 5 (2026-11-21)

- The first Bash call (`git rm -q scratch_probe.py`) was refused by this session's permissions ("don't ask" mode):
  the thirteenth refusal. No other route was tried (revert, `--cached`, emptying the file), since each would get
  around the same refusal. Nothing was deleted, committed or run; this note is **not committed** by this session.
- Searched again: nothing in `ergostat/`, `tests/` or `scripts/` names `scratch_probe.py`. No code changed, so the
  size and the last results stand (17 and 93 passed, ruff clean, serial unit run 1948 passed). The non-blocking
  `TrialError` finding (`judge.py:556-560`) stays as resumed round 3 describes. It was left alone because a change
  that can't be tested or committed would land on the branch unverified.
- **Left, and only a person can do it:** `git rm scratch_probe.py && git commit`, along with the uncommitted doc
  edits. Then the merge queue merges origin/main and runs the suites under `suite_watch.py`. This item should not
  be sent to another automated round, because each one has been refused the same way.
- Round 5, the scratch-file gate again: `git rm -q scratch_probe.py` was refused a fourteenth time ("don't ask"
  mode). No other route was tried. Nothing deleted, committed or run; this line is not committed by this session.
- Round 5, the gate once more: refused a fifteenth time, the same way. Nothing deleted, committed or run.

### Resumed, round 6 (2026-11-21)

- The first Bash call (`git rm -q scratch_probe.py`) was refused ("don't ask" mode): the sixteenth refusal. No
  other route was tried. Nothing was deleted, committed or run; this note is **not committed** by this session.
- Searched again: nothing in `ergostat/`, `tests/` or `scripts/` names `scratch_probe.py`. No code changed.
- **Left, and only a person can do it:** `git rm scratch_probe.py && git commit`, with the uncommitted doc edits.
  Then the merge queue merges origin/main and runs the suites under `suite_watch.py`. Do not send this item to
  another automated round.
- Round 6, the scratch-file gate again: `git rm -q scratch_probe.py` was refused a seventeenth time ("don't ask"
  mode). No other route was tried. Nothing deleted, committed or run; this line is not committed by this session.
- Round 6, the gate once more: refused an eighteenth time, the same way. Nothing deleted, committed or run.

### Resumed, round 7 (2026-11-21)

- The first Bash call (`git rm -q scratch_probe.py`) was refused ("don't ask" mode): the nineteenth refusal. No
  other route was tried (revert, `--cached`, emptying the file), since each would get around the same refusal.
  Nothing was deleted, committed or run; this note is **not committed** by this session.
- Searched again: nothing in `ergostat/`, `tests/` or `scripts/` names `scratch_probe.py`. No code changed, so the
  size and the last results stand. The non-blocking `TrialError` finding (`judge.py:556-560`) stays as resumed
  round 3 describes, for a session that can run its test.
- **Left, and only a person can do it:** `git rm scratch_probe.py && git commit`, with the uncommitted doc edits.
  Then the merge queue merges origin/main and runs the suites under `suite_watch.py`.
- Round 7, the scratch-file gate: `git rm -q scratch_probe.py` was refused a twentieth time ("don't ask" mode). No
  other route was tried. Nothing deleted, committed or run; this line is not committed by this session.
- Round 7, the gate once more: refused a twenty-first time, the same way. Nothing deleted, committed or run.

### Resumed, round 8 (2026-11-21, main 9acc11c2 merged in)

- **The merge.** `judge.py` conflicted only in its imports: main added `version as ver` (for its new check, under the
  lock, that the files on disk are the model loaded) and the branch added `unmoved as un`. Both kept, committed as
  96f24c13. Main's check runs before the structural path in the same lock, and they do not interact.
- **What main's merge broke, and why.** With main merged in, `test_a_model_edited_before_the_scorecard_reads_gets_no_verdict`
  and `test_a_verdict_carries_the_version_the_scorecard_read` failed on their last assertion only: "the next pass
  supersedes the change". Main's `proposals-superseded-by-any-edit` now *carries* an open change over a hand edit
  that leaves its subject alone (here the edit is to `k`), so the next pass moves the change to the edited version,
  clears its verdict and judges it again. That is lesson-7, and the right result: the old verdict is never used for
  the new model. The two tests now assert main's behaviour: carried to the version on disk, judged again, the new
  verdict stamped with that version, and (in the second) still not written by `auto`. Their first-pass assertions,
  which guard this branch's lines, are unchanged. Seen failing again (lesson-9): stamping `ver.version(spec)` from
  the pass start fails the first; re-reading `ver.version()` at event write fails the second. Both breaks reverted.
  SPEC §12e and the `judge.py`/`unmoved.py` docstrings now say "carried or superseded" where they said "superseded".
- **The review-6 `TrialError` finding (`judge.py:563-564`), fixed now that this session can run tests.** A
  `TrialError` from `un.judged` now keeps the change under test with a `testing` event whose `undecided` says "its
  edit could not be tried on the model (...)", where before it waited with no event. That is one line. New test:
  `test_an_edit_that_cannot_be_tried_stays_under_test_saying_why`, seen failing with the old line back. SPEC says it.
- **`scratch_probe.py`:** `git rm -q scratch_probe.py` was refused again ("don't ask" mode), the twenty-second time,
  and no other route was tried. **Still blocking the merge:** a person runs `git rm scratch_probe.py && git commit`.
- **Run here, one file set at a time:** `tests/test_unmoved.py` 18 passed; `test_slowjudge`, `test_redesign`,
  `test_improve`, `test_gate`, `test_bench` with it, 111 passed; ruff clean. These 14 files run together:
  `test_churn_carry`, `test_churn`, `test_review`, `test_backlog`, `test_modelling_core`, `test_modelling_core2`,
  `test_modelling_ai_cap`, `test_exercised`, `test_extremes_closed`, `test_intent`, `test_parity`,
  `test_redesign_bench`, `test_redesign_memory`, `test_self_improve`, 199 passed and 1 failed:
  `test_modelling_ai_cap.py::test_two_runs_cannot_both_take_the_last_of_the_cap`. Main added that file, and it tests
  `modeller_spend`, which this branch does not touch. Run alone, the file passes 22 of 22, so the failure appears
  only when it runs with other files (lesson-10/13). It is named here and left alone. Not run: the whole unit suite
  and the four browser files under `suite_watch.py` (left to the factory).
- Round 8, the scratch-file gate: the merge of main was already committed (96f24c13; main is an ancestor of HEAD, no
  conflict markers in `judge.py`). `git rm -q scratch_probe.py` was refused the twenty-third time ("don't ask"
  mode). No other route was tried. Only a person can clear it: `git rm scratch_probe.py && git commit`.
- Round 8, the gate again: the tree was clean and the merge already committed. `git rm -q scratch_probe.py` was
  refused the twenty-fourth time ("don't ask" mode); no other route was tried. Nothing in `ergostat/`, `tests/` or
  `scripts/` names it (searched). No code changed and no test was run.

### Resumed, round 9 (2026-11-21): the scratch file removed

- **The blocking finding is cleared.** `git rm -q scratch_probe.py` was allowed this time and is committed with this
  note. Nothing in `ergostat/`, `tests/` or `scripts/` names it (searched), so no test changes with it.
- Local `main` is an ancestor of HEAD (main is merged in). This clone has no `origin`, so merging the real
  origin/main is left to the merge queue.
- Run here, one file set at a time, after the removal: `tests/test_unmoved.py` 18 passed; `test_slowjudge.py`,
  `test_redesign.py`, `test_improve.py`, `test_gate.py`, `test_bench.py` 93 passed; `ruff check ergostat tests
  scripts` clean. No code changed in this round.
- **Left:** the merge queue merges origin/main and runs the whole unit suite and the four browser files under
  `suite_watch.py`. The cross-file failure named in round 8
  (`test_modelling_ai_cap.py::test_two_runs_cannot_both_take_the_last_of_the_cap`, main's file, outside this gap)
  is still left alone. After that the branch can go to review for merge.

### Continued, round 1 (2026-11-22)

- The gap's work is on main already (merge a1d1b941; `scratch_probe.py` removed in 8e210c62). This branch was made
  from main (de914e32) and had no difference from it before this note. Neither the queue nor any earlier review left
  an open finding.
- Run here on that main, one file set at a time: `tests/test_unmoved.py` 18 passed; `test_slowjudge.py`,
  `test_redesign.py`, `test_bench.py` 48 passed; `test_improve.py`, `test_gate.py` 48 passed; `ruff check ergostat
  tests scripts` clean. No code changed in this round.
- Not run here (left to the merge queue, as the house rules say): the whole unit suite and the four browser files
  under `suite_watch.py`. This clone has no `origin`, so the local `main` is the one merged in.
- Still left, outside this gap (GAPS *Left*): the information limit of a slow record. The cross-file failure named in
  round 8 (`test_modelling_ai_cap.py::test_two_runs_cannot_both_take_the_last_of_the_cap`) is in main's code and is
  left alone (lesson-13).
- The commit of this note (`git add docs/roadmap/overnight/the-judge-almost-never-decides.md && git commit`) was
  refused in this session ("don't ask" mode) when run in the same command as the append. Run on its own, it was
  allowed (3be27fb9).
