# error-budget-sets-check-level: An error budget sets how much checking a change gets

depends-on: [merge-first-verify-after-proposal]

A general control loop: a budget of regressions reaching main per window; while it is healthy, the declared check level for low-risk changes drops (fewer pre-merge tests, no blocking review); as it burns, checks tighten. It requires the retroactive fix path from merge-first-verify-after-proposal and stays off until that exists.
Done: 1. Tests: the level moves with the budget, both ways, with a recorded reason. 2. With no retroactive mechanism declared, the level never drops. 3. The budget and level are dashboard series.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.

## Where it stopped

Round 1, built. All three done items are in the branch. The factory's use stays inert until the coordinator switches
the verification lane on.

What was built:
- In ergostat's core: a new built-in block, `type: budget` (an error budget). It is in `ergostat/spec/blocks.py`
  (`Budget`), its keys are checked in `compile.py` (`budget_block`), and it is listed in SPEC §9.2.
  - `in: {spent: SIGNAL, retroactive: SIGNAL}`. `retroactive` is optional.
  - `budget` (over 0, at most 10⁶), `levels` (2 to 10 names, the lightest first), `healthy` (default 0.5) and `hold`
    (default 1d).
  - The output is the level's number. It starts at the strictest.
  - With at least `healthy` of the budget left, the level drops one step once it has stood `hold`. As the budget burns
    it rises at once, to the strictest when nothing is left.
  - It drops only while `retroactive` is declared and reads over 0. Undeclared, it never drops. Off, unread, or not a
    finite number, it is the strictest. So is a `spent` that is unread, not finite, or below 0 (lesson-3).
  - It is off unless a model declares it, and it names no gaps or software.
- The engine (`engine.py`):
  - steps a budget every pass (`every_pass`), so a held level drops on time alone;
  - writes its budget left as the series `block/NAME/left`;
  - records each move as `controller.decided`, with `decision` ("check level drops to standard (1)") and `why` (the
    budget left, its share, and the rule). `decided` takes the block's own words when it gives them.
- Two built-in measures, `ergostat.errors.level@BLOCK` and `ergostat.errors.left@BLOCK` (`numbers/measures.py`,
  `ir.ERRORS`). An auxiliary reads each through a `builtin:` sensor, so it is a chart series. A name that is not a
  budget block is an error, never a number.
- Library trust: `budget` is a refused block type for libraries you did not write (`trust.REFUSED_TYPES`,
  SECURITY.md). A library could otherwise lower the owner's checking.
- The factory, the first user (`dev/model/landing.yaml`):
  - the block `error-budget`: 2 regressions over 14 days, levels light, standard and full, healthy 0.5, hold 1d;
  - it reads `verify-escapes` (spent) and the new auxiliary `verify-retroactive` (`verify.py retroactive`: 1 with
    `[verify] after` on, a verified commit, and the lane not held; run/verify.json unreadable means no reading);
  - the auxiliaries `check-level` and `error-budget-left` are on the `merge-pipeline` chart;
  - dev/README.md: *The error budget sets the check level*.

Tests, `tests/test_error_budget.py`, 24 passing:
- Done 1:
  - `test_the_level_moves_with_the_budget_both_ways_with_a_recorded_reason`: full, held, standard, light; then up to
    standard and full as the budget burns, and down again. Each move's decision and reason are checked.
  - The retroactive input off or unread, and `spent` unread, NaN, infinite or negative, give the strictest at once.
- Done 2: `test_with_no_retroactive_mechanism_declared_the_level_never_drops` (a month with the whole budget left).
- Done 3: `test_the_budget_and_the_level_are_dashboard_series`. The chart's refs check, the measures read what the
  engine wrote, and `/api/series` (`series.series`) gives both auxiliaries' values.
- Also: bad keys refused (9 cases), ports other than spent and retroactive refused, stepped every pass, the factory's
  model loading with the block wired and no finding on its parts, and `verify.retroactive` (on, off, held,
  unreadable, no verified commit). `tests/test_library_trust.py` gains the refused `budget` case.
- Seen to fail when the code was broken:
  - an undeclared retroactive read as on (the level dropped on day 1);
  - the hold removed (the first step dropped at once);
  - the engine's reason event limited to on/off changes (no event on the drop);
  - the left series not written (no reading to chart);
  - `retroactive()` ignoring `held`.

Other suites run, all passing: `tests/test_spec_blocks.py`, `tests/test_closedloop.py` and `tests/test_library_trust.py`
(82, then 50 after the new case); `tests/test_run_costs.py`, `tests/test_verify_after.py` and
`tests/test_runner_and_state.py` (87); `tests/test_factory.py` (251 passed, 2 skipped: Docker absent). ruff is clean on ergostat, tests, scripts and dev/bin/verify.py. Not run here:
the full unit suite and the four browser files (the merge queue runs them). No page changed.

Choices, each the most reversible reading I could find:
- "Low-risk changes" and what each level skips are not built. The definition's done items ask for the control loop,
  its rule with no retroactive path, and the series. The level is a number the model declares and names. Nothing in
  the factory reads it yet. Wiring the queue and the reviewer to skip pre-merge tests or the blocking review is a
  change to what reaches main. That is the coordinator's to make once the lane is on, or a gap of its own.
- The retroactive path is a signal, not just a declaration. The factory's verifier block always exists in the model,
  even while `[verify] after` is off. A declared-only rule would let the level drop with nothing finding regressions.
- The budget left is `budget − spent` over the `spent` sensor's own window. The factory's window is
  `verify-escapes`' 14 days, and its `budget: 2` is a starting value for the coordinator to tune.
- The level is the engine's state. A restart starts it at the strictest, and it waits `hold` per step down. That errs
  toward checking more.
- The decision text says "check level", since checking is what the definition names. The block itself is general.

Size: about 140 net lines in `ergostat/`, under the 600 budget. dev/ and docs/ are not counted.
No `## Entry` was written: this file may only gain this section.

### Round 2: the two blocking findings

Both are fixed. Where round 1's text above says otherwise, this part holds.

1. An old reading stood in for a failed sensor (lesson-3, 8, 9). The finding was right: the engine fed the block the
   newest reading however old, so retroactive 1 from before a failure kept the level dropping.
   - Fix: `Engine.fresh_only` (engine.py). For a budget block, a stock, flow or auxiliary input whose newest reading is
     past its sensors' clocks reads as None (`observer.fresh`). The clock is the observer's rule: three periods, or
     three cron times. There is no grace after a start or a sleep, so an old reading is never fresh after a restart.
   - A sensor that reads on no clock (manual, items, changes) cannot be shown fresh, so it counts as unread. A part
     with no sensor is read as it is.
   - A budget block ignores `on-stale: hold`, so a stale input can never keep a low level.
   - The factory: `verify-retroactive` reads every 10m and `verify-escapes` every 30m. So 30 or 90 minutes after
     either one fails, the level is full.
   - Test: `test_a_failed_sensor_s_last_reading_does_not_stand_in_once_it_is_past_its_clock[escapes|retro]`. It takes
     the real path: readings written to the record, `Engine.measure`, then the pass. The level drops to standard,
     then one sensor stops writing. The level stays at standard while the reading is within its clock, rises to full
     just past it, and stays at full for days. Also `test_an_input_never_read_is_the_strictest`.
   - The test stepper no longer sets a None signal, a state a failing sensor never produces. A None now means no new
     reading, so the last one stays. The None cases moved to these two tests. The model's two inputs now have
     clocked `run:` sensors.
   - Seen to fail: with `fresh_only` replaced by the plain `get`, both cases of the new test fail (the level stays 1).
2. The level dropped while the budget was unhealthy (blocks.py). Fixed: below `healthy` the level only rises, to the
   formula's step when that is stricter, or stays.
   - Test: `test_an_unhealthy_budget_never_lets_the_level_drop`. With 1 of 4 left, the level stays at full for 30 days.
   - Seen to fail: with the old target rule restored, it fails (the level reads 1).
   - Docs corrected to match the code: SPEC §9.2, the `Budget` docstring, dev/README and both landing.yaml
     descriptions. The old README claim "unreadable ... it stays at full" now says when, and after how long.

Tests run in round 2, all passing: `tests/test_error_budget.py` (27), `tests/test_spec_blocks.py` and
`tests/test_closedloop.py` (60 with the first), `tests/test_observer.py`, `tests/test_library_trust.py` and
`tests/test_verify_after.py` (115), and `tests/test_factory.py` (251 passed, 2 skipped: Docker absent). `main` was
already merged in (no new commits on it). ruff is clean. Not run here: the full unit suite and
the four browser files (the merge queue runs them). No page changed.

Size: about 35 more net lines in `ergostat/`, still well under 600.
