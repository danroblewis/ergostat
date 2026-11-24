# forecast-promise-proposal: Proposal: forecasts, quotes, frozen windows and calibration as general core parts

depends-on: [control-aware-estimates-proposal]

Write `docs/proposals/forecasts-and-promises.md`, settling the design the later gaps in this milestone build.

The owner wants to add work knowing it will be done in the right order, with its prerequisites, and what it does to the timeline. Estimates must be abstracted from the Gantt so other features can use them.

Settle:
1. The forecast as a stable result: per item, per group and per stage; finish-time ranges, what it waits on, its basis and its sample size.
2. Promise types a model may use: per-item date, a quantity by a date (N of M), a service level, and starting extra to cover expected loss.
3. How each of the three models contributes: the process model (paths, stage times, rework), system dynamics (aggregate capacity and flow), control (gates, release, pools). Agree with control-aware-estimates-proposal and do not repeat it.
4. A quote: hypothetical items run through the forecast without touching the record, and what it reports.
5. A frozen window: what it protects, how it is declared, how urgent work overrides it, and its effect in the simulation.
6. Calibration: what is recorded when a forecast is made, how it is scored, and how results feed back.
7. How a remote system's forecasts are read by another model.
8. The build split, confirming or amending the gaps of this milestone.

Definition of done.
1. The proposal settles all eight, with a worked example for a job shop with rework and one for a batch process with yield loss.
2. It names what already exists and what is new.
3. Any question for the owner is one sentence.

Boundary (the owner, 2026-11-23). ergostat serves job shops with rework, batch and yield production, and make-to-stock alike. No production style is a principle of the core. The core offers general parts, off unless a model declares them, and names no gaps, merges, software or factories. The ergostat-on-ergostat factory is one user, a job shop with rework, and its choices live in its own model. A model read as a remote system must be able to expose these answers to the model reading it.

Build on what exists: the Monte Carlo over every open item (`ergostat/numbers/eta.py`, `etamodel.py`), its what-if overrides, its backtest (`tests/eta_backtest.py`), and the Timeline's calibration line. Do not start a second estimator.

Do not measure or change the live instance in the session.

## Where it stopped

Round 1: written. docs/proposals/forecasts-and-promises.md settles the eight (§1–§8), with a job shop with rework
(§9.1) and a batch process with yield loss (§9.2). No code changed (0 net lines).

- Done 1: the eight are settled. Both worked examples are illustrative, worked by hand and not run on a record, and
  the file says so. The one exact figure, the binomial table of §9.2 (12 lots for 10 good at level 0.9, scrap 8%), is
  named as the check `test_extra_matches_binomial` that the quote gap must pass. It was worked by hand, because the
  inline check `uv run python -c "from math import comb; ..."` was refused in this session.
- Done 2: the opening table names what exists (file by file) and what is new.
- Done 3: two owner's questions, each one sentence, with the default until answered.
- §8 is proposed whole. The milestone's later gaps are not in this clone (no record names them), so the six gaps,
  their files, order, budgets (about 920 net lines) and acceptance tests are given for the coordinator to map onto
  what is filed. control-aware-completion-estimates is confirmed as control-aware-estimates.md §9 amends it.
- Decisions taken alone (each the reversible one, listed in the proposal): an hourly frozen list recorded as an
  event; an unreadable freeze takes the plain order; the conformal correction and remote quotes off unless declared;
  per-item random streams only if the backtest is unchanged.
- Not measured, and the live instance not touched. No test, page or example changed, so only ruff was run.

Round 2 (no review findings to answer): the proposal checked against the code and SPEC it names. Every name it cites
exists as cited (`eta.FEW`, `etacheck.FEW`, `KindIn.said`, `_Run.done`, `eta.reasons`, `take_key` shared by the
dispatcher and `eta._Run`, `closedloop.parse_whatif`'s `block.NAME.pool`/`.failure`, `closedloop.risk`'s
`p_ever_off`, `eta_api.KEEP` 8, `remote/items.ASKS`, the remote API's `AT_MOST` 200), and it agrees with
control-aware-estimates.md §1–§9. Five corrections, no change of design:
- §1: the item shape keeps every key `eta.simulate` gives today, `mean` included, which round 1 had left out.
- §1: CAE's `flows: {flow: per hour}` is said to be `per_hour` read at each flow's sensor state: one count, one name.
- §5: the frozen start is read from `stages` of the block's `takes.at` states. The unreadable-list case is no longer
  headed "failing closed": it falls back to the plain order on purpose, which the text now says (lesson 8).
- §9.2: the time-bound search lists every k up to `most`, as §2 says it does, and each chance is at most the binomial's.
- §9.2: the remote reader's relation is given in SPEC §5a's `relations:` form, with `bakery-lot` as the remote's kind.
- The binomial table was worked by hand again and agrees: 0.434, 0.782, 0.935, 0.984. A scratch script for it,
  `/tmp/binom.py` written with the Write tool, was refused (`/tmp` is outside /work for the file tools), and a
  scratch file inside the repository would break the rule against them, so no machine check was run.
  `test_extra_matches_binomial` in the quote gap remains the check.
- Still 0 net lines of code. Only ruff was run.

Round 3 (no review findings to answer): checked again after the merge of main (feb19045). The merge changed none of
`numbers/eta*.py`, `etacheck.py`, `leases/ready.py`, `closedloop.py`, `remote/` or control-aware-estimates.md. One
thing it added touches §1: SPEC §5a's why answer now has `place` (`why/within.py`), which tells where an item is held
as one of many, through a relation that is neither precedence, a group nor a remote's. The proposal now names it in
the table of what exists, and §1 says `waits_on` does not repeat it, since the simulation does not model such a hold.
The other SPEC additions (template `exports:`, untrusted marks on diagrams, the Blocks loop drawing, dashboard
diagram panels, the `display` change kind) do not affect this design. No change of design.
- The binomial table was worked by hand a third time and agrees (0.4344, 0.7819, 0.9348, 0.9838). The scratch
  script `/tmp/binom.py` (Write tool) was refused again: `/tmp` is outside /work for the file tools.
- Still 0 net lines of code. Only ruff was run.

Round 4 (no review findings to answer): main (b9341591) was already merged into the branch, so nothing new to check
against. The proposal was read through again for the review lessons and needed no change of design. One line in §9.2
that ran past the file's width was rewrapped.
- The inline check `uv run python -c "from math import comb; ..."` was refused again. The M = 12 row was worked by
  hand a fourth time (0.3677 + 0.3837 + 0.1835 = 0.9349) and agrees. `test_extra_matches_binomial` in the quote gap
  remains the check.
- Still 0 net lines of code. Only ruff was run.

Round 5 (no review findings to answer): main has no commit the branch lacks (`git log branch..main` is empty), so
nothing new to check against. Read through again; no change of design. One more line in §9.2 ("the same four
lanes, ...") ran past the file's width and was rewrapped; the only lines still longer are table rows.
- The inline check `uv run python -c "from math import comb; ..."` was refused again. The M = 13 row was worked by
  hand (0.3383 + 0.3824 + 0.1995 + 0.0636 = 0.9837) and agrees. `test_extra_matches_binomial` in the quote gap
  remains the check.
- Still 0 net lines of code. Only ruff was run.

Round 6 (no review findings to answer): main has no commit the branch lacks. Two corrections, no change of design:
- §8 called yield inside an item "the second owner's question"; it is the first in the list. Now says first.
- The record had no `## Entry`, so docs/GAPS.md, written from the records, would carry nothing for this gap. One is
  appended below (section Modelling), the reversible choice: the queue may place or reword it.
- Still 0 net lines of code. Only ruff was run.

Round 7: both review findings answered (both blocking; there were no others). Both are changes of design, made
in the proposal only:
- Finding 1 (frozen windows and recorded calibration rested on a periodic forecast that does not exist; the eta
  worker in web/eta_api.py is demand-driven and exits after a minute idle). Answered by adding *Standing runs* to
  §1. `numbers/standing.py` is started by the runner beside the engine, as `remote/refresh.start` is, also under
  `--no-web`, and only when a model declares `frozen:` or `forecast: {record:}`. The worker moves to
  `numbers/etaworker.py`. A due `standing` job is taken before any page's ask, so the last-asked-first what-if
  queue cannot starve it. The worker does not exit when idle while a standing schedule is declared. A late or failed
  pass is reported by health and said in each frozen block's why, never read as current. Only standing passes are
  recorded, so calibration samples the schedule and not the moments someone looked. The table of what exists now
  names the demand-driven worker and `remote/refresh.start`. §8 gains the gap forecast-standing-runs (110 lines,
  four acceptance tests), on which frozen-windows and forecast-calibration-recorded now depend.
- Finding 2 (no bound on `extra` quotes, on `record` or `every`, or on the record's growth). Answered by a *Bounds*
  table in §1, refused at check and clamped at run time as `remote/items.period` does: `frozen.every` 15 min to
  1 d; `frozen.for` up to 7 d; `frozen.most` at most 200; `record` 1 h to 1 d; at most 200 items a recorded pass;
  `keep` 7 d to 400 d; `extra.most` at most 10, down from 50; at most 24 `extra` quotes a standing period across
  every group. That makes the worker time per period at most 125 s, 14% of the worker at the 15-minute floor.
  `extra` is never worked out for a page's refresh; it runs as jobs below page asks, and a group not reached is
  unknown, never kept. A frozen list is written only when it changes, and it is about `ergostat.frozen/BLOCK` so
  roll-up folds old lists. The recorded ladders go to a side file `forecasts/YYYY-MM.jsonl.gz` with a keep
  (about 0.5 MB a day raw at most), and `forecast.made` is a summary of 1 kB at most. §7 no longer serves the ladders
  remotely. The new tests are named in §8.
- §8 is now seven gaps, about 1,050 net lines. The Entry below was updated to match (it said six and 920).
- The new figures (125 s, 14%, 0.5 MB a day, 200 MB at 400 d) are worked by hand from the stated ceilings and
  `BUDGET`, and were not run or measured. The roll-up of `ergostat.frozen/BLOCK` was read from `rollup.py`'s
  description, not tried; `test_frozen_lists_roll_up` is the check.
- Still 0 net lines of code. Only ruff was run.

## Entry

section: Modelling

- **Forecasts, promises, quotes, frozen windows and calibration** (done as a proposal, on
  `forecast-promise-proposal`; `docs/proposals/forecasts-and-promises.md`, built on control-aware-estimates.md):
  settles `forecast/v1`, one stable result from the existing Monte Carlo (`numbers/eta.py`), per item, group, kind
  and stage, with a quantile ladder, `waits_on`, basis and runs; promises a model may declare (a date, N of M by a
  date, a service level, extra started to cover loss); quotes of hypothetical items through the what-if path,
  writing nothing; standing runs on a bounded schedule, started by the runner and taken before page asks, for what
  must happen unwatched; frozen windows as a term at the front of `take_key`, broken by urgent work and recorded;
  calibration of recorded forecasts and promises beside the backtest; `/remote/v1/forecast` read by `forecast: true`
  relations. Worked for a job shop with rework and a batch process with yield loss. *Left*: the seven build gaps of
  its §8 (about 1,050 net lines), not yet filed; two owner's questions (whole-lot loss or yield inside a lot; a frozen
  window refreshed hourly or only on request).
