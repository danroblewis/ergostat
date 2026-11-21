# poor-identifications-proposed: a burst's window sized from the process it identifies, and several outside steps fitted together as experiments
depends-on: []

The quality floor, `loop-not-identifiable`, identifying around the largest outside step and the strip's "Low confidence" are on main (`churn`, `docs/roadmap/overnight/churn.md`). They must not be rebuilt. This branch closes two of the three points the GAPS entry leaves:

- **(a)** `ident.around` (`ergostat/control/ident.py:459`) chooses its window from y's own excursion. It fits from `POINTS_MIN` buckets before the step to where y comes half way back, and holds out as long again. A tight loop on a slow process pulls y half way back long before the process has settled, so the part fitted sees only the start of the response.
- **(b)** `loop.around_step` (`ergostat/control/loop.py:208`) uses only `steps[0]`, the largest step. Every other burst in the record is thrown away.

The third point, projections suggesting the missing structure (capacity) themselves, is **not** in this branch. It belongs with *Finding structure from residuals*, and GAPS keeps it under **Left**.

## Definition of done

Names used below:
- `P = ident.POINTS_MIN` (40);
- `h` is the bucket;
- `k` is a step's bucket;
- `n` is the record's length in buckets;
- the **settling** of a first-order process is `S = max(θ + 4τ, SPAN_MIN·(τ + θ) − P·h)`. Past `θ + 4τ`, 98% of a step's response has arrived, and the second term makes the fitted part span what `judge` asks for.

1. **A new module `ergostat/control/experiments.py`** (outside steps as experiments; Ljung §14.3, the same `merge` as `_test_windows`) holds the step-finding that is in `loop.around_step` now, and the windows. `loop.around_step` becomes a thin caller: it gathers the inputs as now, calls `experiments.identify_around(h, t, u, y, ins, noise)`, and builds the record as now. When a result has several experiments, that record is their concatenation, as `_test_windows` builds one. `ident.around` stays as it is: it is the excursion window, pass 0.

2. **Which steps.**
   - `ident.outside_steps` runs on every input, not only the largest's.
   - Steps on different inputs within `P` buckets of each other are one step. It keeps the earlier `k` and names every input it was seen on.
   - At most `STEPS_MAX = 6` steps are kept, the largest by |jump| (a module constant, not configurable; lesson-4). They are then ordered by bucket index, never by wall time.

3. **Windows from the process, in passes** (`PASSES_MAX = 3`, a module constant).
   - **Pass 0:** each step's window is the excursion window of `ident.around`, with its fitted part ending at the half-way point.
   - **Pass i (1 ≤ i < PASSES_MAX):** it starts only if pass i−1 found an FOPDT process, so `τ` is not None. Each step's window is fitted from `k − P` to `f = k + ceil(S/h)`.
     - With **one experiment**, it is held out from `f` to `b = f + max(f − k, P/2)`.
     - With **several**, each experiment is `[k − P, f)`. All but the last are fitted, and the last is held out whole.
   - **Overlapping windows** become one experiment, covering their union. They are never cut. Its steps are listed in it, and its held-out end is taken from its last step.
   - **Stopping:** the passes stop early when a pass's windows are identical (the same bucket bounds) to the previous pass's. No pass ever calls `ident.identify` more than once, so a call makes at most `PASSES_MAX` fits.

4. **A later pass that fails keeps the previous window, labelled. It never fails open.** For a pass i ≥ 1:
   - **Pass i−1 was not found, or was integrating** (no τ, so no settling to size a window from): pass i does not run. The result is pass i−1's, and `outside_step["passes"][i]` says why: `"not run: pass i−1 found no process"` or `"not run: integrating, no settling time to size a window from"`.
   - **Pass i's fit is not found:** the result is pass i−1's, and `passes[i]` says `"not found: <its why>"`.
   - **Pass i's fit is worse than pass i−1's** by `loop.identify`'s own order (proposable, then told apart, then `-ident.precision`): pass i−1's result is kept, with `passes[i]` = `"not kept: pass i−1 was better (<the deciding key>)"`.
   - **Pass i needs more record than exists:** handled by rule 5. It is never filled in or clipped silently.

   The result has `outside_step["window"]` set to `"process"` when a pass ≥ 1 is kept, and to `"excursion"` otherwise. `outside_step["passes"]` lists each pass's outcome, whether it was kept or why not.

5. **A short record drops the step. A proposal is blocked only when no step is left.**
   - **What counts as short:** in a pass ≥ 1, a step is short when its window needs record past the end. With one experiment that means `b > n`; with several, `f > n`.
   - **Dropping it:** the step is dropped from the experiments, whatever its size or position, the held-out one included; the experiment before it then becomes the held-out one. It is listed in `outside_step["dropped"]` as `"the step at HH:MM (<input>): the record after it covers <X> of the <Y> its process needs to settle"`, where X and Y are durations.
   - **When no step is left:** the result is the previous pass's, made **not proposable**. Its `why` gets that same line, so `proposable` is False and `judge`'s reasoning is said in full. A window the process says is too short is not trusted from an earlier, shorter window either.
   - **Too little record before:** a step with fewer than `P` buckets before it cannot occur, since `outside_steps` requires them.

6. **An input with no readings in a step's window drops that step. It is never forward-filled across experiments** (lesson-3).
   - **When this applies:** in any pass, u or any input fitted beside u (`ins`, the step's own input included) has no reading inside an experiment's window.
   - **What happens:** that experiment is dropped and listed in `dropped` as `"the step at HH:MM: <input> has no readings in its window"`. It is not fitted with that input taken as constant, and that input is not removed from the fit of the others.
   - **When nothing is left:** `identify_around` returns a result with `found: False, proposable: False` and those lines as its `why`. That result ranks last in `loop.identify`, so nothing is proposed from it.

7. **What it says.** `proposals._around` names every step used and how the window was chosen:
   - `"identified around outside steps at 14:20, 16:05 (flow.asked), each window from the process (θ + 4τ = 7m)"`, or
   - `"... window from y's excursion (<the passes line that stopped it>)"`.

   The same text goes into its `identified:` line and the reason, with `dropped` lines appended when there are any. `instead_of`'s `"an outside step"` becomes `"outside steps"` when there are several. `outside_step` keeps its keys `at` (the first step), `input`, `since`, `until` and `held` (where the held-out part starts, which `loop.py:332` reads), and adds `steps`, `experiments`, `window`, `passes` and `dropped`.

8. **Numbers this branch must meet, by tests that can fail.** All of them use the existing `burst_loop` model in `tests/test_churn.py`: K = 0.2, θ = 20 s, KD = 0.5, H = 10 s, integral control, measured burst d, unmeasured steps v.
   - **(i)** On the existing fixture (τ = 60 s, seeds 0–5), `identify_around` meets the existing bounds, written here:
     - per seed |K − 0.2| < 0.1 and |θ − 20| ≤ 10;
     - the mean over seeds of |ΔK|/K + |Δτ|/τ is < 0.3, and below a third of the loop-working mean.
   - **(ii)** On a slow fixture (τ = 300 s; integral gain starting at 0.3; a burst of 60 s at 3000 s; n = 12000 s; v quiet from 1000 s before the burst to the end; seeds 0–5):
     - the excursion result (`ident.around`) has the why line `"the part fitted spans less than 5 of τ + θ"` for every seed;
     - `identify_around` has `window == "process"`, no such line, |K − 0.2| < 0.1 and |θ − 20| ≤ 10;
     - its mean relative error is < 0.3, and at most half the excursion's mean.

     The implementor may change only the integral gain (within 0.1–1.0), the burst width (within 30–120 s) and n (≤ 15000 s) to get there, writing the values in the test's docstring. The assertions are not loosened. If no setting in those ranges shows it, the report says so and the branch does not claim it.
   - **(iii)** On a three-burst fixture (bursts at 2000, 5000 and 8000 s; n = 11000 s; v quiet from 1000 s before to 2000 s after each; seeds 0–5): three experiments, with the last held out. For **every** seed, `se["K"]` of the joint fit is **strictly less** than `se["K"]` of `experiments.around_steps(..., steps=[the largest])` on the same record.

9. **Docs.**
   - SPEC: rewrite the *Outside steps* paragraph (`docs/SPEC.md:3109`) to describe the passes, the windows, the experiments, the drop rules and the measured claims of 8, no wider.
   - Agent guide: update the `loop-not-identifiable` bullet (`docs/AGENT-GUIDE.md:528`) to say "outside steps", with the "covers X of Y" line telling the agent to wait for more record.
   - GAPS: in the entry's **Left**, remove the two points done and keep "the projections do not yet suggest the missing structure (capacity) themselves", pointing to *Finding structure from residuals*.
   - Add the definition file `docs/roadmap/overnight/poor-identifications-proposed.md`.

## Files to touch

- `ergostat/control/experiments.py` (new)
- `ergostat/control/loop.py` (`around_step` becomes a thin caller; the `instead_of` wording)
- `ergostat/control/proposals.py` (`_around`)
- `ergostat/control/ident.py` (only if `around` needs to return its fitted end for pass 0; its behaviour is unchanged)
- `tests/test_outside_experiments.py` (new); `tests/test_churn.py` (only to import `burst_loop` from a shared helper if it is moved; no assertion changed)
- `docs/SPEC.md`, `docs/AGENT-GUIDE.md`, `docs/GAPS.md`, `docs/roadmap/overnight/poor-identifications-proposed.md`

## Risks

- **lesson-3 (failing open):**
  - an input with no readings in a window gets forward-filled from another experiment by `_ffill` over the concatenation;
  - a later pass that finds nothing silently keeps a window the process says is too short;
  - a step past the record's end gets its window clipped to `n` and fitted as if whole.

  Rules 4–6 define each case; tests 5, 6 and 7 fail if any of them is filled, clipped or kept unlabelled.
- **lesson-4 (a limit with no ceiling):** the steps and passes multiply the fits (each a Nelder–Mead search over the record). `STEPS_MAX = 6` and `PASSES_MAX = 3` are constants, not config. Test 8 counts the steps used and the `ident.identify` calls.
- **lesson-8 (a claim wider than the code):** the SPEC must not say "closer to the truth" or "more precise" beyond the fixtures and numbers in rule 8. Each sentence of the new SPEC paragraph names the test behind it in the report.
- **lesson-9 (a test that can't fail):** the bounds in rule 8 are separate assertions, never `A or B`. The report breaks each guarded line and shows the test failing:
  - restrict step choice to `steps[0]` → test 3's strict se inequality fails;
  - make pass ≥ 1 reuse the excursion window → test 1 fails;
  - forward-fill instead of dropping → test 7 fails;
  - clip instead of dropping → test 6 fails;
  - treat a failed later pass as kept → test 5 fails.
- **lesson-2 (wall-time ordering):** steps and experiments are ordered by bucket index, and "the last experiment" is the highest index, never chosen by comparing `at` stamps.
- **lesson-7 (merged branches):** *Proposals superseded by any edit* (leased) also touches `ergostat/control/proposals.py`. Merge origin/main and run the suites again before saying it is built.
- **lesson-13 (stay in the gap):** a failure in the owner's-case churn test is looked at as this change's doing first, since the result `loop.identify` ranks has changed. A failure elsewhere is named and left alone.

## Acceptance tests

1. `tests/test_outside_experiments.py::test_a_slow_process_is_identified_from_its_own_window_not_ys_excursion`: rule 8(ii). Each assertion is its own `assert`: the excursion's span line, `window == "process"`, the K and θ bounds, mean error < 0.3, and mean error ≤ half the excursion's.
2. `tests/test_outside_experiments.py::test_one_burst_meets_the_churn_bounds_through_the_new_path`: rule 8(i) through `identify_around`.
3. `tests/test_outside_experiments.py::test_several_outside_steps_are_fitted_together_as_experiments`: rule 8(iii). `experiments == 3`, the three step times are in order, `held` equals the third experiment's `since`, and the strict `se["K"]` inequality holds per seed. It fails under a `steps[0]` restriction, where the two errors are equal.
4. `tests/test_outside_experiments.py::test_steps_whose_windows_overlap_become_one_experiment`: two bursts 300 s apart on the τ = 60 s fixture give `experiments == 1`, both steps listed in it, and its fitted end at least `ceil(S/h)` past the later step. Nothing is cut.
5. `tests/test_outside_experiments.py::test_a_later_pass_that_fails_keeps_the_previous_window`: pass 0 succeeds, and `ident.identify` is monkeypatched for its second call to return each of three things in turn:
   - `found: False` → the result's K equals pass 0's, `window == "excursion"`, and `passes[1]` starts `"not found"`;
   - an integrating form → `passes[2]` starts `"not run: integrating"` (pass 1 is kept);
   - a worse fit by the order → `passes[1]` starts `"not kept"`.
6. `tests/test_outside_experiments.py::test_a_step_without_enough_record_after_it`: three cases.
   - **(a)** One burst 400 s before the end (τ = 60 s): not proposable, and `why` has `"the record after it covers"` with X < Y.
   - **(b)** Three bursts, the last of them short: `experiments == 2`, the last in `dropped` with `"covers"`, and K and θ within the bounds of rule 8(i).
   - **(c)** The same as (b), with the short burst the largest: still dropped.
7. `tests/test_outside_experiments.py::test_a_step_whose_input_has_no_readings_in_its_window_is_dropped` (case iv): three cases.
   - Two inputs, d2 None across the second of three bursts' windows: `experiments == 2`, and `dropped` has `"d2 has no readings in its window"`.
   - The same with one burst: `found` is False, `proposable` is False, and the line is in `why`.
   - The same for u.
8. `tests/test_outside_experiments.py::test_steps_and_passes_are_bounded`: nine bursts keep 6 steps, the largest ones, and a counting monkeypatch shows `ident.identify` called at most `PASSES_MAX` times.
9. `tests/test_outside_experiments.py::test_the_reason_names_every_step_and_how_its_window_was_chosen`: `proposals._around` on a crafted result with two steps and `window == "process"`, then `"excursion"` with a passes line, then with a `dropped` line, asserting the exact text of rule 7.
10. The existing tests stay green and unchanged:
    - `tests/test_churn.py::test_identification_around_an_outside_step_beats_the_loop_working`
    - `tests/test_churn.py::test_a_poor_identification_gives_the_finding_not_a_proposal`
    - `tests/test_churn.py::test_the_owners_case_proposals_persist_and_get_judged`
11. The unit suite and the four browser files under `scripts/suite_watch.py` pass with rc 0 and no page test skipped; `uv run ruff check` is clean; `demo_check` passes on ticket-factory; origin/main is merged in and the suites are run again.

## Size budget

280 net lines (outside `tests/` and `docs/`): about 200 for `experiments.py`, 40 for `loop.py`, 20 for `proposals.py`, and 20 to spare.

## Notes from the plan review (answer each)

- Rule 3/4: 'pass i−1' is ambiguous when pass i−1 was found but not kept. Does pass i size its window from the attempted pass's τ or the kept pass's τ? Does the 'windows identical to the previous pass' stop compare against the attempted pass or the kept one? Pick one: the kept pass is the safer reading. Test it with a monkeypatched 'not kept' pass 1 followed by pass 2.
- Rule 5: when drops leave exactly one experiment, the single-experiment rule must apply again: held out from f to b, short when b > n. That can make the remaining step short too. Say so, and add a case to test 6: three bursts, the last two short.
- Test 5's integrating case asserts that pass 1 is kept. That only holds if the monkeypatched integrating result ranks at least as well as pass 0 by loop.identify's order. Build the fake so that it does, and assert window == 'process' for it, so the test checks the 'not run: integrating' branch and not the order.
- Test 3's strict per-seed se['K'] inequality has no escape clause, unlike 8(ii). If some seed fails because the fixture is unlucky, the implementor may not loosen it. Either allow fixture-only changes within stated ranges (as 8(ii) does), or require that the report say the claim is not made. Also define 'the largest' when the three bursts are equal: use the bucket order, never the stamps.
- Test 8: loop.identify may also call ident.identify for the loop-working candidate. Scope the counting monkeypatch to one identify_around call, and say that pass 0 (ident.around) counts as one of the PASSES_MAX fits.
- Rule 4: the 'worse' comparison runs across different held-out windows, so -precision favours the longer window. That is intended, but write it in the SPEC as such, so it is not read as like-for-like (lesson-8).
- Rule 2: say what happens to two steps on the same input within P buckets of each other. They are probably one burst's rise and fall. Keep outside_steps' existing behaviour and state it.

## Where it stopped

Built, in round 1. `ergostat/control/experiments.py` (new), with `loop.around_step` as a thin caller and `proposals._around`
saying every step. `ident.around`'s window logic is now `ident.excursion`, and `around` calls it (behaviour unchanged).
Net lines outside tests and docs: 219 of the 280 budgeted.

**Not claimed: rule 8(ii) as written.** `test_a_slow_process_is_identified_from_its_own_window_not_ys_excursion`
holds every assertion of 8(ii), not loosened, and is marked `xfail(strict=True)`: it fails today, and it turns red the
day it passes. Every allowed setting was scanned: integral gain 0.1, 0.2, 0.3, 0.45, 0.6, 0.8, 1.0; burst width 30, 60
and 120 s; n of 12000 and 15000 s. None gives a process window on all six seeds.
- The best per seed was gain 0.8, width 30 s: 5 of 6 seeds reached a process window and 6 of 6 were within the K and θ
  bounds, but the mean error was 0.51 against the 0.3 required.
- The blocker is `ident.moves`, in `ident.identify`, which is outside this gap. Pass 1's longer window often fails with
  "u did not move in the part of the record fitted": integral action ramps u, so no change from one bucket to the next
  passes a twentieth of its range over the longer window.
- When pass 1 is sized from pass 0's τ, which the excursion underestimates, the "spans less" line can also remain. Pass
  2 would correct that, but it fails the same way.

What does hold is in a separate, narrower test,
`test_a_slow_process_mean_error_from_the_new_path_is_under_half_the_excursions`, at the definition's own fixture (gain
0.3, width 60 s, n 12000 s):
- the excursion's span line appears on every seed;
- the mean error is 0.28 against the excursion's 0.57;
- at least 3 of 6 seeds reach a process window.

The SPEC claims only this. A gap for `ident.moves` (steps of u counted against its range, which misses a ramp) would be
its own.

**Decisions taken where the definition left a choice (each the more reversible option):**
- *Pass 0 with several steps.* Each step's excursion is read only up to the next outside step found in the record, not
  into it. Without that, the half-way point of the first of three bursts was found past the third, and all three became
  one window. With several experiments, pass 0's windows are `[k − P, half)`, the last held out whole, as rule 3 does
  for later passes.
- *"Pass i−1" is the kept pass* (the plan review's safer reading). Pass i is sized from the kept pass's τ and compared
  with it, and "not run: pass j found no process" names the kept pass. The early stop compares with every window
  already fitted ("not run: its windows are pass j's"), so the same window is never fitted twice. After a "not kept"
  or "not found" pass 1, pass 2 is sized from pass 0 again, gets pass 1's windows and stops. Test 5 checks this, with
  two `ident.identify` calls in all.
- *Short steps and an earlier pass.* When a later pass finds a step short that the kept pass fitted, the kept result
  gets that line in its `why` and is not proposable, before the comparison ("a window the process says is too short is
  not trusted from an earlier, shorter window either"). Without this, case (d) of test 6 kept pass 0, which had fitted
  both short steps.
- *`dropped`* holds one line per step: the kept pass's line, else the first pass that dropped it.
- *Rule 6 in a pass ≥ 1 that leaves nothing* returns the `found: False` result, as rule 6 says, not the earlier pass.
- *Rule 2 on one input:* `outside_steps` is unchanged. It keeps the larger of two steps within P, so a burst's rise and
  fall are one step. Note that it measures the P from `k + 1`: two steps need 41 buckets between them.
- *The rule 7 text with one step* is "identified around an outside step at 14:20 (flow.asked), its window from …". The
  "excursion" form quotes the first pass line after pass 0 that is not "kept". `θ + 4τ` is the kept result's own.
- *The two-step overlap case of test 4* uses bursts 500 s apart, not 300 s. At 300 s (30 buckets) two steps on one
  input are one step by rule 2, so no overlap of two steps can occur. It uses seed 0, where pass 1 is kept, and
  `PASSES_MAX` is set to 2 so the size ⌈S/h⌉ is known from pass 0. At 550 s, pass 0 often finds an integrator from two
  short experiments, and no later pass runs.
- *Test 6(a)* puts its burst 420 s before the end, not 400 s: `outside_steps` needs at least 41 buckets after a step.
  *Tests 6(b), 6(c) and 6(d)* use τ = 120 s. With τ = 60 s, S = 260 s is shorter than the 400 s after a step that
  `outside_steps` asks for, so with several experiments no step can be short.
- *Test 7* uses an all-zero second input `d2`, missing over the second burst's window. A second burst input that moved
  with d would be collinear with it.
- *Settling and judge's span.* When S's second term binds, the fitted part spans one bucket less than 5 (τ + θ), as the
  formula is written. It was not changed.
- The excursion test of 8(ii) uses `ident.around` on its own, so it is unchanged by these pass-0 decisions.

**Breaking each guarded line (lesson-9), each failing as it should:**
- step choice restricted to the largest → test 3 fails (`experiments == 3`);
- pass ≥ 1 reusing the excursion windows → the 8(ii)-narrow test, test 4, test 5 and test 6 fail;
- forward-filling over the whole record instead of dropping → test 7 fails;
- clipping to `n` instead of dropping → test 6 fails;
- a failed later pass kept, or a worse one kept → test 5 fails.

**Not run here:**
- the whole unit suite and the four browser files under `scripts/suite_watch.py` (the factory runs them after);
- `demo_check`.

This clone has no remote, so origin/main could not be merged. Local `main` is this branch's base (8eb0fc0), so there
was nothing to merge.

Run here, and green: `tests/test_outside_experiments.py` (9 passed, 1 xfailed), `tests/test_churn.py`,
`tests/test_control.py`, `tests/test_graph_cli_web.py`, `tests/test_sd_tools.py`. `ruff check` is clean.

`tests/test_zz_scratch.py` is an untracked, empty scratch file that this session could not delete. Delete it.

**After the factory's `unit` run failed.** The tail the factory passed on stops at 39%, with no failing test, error or
summary line in it. So it does not name the test that failed, and it may be a run that was cut off or killed rather
than an assertion. That could not be reproduced here:
- The whole suite could not be run in this session (the permission was refused), so it was searched file by file.
- Every test file that reaches the changed code, mentions `control` or the docs this branch edits, or loops over the
  examples passed, alone and under `-n 4`: 1,000+ tests and no failures. They are `test_outside_experiments` (9
  passed, 1 xfailed, stable under xdist), `test_churn`, `test_control`, `test_inbox`, `test_review`, `test_numbers`,
  `test_redesign_memory`, `test_series`, `test_architecture`, `test_guide`, the `test_spec_*` files, `test_parity`,
  `test_gate`, `test_mended`, `test_extremes_closed`, `test_slowjudge`, the `test_factory*` files,
  `test_modelling_core*`, `test_dynamics_view`, `test_sandbox_attacks`, `test_changesets`, `test_cloud_arrivals`,
  `test_rollup`, `test_chains`, `test_spec_structure`, `test_closedloop`, `test_identify` and 30 more.
- The new tests take 7 s together, and no new test leaks state: every constant and `ident.identify` is changed through
  `monkeypatch`.

No code was changed in this round, because no fault was found to fix. The next step is the full `unit` output (the
failing test's name and traceback, or the watchdog's JSON line if the run was killed). `tests/test_zz_scratch.py` was
committed by the factory as "work the session left uncommitted". It holds only a docstring and runs no test. This
session could not delete it either. It should be removed before merging.

**Round 2, answering the review.** Both findings were blocking, and there were no non-blocking ones:
- *A kept integrating pass raised a TypeError in `proposals._around`* (`θ + 4τ` with τ None). Fixed: the window is
  still labelled `"process"`, since rule 4 labels any kept pass ≥ 1 that way, but it is said "… from the process
  (integrating: no settling time, so no θ + 4τ)". Test 9 now asserts that text on a crafted integrating result. Test 5
  passes its real kept-integrating result through `_around`. With the guard removed, both tests fail with the
  TypeError (2 failed), and they pass with it. SPEC's *Outside steps* paragraph names the wording.
- *`tests/test_zz_scratch.py` committed.* **Still not done.** This session was refused `git rm` on it, as earlier
  sessions were refused deletion, so it is still tracked. It holds only a docstring and runs no test. The factory or
  coordinator must `git rm tests/test_zz_scratch.py` before merging. This branch must not reach main until then.

Run in round 2, green: `tests/test_outside_experiments.py` and `tests/test_churn.py` (16 passed, 1 xfailed), and
`ruff check ergostat tests scripts`. The whole unit suite, the browser files and `demo_check` were not run here.

**Round 2, after the factory's second `unit` failure.** This tail ends at uv's "Installed 1 package", before pytest
printed anything. It has no test line, no summary, and no JSON line from `suite_watch.py`, which prints one even when
it kills a run. So the run was stopped from outside before any test reported, and no test of this branch is named in
it. No code was changed, because nothing in the tail points to a fault.
- `pytest --collect-only` collects 2041 tests without errors, so the failure is not at collection.
- Run here, one file group at a time, all green: `test_outside_experiments` and `test_churn` (16 passed, 1 xfailed).
  `test_control`, `test_items_page`, `test_factory`, `test_factory_knowledge`, `test_backlog`, `test_relations` and
  `test_relations_asof` (the files the merge of main changed) gave 175 passed and 3 skipped.
- `git rm tests/test_zz_scratch.py` was refused again in this session. The file is still tracked, and it must be
  removed before merging.

Left: the full `unit` output (a failing test's name, or the watchdog's line), and removing the scratch file.

**Round 3, answering the round-2 review.** It had four findings. Each is answered here (lesson-12):
- *`dropped` took lines from passes that were not kept* (`experiments.py`, blocking). Fixed. `dropped` now holds the
  kept pass's drops, plus any later pass's "covers" line that rule 5 copied into the kept result's `why`. That second
  part is a step the kept pass fitted and a later pass found short. Nothing else comes from a pass that was not kept.
  This replaces the round-1 decision above ("the kept pass's line, else the first pass that dropped it").
  - New test `test_a_drop_in_a_pass_not_kept_is_not_said`. On the three-burst fixture, d2 has no readings from k − P
    to pass 0's half-way point of the second burst, and has readings after it. Pass 0 drops that step. Pass 1's longer
    window fits all three steps and is kept, and the test asserts that no "has no readings" line is said. Then, with
    pass 1 monkeypatched to "not found", pass 0 stays and its drop is said.
  - With the old line put back, the test fails (`['the step at …: d2 has no readings in its window']`). With the fix
    it passes.
- *The concatenated record set no `last`* (`loop.py`, display only). Fixed. `around_step` sets `last` to the span of
  the last (held-out) experiment in the concatenation, as `_test_windows` does. So `loop.py` draws only that
  experiment, not all of them joined across their gaps.
  - New test `test_the_record_of_several_experiments_draws_only_the_held_out_one`: `identify_around` is stubbed with
    three experiments. Without the key, the test fails with `KeyError: 'last'`.
- *`tests/test_zz_scratch.py` still committed* (blocking). **Still not done.** `git rm` was refused again in this
  session. The factory or coordinator must `git rm tests/test_zz_scratch.py`. The branch must not reach main before
  that.
- *Not run by the reviewer* (the reviewer's shell was refused). Run here instead: `tests/test_outside_experiments.py`,
  `tests/test_churn.py` and `tests/test_control.py` (70 passed, 1 xfailed), and `ruff check ergostat tests scripts`
  (clean). SPEC's *Outside steps* paragraph now says both rules and names the two tests.

Not run in round 3: the whole unit suite, the four browser files and `demo_check` (the factory runs them). origin/main
was not merged again: this clone has no remote.

**Round 4, answering the round-3 review.** In this session every shell command was refused, `git status` included. So
nothing was run, removed or committed here. The edits below are in the working tree for the factory to commit.
- *`tests/test_zz_scratch.py` still committed* (blocking). **Still not done.** `git rm` was refused again. The factory
  or coordinator must `git rm tests/test_zz_scratch.py` before merging. The branch must not reach main before that.
- *A later pass left with no step, with a "no readings" drop, returns `_nothing` without saying an earlier pass found a
  process* (`experiments.py`, non-blocking). Answered. Rule 6 still applies and the result still fails closed. Its `why`
  now adds "pass j found a process on shorter windows; it is not used, since the windows its process needs have no
  readings". `dropped` is unchanged. The existing tests check `why` and `dropped` by containment, so they should be
  unaffected. **This edit has not been run or tested**, and no test asserts the new line yet.
- *Not run by the reviewer* (the tests and ruff). They were not run in round 4 either, because the shell was refused.
  The factory's suites, run after merging main (lesson-7), are still owed.

Left for the factory: `git rm tests/test_zz_scratch.py`; commit this round's two edits; run
`tests/test_outside_experiments.py`, `tests/test_churn.py`, ruff, the unit suite, the four browser files and
`demo_check`.
