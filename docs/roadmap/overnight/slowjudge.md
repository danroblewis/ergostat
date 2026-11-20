# slowjudge: the judge decides on a slow model, with its error rate stated

Branch `slowjudge`, from main at fdf83b9. Gap (`docs/GAPS.md`, *The judge almost never decides on a slow model*; the
owner, 2026-11-19: "on the work model nearly every change ended inconclusive"). The judge (`numbers/judge.py`, SPEC
§12e) passes a change only when it is better by the threshold in **every** window (the record held out, whole, in
halves, in quarters), each at least the dominant time constant long, with an absolute noise floor of 0.005 on scaled
errors. On a model whose stocks move over hours or days, or a sparse record, each window is one noisy draw: a small
effect never clears the floor (inconclusive after three times the record it needs), and a large one is decided by the
noise of three draws, with no error rate at all.

## Definition of done

1. **Reproduced and measured** on a synthetic slow world (a queue drained over about a day, arrivals at random,
   readings every 15 minutes: the work model's shape) and the fast one (`ergostat bench judge`): how often the judge
   decides, what, and after how much record, before and after.
2. **Pooled evidence with a stated error rate.** The judge replays the model as it is and with the change once over
   the whole record held out (warm, as now), pairs their errors reading by reading on what the change touches, and
   pools them in batches (batch means, corrected for the batches' own lag-one autocorrelation, so the replay's own
   error distribution is the noise model). It bounds the change's effect with an **always-valid confidence sequence**
   (a normal mixture: Robbins 1970; Howard et al. 2021), so looking again as the record grows does not inflate the
   error: a change no better than the model as it is is passed with probability at most `ALPHA` (5%), however often
   it is looked at. **Passed** when the bound excludes no improvement and the estimate is better by the threshold;
   **failed** when the bound excludes no harm and it is worse by the threshold (near it, elsewhere or on a goal's
   stock); the record **tells it from the model as it is by less than the threshold** (both bounds within it) is no
   longer a wait: answered findings or a simpler model pass it, else it is inconclusive at once.
3. **"Needs N more record", not repeated inconclusives.** A change the bound cannot decide yet says how much more
   record it needs (the bound narrows as one over the root of the record), on its testing event and in the waiting
   list; it stays under test while that is within a week of record held out, and is inconclusive, saying how much
   more, only past that.
4. The `windows` policy keeps its meaning for the reader: the verdict's evidence is the record whole, in halves and in
   quarters, sliced from the same replay.
5. SPEC §12e and the GAPS entry say so. 400 net lines of code at most.

## Acceptance tests

- `tests/test_slowjudge.py::test_a_worse_change_on_a_slow_record_is_never_passed` (many seeds; fails on main)
- `tests/test_slowjudge.py::test_a_better_change_on_a_slow_record_is_passed_within_a_bounded_record` (fails on main)
- `tests/test_slowjudge.py::test_an_undecided_change_says_how_much_more_record_it_needs`
- `tests/test_slowjudge.py::test_the_bound_holds_its_error_rate_however_often_it_is_looked_at`
- still passing: `tests/test_bench.py::test_the_judge_never_writes_a_worse_or_neutral_change`,
  `tests/test_bench.py::test_the_judge_passes_a_correct_delay_in_windows_shorter_than_its_settling`,
  `tests/test_bench.py::test_the_judge_is_not_fooled_by_a_stock_slowed_out_of_the_fit`, and the judge's tests in
  `tests/test_improve.py` and `tests/test_gate.py` (updated where they named the old rule).

## Not in this branch

Judging a change that cannot move the replay (structure, wiring) by structural measures, and a change carrying over
edits elsewhere: the GAPS entry's other two parts, left open.
