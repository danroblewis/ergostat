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

## Where it stopped

Done, all four suites green after the gate review's round (unit 1809 passed; the four browser files 218 passed, none
skipped; ruff on `ergostat` and `tests`: the 14 errors `ruff check` reports are in example scripts and on main as
well). 153 net lines of code. The table is after that round.

Measured: the synthetic world (the acceptance tests' `slow_world`; a week of record after each change, the judge
every hour, 20 seeds each), and the fast bench (`ergostat bench judge --seeds 10`, 120 trials, judged at 2, 4 and
6 hours).

| case (truth k; change) | before: passed / failed / other, median hours | after |
|---|---|---|
| queue (~40 jobs, 15-min readings), k 0.1 → 0.05 (better, twice off) | 19 / 1 / 0, 20 h | 20 / 0 / 0, 60 h |
| queue, k 0.06 → 0.05 (better by a fifth) | 9 / **11** / 0, 24 h | 5 / 0 / 15 undecided after a week, 72 h |
| queue, k 0.05 → 0.06 (worse by a fifth) | **6** / 14 / 0, 24 h | 0 / 5 / 15 undecided, 72 h |
| queue, k 0.05 → 0.0501 (no difference) | 0 / 0 / 20 inconclusive | 0 / 0 / 20 inconclusive |
| a few items (~2), k 0.15 → 0.1 (better) | 6 / **14** / 0, 14 h | 3 / **1** / 16 inconclusive, 42 h |
| a few items, k 0.1 → 0.15 (worse) | **3** / 17 / 0, 21 h | 0 / 2 / 18 inconclusive, 60 h |
| a few items, hourly readings, better | 6 / **14** / 0, 14 h | 3 / **2** / 15 inconclusive, 42 h |
| a few items, hourly readings, worse | **3** / 17 / 0, 40 h | 0 / 1 / 19 inconclusive, 100 h |
| fast bench (120 trials) | 0 false accepts, 0 false rejects, 70 decided, median 2 h | 0, 0, 50 decided, median 2 h |

Before, the judge decided almost everything on the slow world, and wrongly about a third of the time (false passes
15-30%). Now it never passed a worse change (0 of 60) and failed 3 better changes in 80 (about the stated 5% each way);
a change twice off is decided within a week, a change a fifth off mostly needs more than a week of this record
(stated as "needs about N more record"). The information is the limit: a day-long drain read every 15 minutes
holds about one independent draw a day.

Left: judging changes that cannot move the replay by structural measures; carrying a change over edits elsewhere.

### After the gate review (merge after fixes)

- **B1, what only accumulates.** A stock with no time constant keeps whatever it gets wrong, so once its noise drifts
  it is also taken as a walk (its steps from the record's successive differences, covariance min(i, j)), and the
  larger variance counts. The reviewer's probe passed 17% and failed 20% of equally good changes on a walk; through
  the judge's own path it now passes and fails 0.07% (1,500 records, looked at seven times each).
- **B2, the guarantee as it holds.** Stocks' standard errors add (correlated stocks are not taken as independent);
  the fail side's tests (near it, the rest, each goal's stock) share ALPHA (Bonferroni); the bound is two-sided at
  2·ALPHA by Ville, each way about ALPHA by symmetry; it is called a plug-in, asymptotic confidence sequence, valid
  under stationary AR(1) noise (or a walk). Measured on equally good changes, 1,500 records each, seven looks:

  | noise | passed | failed |
  |---|---|---|
  | AR(1), 0.97 a reading | 4.7% | 5.0% |
  | AR(1), far slower than the record, the model's time constant a quarter of the noise's | 3.1% | 3.9% |
  | a walk (no time constant) | 0.07% | 0.07% |
  | two stocks sharing their noise | 4.8% | 4.8% |
  | both replays wrong, mirrored | 4.3% | 5.8% |

  (`tests/test_slowjudge.py::test_the_bound_holds_its_error_rate_however_often_it_is_looked_at`, 300 records a
  case, allows ALPHA plus two standard errors of the trials.)
- **The noise's time scale** is now the time constant of whichever replay fits the record better (it was the slower
  of the two, which let a change that slows a part set it).
- **B3, the 20 fast-bench trials that stopped deciding** (`ergostat bench judge --seeds 10`, verdicts at 2, 4 and 6
  hours; main against this branch, trial by trial). They are **not** neutral or only slowed, as said before the review:
  they are the delay family's worse and slowed changes, which main failed and this branch leaves under test after six
  hours. None is written either way; no trial's written outcome changed, and no worse change passed.

  | world / family / kind | seeds | main | branch |
  |---|---|---|---|
  | judge-delay / delay / worse (DELAY3 eight times too long) | 1-10 | failed | testing at 6 h |
  | judge-delay / delay / slowed (DELAY3 two hundred times too long) | 1-10 | failed | testing at 6 h |

  Why: both replays are far off (the model as it is has no delay at all), and the better one's bias counts as noise
  (its second moment, not its variance), so the bound stays wide; taking the bias out failed the error-rate tests
  (9% to 18% false passes). Left: a noise estimate that separates a replay's bias from the record's noise.
- **Also:** a change whose record stopped is inconclusive once its horizon has passed (it waited for ever); "needs
  about N more record" counts the mixture's log factor; looks are due a second early.
- **The definition above says otherwise in two places,** and is not edited (gate 1): an undecided change within the
  threshold both ways is inconclusive after three times the record it needs, not at once; and the noise is the
  replay's own about the better replay, AR(1), not batch means (tried first: a drifting effect was read as noise).
