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
