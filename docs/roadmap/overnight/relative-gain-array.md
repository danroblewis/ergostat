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
