# group-and-yield-forecasts: Forecasts for groups: how many of a set finish by a date, allowing for loss

depends-on: [forecast-is-a-core-result]

From the same simulation, answer group questions: how many of a declared set finish by a date, the chance at least N do, expected loss, and how many to start to get N out at a stated confidence.

Definition of done.
1. Tests on a fixture with a known yield recover the right counts within stated bounds.
2. A second fixture, a job shop with rework, gets correct group answers with no special case.
3. The answers are available to dashboard panels.

Boundary (the owner, 2026-11-23). ergostat serves job shops with rework, batch and yield production, and make-to-stock alike. No production style is a principle of the core. The core offers general parts, off unless a model declares them, and names no gaps, merges, software or factories. The ergostat-on-ergostat factory is one user, a job shop with rework, and its choices live in its own model. A model read as a remote system must be able to expose these answers to the model reading it.

Build on what exists: the Monte Carlo over every open item (`ergostat/numbers/eta.py`, `etamodel.py`), its what-if overrides, its backtest (`tests/eta_backtest.py`), and the Timeline's calibration line. Do not start a second estimator.

Do not measure or change the live instance in the session.

## Where it stopped

Round 1, built. All three items are in the code, each with acceptance tests in `tests/test_group_counts.py`. Size:
225 net lines outside tests, docs and dev (252 added, 27 removed, against the branch's start 74f4c198, the new
`numbers/yields.py` included), within the 600 budget.

- **One simulation.** `eta.simulate` gains `counted=`: for each named set, each run's sorted times its members came
  out and were lost (two `array('d')`), kept beside what it already said; nothing it said before changes (the job-shop
  test compares a run with and without it). `_Run` marks an item lost when it ends dead or in a state its kind
  declares `lost:`. `numbers/yields.py` answers from those runs: a summary (out and lost, mean and p10/p50/p90, the
  yield, the k-th member's date at p50 and p90) and asks (by a date: out, lost, the chance at least N, how many to
  start at a confidence). No second estimator.
- **A general part, off unless declared.** An item kind's `lost: [states]` (compile checks it, `bad-lost`; the library
  trust table lists it). Without it only dead letters count as lost. Nothing names a production style.
- **Done 1.** `test_a_known_yield_is_recovered_within_stated_bounds`: a record of 200 units passed or scrapped (0.8 a
  pass, stays even over 1000–6970 s) read through `etamodel.read` and the eta worker; lot/A's 50 open units. Out and
  lost means within ±1.0 of 40 and 10 (4 standard errors at 200 runs), the yield within ±0.02, out by a date within
  ±1.0 of 50 · 0.8 · 101/200, the chance of 25 by then within ±0.1 of the exact binomial, how many to start for 40
  at 0.9 within ±2 of the exact answer (55).
- **Done 2.** `test_a_job_shop_with_rework_gets_correct_group_answers`: a machine of 2 (600 s), inspection passing
  70%, sending 25% back to the queue and scrapping 5%, ten older jobs ahead of order/7's 30. Through the same
  `forecast.build` and `asked`: yield 14/15 (rework loops counted, not lost), out and lost means within ±0.4, none out
  before 3660 s (the ten ahead first), Binomial(2, 0.7) just after, how many to start within ±1 of the exact answer
  at 14/15 (32) and equal to the exact answer at the yield it simulated.
- **Done 3.** `test_a_panel_reads_the_group_counts_through_the_sql_source` (through `/api/query`): `forecast_groups`
  gains `members, out, lost, yield`; a new view `forecast_group_by(parent, n, p50, p90, …)`; and the functions
  `forecast_out`, `forecast_lost`, `forecast_chance`, `forecast_start` answer by any date, equal to the API's
  `asked`. A query naming one while there is no forecast is refused with why, as for the views. The remote side:
  `test_a_model_read_as_a_remote_exposes_its_group_counts` (two instances in one process): the reader's
  `/api/forecast?remote=shop&group=lot/A&by=…&at_least=40&confidence=0.9` gets the remote's `count` and its `asked`.
- Breaking the code to see the tests fail (lesson 9): with the `lost:` check removed from `_Run.enter`, Done 1 and
  Done 2 fail (lost 0, yield 1.0); with `start_for` answering `ceil(N / y)`, Done 1, Done 2 and the unit test fail (50 for
  55; 31 for 32, caught by the exact check at the simulated yield, which the ±1 bound alone let through).

Decisions taken alone (each the more reversible):

- A group's members for counts are its open members that can move, its parent not one (the forecast's existing group
  set includes the parent). Members already finished before now are not counted: an ask is of what is still to come.
  A panel can add the done count from the Items tab's group progress.
- How many to start uses one pooled yield (the share out by the date over every run) and the exact binomial: each
  extra item is taken to come out as these did, independently. The extra items' own queueing is not simulated; SPEC
  says so. A per-run mixture would count the binomial noise twice.
- The kept runs are capped at 500,000 member-runs per forecast (4 MB), by parent id. Groups past that keep their last
  finish and say `none` in `count`. An ask wants at most 10,000 out.
- A `lost:` state that is not a finished state is accepted by compile (finished may be inferred from the record) and
  never reached as a loss; SPEC says so.
- In the SQL frame a numeric `n` is a measure, so a panel listing `forecast_group_by` by k writes `printf('%d', n)`
  as its label (the source's own rule; the test does this).

Tests run, one file at a time: `tests/test_group_counts.py` (6 passed), `tests/test_forecast_result.py`,
`tests/test_eta.py`, `tests/test_library_trust.py`, `tests/test_sql_source.py` (one pinned list of views gains
`forecast_group_by`), `tests/test_todo_template.py`: all pass. `ruff` is clean. `main` is an ancestor of HEAD. Not
run: the whole unit suite, the browser files (no page or JS changed) and `demo_check` (no example touched). The live
instance was not measured or touched.

## Entry

section: Modelling

- **Group counts from the forecast** (done, on `group-and-yield-forecasts`; SPEC §5a *Group counts*, §4c, §4e): from
  the same Monte Carlo, each group's open members: how many come out by a date, the chance at least N do, the
  expected loss, and how many to start for N out at a confidence (exact binomial on the simulated yield). A kind
  declares its loss states with `lost:` (off unless declared; dead letters always lost). In `forecast/v1` as a
  group's `count`; asked through `GET /api/forecast?group=…&by=…&at_least=…&confidence=…`, `/remote/v1/forecast` and
  a reader's `/api/forecast?remote=NAME&group=…`; for panels, `forecast_groups`' count columns, `forecast_group_by`
  and the `forecast_out`, `forecast_lost`, `forecast_chance` and `forecast_start` SQL functions. Not done: the extra
  items' own waits in how many to start, and counts of members finished before now.
