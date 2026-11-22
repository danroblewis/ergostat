# relative-gain-array: the relative gain array of a system's loops, from approved step tests, said by `explain system.NAME`
depends-on: []

## Definition of done

The relative gain array (`docs/proposals/architecture.md` §3; Bristol 1966, Skogestad and Postlethwaite §3.4, §10.6) is
worked out per system from the step tests the owner approved. It appears as one line in `explain system.NAME` when a
project is given (also through the MCP `explain` tool). The UI gets no new page or panel. A model with no systems gets
no RGA; that is stated in SPEC and is not built.

What exists and is not rebuilt: `control/steptest.py` (runs an approved test and records `steptest.started/stepped/finished`
on the stepped goal), `control/loop.py::tests_in`, `control/record.py::signals/fine/read`, `numbers/estimate.py::_invert`,
`numbers/redesign_due.py::signature`, `spec/architecture.py::_chains`.

1. **The stamp a step test carries.**
   - `numbers/redesign_due.py::signature(spec, unit, kinds=ALL)` gets a `kinds` argument. Its default keeps it byte-for-byte what it is today, so the existing redesign tests still pass unchanged.
   - New `control/rga.py::plant_signature(spec, system)` = `signature(spec, system, kinds=("stock", "flow", "auxiliary"))`. That covers the process and the parameters its equations use. Goals and blocks are left out, so accepting a `process:` or a controller `gain:` does not invalidate tests, while any change to a stock, flow or auxiliary anywhere in the system does.
   - `steptest.run` adds `"plant": {S: plant_signature(eng.spec, S) for S in _chains(spec)["goal.<goal>"]}` to `steptest.started`. That is one entry for **every** system enclosing the goal, innermost to outermost, taken just before the event is written.
   - If working out any of them raises, it writes `"plant": null` and the test still runs. The stamp exists only for the RGA, and a test the owner approved is never blocked by it.
   - `loop.tests_in` carries `plant` into each test's dict.
2. **Which tests count for system NAME** (`rga.of(p, spec, NAME)`):
   - **Which loops:** the goals whose chain contains NAME (at any depth) and for which `record.signals` gives a `u`.
   - **Which tests:** those from `tests_in(p, goal, 0, now)` that pass all four checks:
     - `how` starts with `"done"` (a stopped-early, cut-off or not-run test is left out);
     - it has `up`, `back` and `finished`;
     - its `plant` is a dict;
     - `plant.get(NAME)` is a `str` equal to `plant_signature(spec, NAME)` now.
   - **Signature failures:** if the signature now cannot be worked out, the result is "not computed: the system's signature could not be worked out". A `None` or missing value on either side never matches; equality is checked only between two strings.
   - **Cap:** at most `MOST_TESTS = 12` tests are used, the latest in record order (query order, never by comparing `time`).
3. **What each test gives:**
   - **The windows:** with `W = hold/4`, for every loop `i` it reads `u_i` and `y_i` with `record.read` on `record.fine` over `[up − W, back]`. Δ is the mean over `[back − W, back)` minus the mean over `[up − W, up)`.
   - **Missing reading:** a window with no reading for any loop's `u` or `y` leaves the test out, with the reason "no reading of X".
   - **Not settled:** a variable whose two half-window means in the after window differ by more than `SETTLE (0.25)·|Δ| + 2·sd(before window)` leaves the test out with "not settled: X still moving at the end of its hold".
   - Left-out tests and their reasons are part of the result.
4. **The guards, in order. Each gives `{"computed": False, "why": ...}`, said as "Relative gain array: not computed: WHY":**
   1. Fewer than 2 loops → `None`, and explain prints no line.
   2. More than `MOST_LOOPS = 8` loops → why names the count.
   3. A loop whose goal's `process:` is integrating, or whose `signals.known` says it is an integrator → why names the goal and says an integrator has no steady-state gain.
   4. Fewer used tests than loops → why gives both counts.
   5. A loop with no used test of its own → why names those goals.
   6. `ΔU` (tests × loops, each column scaled by its RMS): if `_invert(ΔUᵀΔU)` is `None` → "the moves were collinear". Otherwise if `sqrt(cond₁(ΔUᵀΔU)) > COND = 100` → "nearly collinear", with the number.
   7. `G` from least squares (`ΔY = ΔU Gᵀ`): if `_invert(G)` is `None` → "the gains found are singular".
5. **The result:**
   - Λ = G ⊙ (G⁻¹)ᵀ. The line gives each loop's λ on the pairing as built (its own `u`) and the number of tests used.
   - A λ < 0 adds "never pair on a negative relative gain: GOAL".
   - A λ > `FIGHT = 10` adds "the loops fight: GOAL".
   - With exactly 2 loops, when |λ₁₂ − 1| < |λ₁₁ − 1| it adds "swapped, λ X: pair A with B's u instead".
   - The pure math sits in `rga.solve(du, dy, goals)` so it can be tested without a record.
6. **Docs:**
   - SPEC §12d gets a paragraph saying exactly what is computed: the gains as held over the last quarter of each hold, the 1-norm condition estimate, the pairing as built, and systems only.
   - `docs/proposals/architecture.md` §3: "Computed today" is updated.
   - `docs/GAPS.md`: the relative gain array comes off *Left*.
   - `docs/AGENT-GUIDE.md` gets a sentence where it describes `explain system.NAME`.

## Files to touch

- `ergostat/control/rga.py` (new)
- `ergostat/control/steptest.py` (stamp)
- `ergostat/control/loop.py` (`tests_in` carries `plant`)
- `ergostat/numbers/redesign_due.py` (`signature(..., kinds=)`)
- `ergostat/spec/explain.py` (`Explainer.system`: the line, only when `self.p` is set)
- `tests/test_rga.py` (new)
- `docs/SPEC.md`, `docs/proposals/architecture.md`, `docs/GAPS.md`, `docs/AGENT-GUIDE.md`

## Risks

- **lesson-5:** a test made for the system as it was is used after the system changed. Examples: a part elsewhere in NAME (outside the stepped goal's inner subsystem) is changed, or the stamp covers only the innermost system. The stamp holds every enclosing system and is compared to NAME's own.
- **lesson-3:**
  - A stamp or signature that can't be worked out, if `None == None` were allowed to match, would let any test in.
  - A missing reading read as 0.
  - An unknown process assumed self-regulating. Integrating loops are refused, and an unsettled step is left out.
  - A stopped-early test used.
- **lesson-9:** guards with no test that fails alone. Every guard in point 4, and each left-out reason in points 2 and 3, gets its own test. The implementor breaks each guard in turn and reports that its test fails.
- **lesson-8:** claims wider than the code: "open-loop gains" when other controllers act, "steady state" when not settled, a condition number called 2-norm. SPEC says exactly what is computed (point 6), and test 2 shows that other controllers acting still give the open-loop gains.
- **lesson-4:** unbounded loops or tests. `MOST_LOOPS` and `MOST_TESTS` are constants, not config, and are tested.
- **lesson-2:** "latest tests" chosen by `time` with `>=`. Record order is used instead.
- **lesson-7:** merge origin/main (the redesign signature has other users) and run both suites again.

## Acceptance tests

All in `tests/test_rga.py`. The fixtures write a system `plant` holding two (or three) loops, each with a setting its controller steps, plus the step-test events and sensor readings of a linear plant G = [[1, 0.4], [0.5, 1]] (λ₁₁ = 1.25).

1. `test_two_interacting_loops_give_their_relative_gains`: λ = 1.25 ± 0.02 for both loops, and `explain system.plant` with the project prints that line.
2. `test_the_other_loops_acting_still_give_the_open_loop_gains`: the unstepped loop's `u` compensates, so its Δy is about 0. λ is still 1.25 ± 0.05.
3. `test_steptest_run_stamps_every_enclosing_system`: with the goal in `inner` ⊂ `plant`, `steptest.started.plant` has both keys, each equal to `plant_signature` (FakeEngine as in `test_control.py`).
4. `test_steptest_run_writes_no_stamp_when_the_signature_fails`: `plant_signature` is monkeypatched to raise. The test still finishes `done`, and `plant` is null.
5. `test_a_change_elsewhere_in_the_system_leaves_old_tests_out`: tests of a goal in `inner`, then a flow directly in `plant` (outside `inner`) changes its equation. The result is not computed, naming the goal with no usable test.
6. `test_a_change_outside_the_system_keeps_its_tests`: a part outside `plant` changes, and λ is still computed.
7. `test_a_change_to_a_controller_gain_keeps_the_tests`: a block's `gain:` changes, and λ is still computed.
8. `test_a_test_with_no_stamp_is_left_out`: a test with `plant` missing or null is left out with its reason.
9. `test_none_never_matches_none`: the signature now and the stamp are both monkeypatched to `None`. Not computed.
10. `test_an_unworkable_signature_now_is_not_computed`: the signature raises at `of`, giving "could not be worked out".
11. `test_a_test_stopped_early_is_left_out`.
12. `test_a_step_not_settled_by_the_end_of_its_hold_is_left_out`.
13. `test_a_missing_reading_leaves_the_test_out`: there is no `y` reading in one test's after window. That test is left out with "no reading of", and the result is not computed.
14. `test_collinear_moves_are_not_computed`: `solve` with proportional rows.
15. `test_nearly_collinear_moves_past_cond_are_not_computed`: `solve` with rows (1, 1) and (1, 1.01). The rows are of full rank, and the why gives the condition number.
16. `test_singular_gains_are_not_computed`: `solve` with ΔU well conditioned but ΔY making G singular.
17. `test_an_integrating_loop_is_not_computed_and_says_why`: the goal's `process: integrating`, and the why names it.
18. `test_fewer_usable_tests_than_loops_is_not_computed`: 1 test for 2 loops, and the why gives the counts.
19. `test_a_loop_with_no_usable_test_is_named`: 3 loops, 3 tests (two of A, one of B). The why names C.
20. `test_more_than_most_loops_is_not_computed`: `MOST_LOOPS` monkeypatched to 2, with 3 loops.
21. `test_a_system_with_fewer_than_two_loops_has_no_line`: `of` returns `None`, and explain has no "Relative gain" line.
22. `test_a_large_relative_gain_says_the_loops_fight`: G gives λ > 10.
23. `test_a_negative_relative_gain_says_never_pair_on_it`.
24. `test_a_better_pairing_swapped_is_said`: G = [[0.3, 1], [1, 0.3]].
25. `test_only_the_latest_tests_are_used`: `MOST_TESTS` is monkeypatched. Older tests that would make ΔU collinear are not read.

Existing `tests/test_control.py` and the redesign tests pass unchanged.

## Size budget

270 net lines:
- `rga.py` about 200
- `steptest.py`, `loop.py`, `redesign_due.py` about 20
- `explain.py` about 10
- the margin, 40

## Notes from the plan review (answer each)

- Lesson-5: plant_signature uses kinds=(stock, flow, auxiliary), and the plan claims this covers the parameters the equations use. No test changes one. Add test_a_parameter_change_in_the_system_leaves_old_tests_out (change a constant/parameter value inside `plant` but outside `inner`, and expect not computed). If parameters are their own kind in signature(), add that kind to the tuple.
- Lesson-5: blocks are left out of the stamp, so rewiring a goal's controller to a different actuator keeps old tests whose recorded windows are then read against the new `u`. Either add each loop's `u` signal name to the stamp (and compare it) or put the u names into the per-system signature. Test: rewire one loop's output and expect its old tests left out.
- Lesson-9: test 9 can pass through the 'could not be worked out' path even with the str/equality check removed. Assert the exact why, and add a case where the signature now is a real string and the stamp for NAME is None or missing, which must be left out with its reason.
- Test 23 is unspecified: give the G it uses and the expected λ.
- MOST_TESTS: say whether the cap is per system or per loop. As a cap per system, the latest 12 can drop a loop's only usable test and trip guard 5 although usable tests exist. Say which is intended and test it.
- Guard 3: add a test for the signals.known integrator path, not only `process: integrating`.
- Optionally stamp `plant` on steptest.finished as well and require started == finished, so a change accepted and then reverted during a hold doesn't count.
- Show the line through the MCP explain tool once, and show that explain without a project prints no RGA line.
- Test 22: build the λ>10 case with open-loop steps (the other u held) so the COND=100 guard doesn't fire first. Say which applies and why.

## Where it stopped

Built, round 1: every point of the definition, all 25 acceptance tests in `tests/test_rga.py` and 10 more (35 pass).
208 net lines outside tests and docs (`rga.py` 182, `steptest.py` +13, `redesign_due.py` +5, `explain.py` +8,
`loop.py` 0), within the 270 budget.

The answers to the plan review, each choosing the more reversible option where nobody could be asked:

- **Parameters.** `signature()` has no `parameter` kind: it already adds every parameter the unit's equations use, and
  that stays true with `kinds=`. `test_a_parameter_change_in_the_system_leaves_old_tests_out` changes `leak-time`, a
  parameter used by a flow in `plant` but outside `inner`, and the result is not computed.
- **A controller rewired.** `plant_signature` is `signature(spec, S, kinds=("stock", "flow", "auxiliary"))` hashed
  together with each of S's loops' `(goal, u)`. That is the "u names in the per-system signature" option, one place
  instead of a second stamp. It goes past point 1's literal "=", and it is said in SPEC §12d. A gain or `process:`
  change still keeps the tests (test 7). `test_a_controller_rewired_to_another_actuator_leaves_its_old_tests_out`.
- **Test 9.** It asserts the exact why. Its second half has the signature now as a real string and the stamp
  `{"plant": None}`, and both tests are left out with "it carries no stamp of system plant at its start".
  `test_a_test_with_no_stamp_is_left_out` covers a null stamp, `{}`, a stamp without NAME, and NAME null.
- **Test 23.** G = [[1, 2], [1, 1]] with unit open-loop steps: λ11 = −1, λ12 = 2. Both loops are said "never pair on a
  negative relative gain".
- **MOST_TESTS.** The cap is per system, as point 2 says: the latest 12 usable tests in record order across all the
  system's loops. A loop whose only test is older is then named by guard 5. That is intended: it says to run a fresh
  test of that loop rather than mixing in old ones.
  `test_the_cap_is_for_the_whole_system_and_can_leave_a_loop_s_only_test_out` shows it.
- **Guard 3, signals.known.** `test_a_loop_the_model_knows_is_an_integrator_is_not_computed`: a loop whose valve
  fills its stock directly. Any `known` refuses the loop. Today `known` is only ever set for that integrator, so this
  fails closed if something else comes to set it.
- **Stamp at finish.** Done. `steptest.finished` carries `plant` too, and both stamps must equal the signature now
  (`test_a_change_during_the_test_leaves_it_out`).
- **MCP and no project.** `test_the_line_is_said_through_the_mcp_explain_tool_and_not_without_a_project`.
- **Test 22.** It uses open-loop steps: ΔU is the identity, so the COND guard cannot fire first. G = [[1, 0.95],
  [0.96, 1]], λ ≈ 11.4.

Found while building, and said rather than changed:

- **SETTLE is weak.** With W = hold/4, a first-order lag never moves the after window's two halves by more than about
  a seventh of Δ. So SETTLE = 0.25 never calls a lagging response unsettled, however short the hold is against its
  time constant. It catches a response that started late, behind a dead time near the hold (test 12 uses a dead time
  of 320 s in a hold of 400). SPEC §12d says exactly this, and calls the gains "as held over the last quarter of each
  hold", not a steady state. A tighter test is its own gap.
- **Window edges.** Each window is read on its own span, ending just before `up` or `back`. A reading taken at the
  moment of the step back was otherwise counted in the after window: Δu came out 1.82 for a step of 2.
- **Valve loops.** For a valve loop, u is its openings as a rate (`record.read`). No opening in a window counts as a
  rate of 0, which is what the record says, not a missing reading.
- **Merge (lesson-7).** This clone has no `origin`. Local `main` is the branch's base (e8d3e331), so there was nothing
  to merge. The factory's merge of origin/main and its suite runs are still to come.

Each guard and left-out reason was broken in turn, and its own test failed: fewer than 2 loops (21), MOST_LOOPS (20),
`process: integrating` (17), `known` (the signals.known test), the signature now (9, 10), `done` (11), up/back/finish
(the no-step-back test), the stamp is a str (8, 9), the stamp equals now (5, the parameter and rewire tests, the change
during the test), u in the signature (rewire), blocks left out (7), every enclosing system stamped (3), a failing stamp
(4), a missing reading (13), SETTLE (12), the cap (25 and the per-system cap test), guard 4 (18), guard 5 (19 and 5),
collinear (14), COND (15), singular G (16), and the three notes (22, 23, 24).

The fast suites after round 1: `unit` was reported failed. Its tail ends at about 81% and names no test, so the run was
cut short rather than failing an assertion. Nothing in this branch's code was changed for it:

- Every file that touches what this branch changed passes alone: `test_rga` (35), `test_control`, `test_redesign`,
  `test_redesign_memory`, `test_redesign_bench`, `test_spec_mcp_explain`, `test_architecture`, `test_inbox`, the
  explain and modelling files, and the files that read the docs (`test_unmoved`, `test_spec_schema`, `test_parity`,
  `test_factory*`, `test_backlog`, `test_churn*`, `test_code_health_coverage`).
- The whole unit suite run serially (`pytest -q tests`, 36 min): 2336 passed, 6 failed. The six are
  `test_index_files` (4), `test_modelling_ai_cap::test_two_runs_cannot_both_take_the_last_of_the_cap` and
  `test_store_conformance::test_a_second_instance_threads_and_processes_lose_nothing[sqlite]`. Each fails in a spawned
  child with `cannot import name 'Empty' from 'queue' (/work/dev/bin/queue.py)`. The cause is
  `tests/test_backlog.py:23-24`, which puts `dev/bin` first on `sys.path` and leaves it there. A spawned child of the
  same process then imports the factory's `queue.py` instead of the stdlib's. Run alone, those files pass (57 passed).
  This is on main and outside this gap (lesson 13). It can hit any xdist worker that runs `test_backlog` before a
  spawn test. The fix (restore `sys.path` after `test_backlog`'s import) belongs to its own gap.

The fast suites after round 1, again: `unit` failed with one `F` at about 29%. The factory asked for a fix, so the
cause above is fixed here, in tests only. It goes outside Files to touch, and that is said here. `tests/test_backlog.py` gets
a module-scoped fixture that puts `sys.path` back after the file. `tests/test_factory.py::test_two_gaps_editing_gaps_md_merge_cleanly`
uses `monkeypatch.syspath_prepend` in place of a bare insert. No bound or assertion changed. Before the fix, `test_backlog` then
`test_index_files` in one process failed 4. After it, they pass (25 passed with the factory test). `test_backlog` then the
`test_modelling_ai_cap` and `test_store_conformance` spawn tests pass too (19 passed). The change is easy to undo: two test files.

Round 2: no review findings came back, so nothing was changed in the code. The factory merged main (a6a9ebdb) into the
branch (09308037). After that merge I checked that `signature()`'s default `ALL` is still exactly
`architecture.PARTS`'s five kinds, so the redesign signature is byte-for-byte what it was. Then I ran these files one at a time, and
all passed: `test_rga` (35), `test_control` + `test_redesign` + `test_redesign_memory` + `test_spec_mcp_explain` +
`test_architecture` (89), `test_backlog` + `test_index_files` + `test_redesign_bench` (33, in one process: the
`sys.path` fix holds), `test_factory` (116, 2 skipped, as on main), and `test_unmoved` + `test_spec_schema` +
`test_parity` + `test_inbox` (92). Ruff is clean. I did not run the whole unit suite or the browser files. They are
left to the factory's watchdogged run.

Round 3, answering both findings of the review:

- **An integrator nobody declared** (rga.py, lesson-3/8; blocking). It was right: with W = hold/4, a ramp's after-window
  halves differ by exactly 1/7 of Δ whatever the slope, always under SETTLE = 0.25. `SETTLE` is now **0.03**. That goes
  past point 3's literal "SETTLE (0.25)", as the review allowed ("a settle share below 1/7 justified"). The reason, for
  a first-order lag of time constant τ (share = the halves' difference over Δ): 0.008 at τ = hold/5, 0.016 at hold/4
  (97% of its gain held), 0.030 at hold/3 (93%), 0.053 at hold/2 (82%). A ramp gives 0.143. So 0.03 leaves out any ramp
  with almost 5× margin, and any lag longer than about a third of the hold, while keeping the lags whose held gain is
  within about 7%. The `2·sd(before)` term from point 3 is unchanged, so a ramp whose Δ is within about 18 times the
  noise before the step (2 / (1/7 − 0.03)) still passes. SPEC §12d says so. A slope comparison would be a second
  check for the same thing, so I took the single constant, which is easier to undo. New tests:
  `test_a_ramp_or_a_lag_far_from_settled_is_left_out[undeclared-integrator]` (dy/dt = 0.005·G(u − 25), no `process:`,
  no `known`; both tests left out as not settled, not computed) and `[lag-of-half-hold]` (τ = 200 s in a hold of 400).
  `test_a_lag_of_a_quarter_of_the_hold_still_counts` (τ = 100 s, λ 1.25 ± 0.05) keeps it from going too tight.
  Broken in turn: SETTLE = 0.25 fails both cases of the first test, and SETTLE = 0.005 fails the second. SPEC §12d and
  `docs/proposals/architecture.md` §3 now say that only declared integrators (and a u that fills its stock) are refused
  by name, and that an undeclared one is left out as not settled. Budget: rga.py +3 lines, 211 net in all.
- **The sys.path fix** (tests/test_backlog.py, tests/test_factory.py, lesson-13; not blocking). Removed: both files are
  again exactly main's (`git diff main` on them is empty). This puts back the leak described above: on main,
  `test_backlog` leaves `dev/bin` first on `sys.path`, so a spawn test later in the same xdist worker can import the
  factory's `queue.py`. If the unit suite fails in `test_index_files`, `test_modelling_ai_cap` or
  `test_store_conformance` with `cannot import name 'Empty' from 'queue'`, that is this on main and not this branch.
  Its fix belongs to its own gap.

Run in round 3, one file group at a time: `test_rga` (38 passed), `test_control` + `test_redesign` +
`test_spec_mcp_explain` + `test_architecture` (84), `test_backlog` + `test_unmoved` + `test_spec_schema` +
`test_parity` (81), `test_factory` (126, 2 skipped). Ruff is clean. The whole unit suite and the browser files were not
run by me. No origin remote is in this clone, so origin/main could not be merged here (lesson-7). The branch already
has main d697b89e merged in.

Round 4: the factory merged main (93d433d9) into the branch. It conflicted in `ergostat/spec/explain.py`, where
`Explainer.system` gained main's `lines += self.vsm(name)` at the spot where this branch adds the RGA line. Both were
kept, the RGA line first and then the VSM lines, all under `if self.p is not None` (992b1020). The one finding, "not
merged: the fetched branch is not the reviewed commit", is about the queue and asks for no code change. The branch is
now the merged commit, ready for review again. Nothing else changed. Run in round 4, one group at a time: `test_rga`
(38 passed), `test_control` + `test_redesign` + `test_spec_mcp_explain` + `test_architecture` (84),
`test_vsm_review` + `test_unmoved` + `test_spec_schema` + `test_parity` (78). Ruff is clean. I did not run the whole
unit suite or the browser files.
