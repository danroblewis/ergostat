# eigenvalue-elasticity: the stocks' modes at the model's start (eigenvalues of their Jacobian) and each link's eigenvalue elasticity, shown by `explain`
depends-on: []

## Definition of done

The gap: `docs/proposals/architecture.md` §4 says eigenvalue elasticity at the start is "a small step", because one Jacobian is already taken for time constants. GAPS' Modelling entry lists "eigenvalue elasticity" under *Left*. Today `numbers/extremes.py::time_constants` keeps only the diagonal of that Jacobian, and `time-scales` says it is "a screen, not the system's modes". Nothing computes eigenvalues, eigenvectors or elasticities. The replay-long elasticities and aggregation stay out of scope.

When done, all of the following is true:

1. **One Jacobian, shared.** `simulate._Stepper` gets `jacobian(state) -> (J, faulted)`:
   - `J[(i, j)]` = ∂(net inflow of stock i)/∂(level of stock j), per hour, over the live stocks.
   - It is the forward difference that `rates()` uses today, with the same step `h = max(|x|·1e-4, 1e-6)`. Columns of stocks no equation reads are 0.
   - `faulted` lists the equations that recorded a fault or error during the perturbed evaluations. `c.faults` is saved and restored as `rates()` does now.
   - `rates()` is rewritten to sum `jacobian()`'s entries. Its returned bound, `diag` and `coupling` are unchanged.
   - In `numbers/extremes.py`, the start-state set-up inside `time_constants` (the `_data` call, `_Stepper`, `V`, `state`) moves into one helper `_at_start(spec, pl, cond, scales) -> (st, state)`. Both `time_constants` and the new modes use it, so both work from the same point and the same differences. Mandatory: modes has no difference scheme of its own.
2. **`ergostat/numbers/modes.py`** (new; standard library only).
   - `at_start(spec) -> Modes` with `Modes(why: str | None, stocks: list[str], modes: list[Mode])`.
   - `Mode(value: complex, tau_h, period_h, links: dict[(row_ref, col_ref), complex] | None, why: str | None, most_in: str | None)`.
   - `of_matrix(J, refs) -> Modes` is the pure-math core that the tests call directly.
   - Method:
     - Reduce J to Hessenberg form, then run complex single-shift QR with a Wilkinson shift.
     - Find the right eigenvector v by inverse iteration on J, and the left eigenvector w by inverse iteration on Jᵀ, with the same λ (unconjugated).
     - ∂λ/∂a_ij = w_i v_j / (wᵀv). Elasticity ε_ij = (a_ij/λ)·∂λ/∂a_ij.
     - Participation of stock k: |w_k v_k| / Σ|w_k v_k|. `most_in` is the stock with the largest participation.
   - **Links:**
     - Every entry of J is a link. Off-diagonal `(i, j)` is "stock.j → stock.i". A diagonal entry is the stock's own link, said "stock.i (its own)" (its own drain or growth). Diagonal entries count as links and are ranked with the rest.
     - Entries with a_ij = 0 have ε = 0 and are not listed.
     - Rank by |ε| descending, ties broken by (row ref, column ref) name order.
   - **Complex values:**
     - ε is stored as the complex value.
     - Ranking and display use |ε|. A real mode shows the signed real ε (`ε -2.00`). A complex mode shows `|ε| 0.41 (0.33-0.24i)`.
     - λ counts as real when |Im λ| ≤ 1e-9·max(1, ‖J‖∞). Its imaginary part is then set to 0 and its vectors are taken real.
     - A conjugate pair is listed once (Im > 0), said "±".
     - Over all entries Σε = 1 for every mode with elasticities.
   - **Time constants:** τ = 1/|Re λ| hours. A mode with Re λ > 0 is said "grows, e-folding every τ". A complex mode has period 2π/|Im λ|.
3. **No inf or NaN is ever read as an answer** (lesson-3). Each input that can be missing or bad gives `why`, never a number. These are checked in this order, and each returns before the later steps:
   - (a) **More than `MOST = 40` live stocks.** Returns before `_at_start` or `jacobian` is called: "N stocks move by equations, more than 40: modes are not worked out (pure-Python eigenvectors are O(n³) a mode)". 40 is a module constant, not config.
   - (b) **No equation reads a stock** ("the stocks do not feed back through any equation: no modes").
   - (c) **The equations fail at the start.** This covers ArithmeticError or ValueError raised from `evaluate`, and any fault or error recorded in the start evaluation or in `faulted` (for example "divided by 0", which the stepper substitutes with 0). The reason names the equation and the fault, as `_Stepper.faults()` words it.
   - (d) **A non-finite entry in J**, named as "stock.j → stock.i is nan".
   - (e) **QR does not converge within `30·n` iterations in total.** `why` says so, and no partial eigenvalues are given.
   - Per mode, `links` is None and `why` is set when:
     - **λ = 0** (|λ| ≤ 1e-9·‖J‖∞, or ‖J‖∞ = 0): "no decay (a conserved quantity, or a stock nothing drains): elasticities are not defined at λ = 0". τ is None.
     - **Repeated:** another eigenvalue lies within 1e-6·‖J‖∞, or |wᵀv| ≤ 1e-8·‖w‖₂‖v‖₂ (defective). Said "repeated eigenvalue: not differentiable there; elasticities not given". Both checks apply; the second is a backstop and is unit-tested on its own.
     - **Inverse iteration fails:** the residual ‖Jv − λv‖∞ > 1e-8·‖J‖∞·‖v‖∞ after 3 iterations. Said "eigenvector not found".
   - **An exact eigenvalue as the shift:** inverse iteration shifts by σ = λ + δ with δ = 1e-10·‖J‖∞. A pivot that is still exactly 0 is replaced by 1e-14·‖J‖∞ (LAPACK's practice). So J − λI that is exactly singular still yields v.
4. **Shown by `explain`, nowhere else.** No new page or panel, and no `check` note.
   - **`explain` (model)** adds "Modes at the start (eigenvalues of the stocks' Jacobian, one evaluation of the equations, no run; a delay's stages are not states here: its time is in time-scales):". It lists up to 8 modes, slowest first (λ = 0 first), with "and N more" beyond that. Each line gives λ per hour, τ (or period), its 3 strongest links with ε, and `most in stock.X`. When `why` is set it prints "Modes: not worked out: <why>".
   - **`explain system.NAME`** lists the modes whose `most_in` stock is in that system at any depth.
   - The model is computed once per Spec, cached in `spec.lookups().kept["numbers.modes"]`.
   - `explain` imports `ergostat.numbers.modes` only when some flow or auxiliary has an equation (the same guard as `architecture.taus`). `check` never imports or computes it.
5. **Docs** say only what the tests show:
   - SPEC (the architecture section beside time-scales): a "Modes" paragraph saying that modes are:
     - at the start only, linearised by the forward differences;
     - for stocks only;
     - capped at 40 stocks;
     - never computed by `check`;
     - and that it lists the λ = 0, repeated and failure outputs.
   - `docs/proposals/architecture.md` §4: modes and elasticities at the start move to *Computed today*. Over the replay stays *Not computed*.
   - GAPS' Modelling entry: "eigenvalue elasticity" leaves *Left*; "aggregation from loop dominance" and "elasticity over the replay" stay.
   - No claim of speed.
6. Done is the house's done: the acceptance tests pass; the unit suite and the four browser files pass with rc 0 and no page test skipped for want of a port; ruff is clean; `demo_check` passes (no example is changed); origin/main is merged in and the suites are run again.

## Files to touch

- `ergostat/numbers/modes.py` (new)
- `ergostat/numbers/simulate.py` (`_Stepper.jacobian`; `rates` built on it)
- `ergostat/numbers/extremes.py` (`_at_start`, used by `time_constants`)
- `ergostat/spec/explain.py` (`model()`, `system()`)
- `docs/SPEC.md`, `docs/proposals/architecture.md`, `docs/GAPS.md`
- `tests/test_modes.py` (new)
- `docs/roadmap/overnight/eigenvalue-elasticity.md` (this definition, the first commit)

## Risks

- **lesson-3** (failing open): the stepper substitutes 0 for a division by zero, so a faulting equation would give a plausible but wrong J. Also λ = 0, defective eigenvalues, a NaN entry, QR non-convergence and an empty Jacobian could each come out as inf, NaN or "no modes" read as fine. Each has a defined `why` (§3) and a test.
- **lesson-4** (a limit with no ceiling): the cost grows as n³ per mode, and QR has no natural end. `MOST = 40` stocks and `30·n` QR iterations are hard constants. The cap returns before any evaluation.
- **lesson-8** (claims wider than the code): "modes of the system" when delay stages are not states; "check is unaffected"; "agrees with time constants". Each is narrowed to what a test shows: stocks only (said in the output), the import test, and bit-exact diagonal agreement through the shared helper.
- **lesson-9** (a test that can't fail):
  - A triangular J gives cross-link ε = 0, so "names the strongest link" could not fail. The ranking tests use coupled pairs with nonzero hand-computed cross ε, asserted numerically.
  - Σε = 1 holds only if the formula is right.
  - Each test below names the break that fails it.
- **lesson-10** (load-dependent timing): no wall-clock assertions anywhere. The cap is proven by a monkeypatched evaluation that raises.
- **lesson-7** (merged branches): `simulate._Stepper.rates` is on the hot path of replay, projection and extremes. Refactoring it must leave every existing simulate, extremes and closedloop test passing after origin/main is merged.
- **lesson-13** (staying in the gap): an unrelated suite failure is named and reported, not fixed here.

## Acceptance tests

All in `tests/test_modes.py`. Matrices are written with stocks ordered (x, y), with J[i][j] = ∂(net of i)/∂(level of j) per hour. Exact-matrix tests call `of_matrix` and assert within 1e-9. Model tests assert within 1e-6 relative.

- `test_a_coupled_pair_gives_hand_computed_elasticities`: J = [[−1, 1], [−2, −4]].
  - λ = −2: ε = [[1, 1], [1, −2]], so ε(x own) = 1, ε(y→x) = 1, ε(x→y) = 1, ε(y own) = −2.
  - λ = −3: ε = [[−1/3, −2/3], [−2/3, 8/3]].
  - Σε = 1 for each mode.
  - The first-ranked link of each is "stock.y (its own)".
  - Fails if v and w are swapped, w·v is conjugated, or a_ij/λ is dropped.
- `test_a_complex_pair_ranks_a_cross_link_first_by_modulus`: J = [[−1, 2], [−1, −1]], λ = −1 ± i√2, listed once with Im > 0.
  - ε(x own) = ε(y own) = (1+i√2)/6, with |ε| = √3/6.
  - ε(y→x) = ε(x→y) = (2−i√2)/6, with |ε| = √6/6.
  - The first-ranked link is "stock.y → stock.x" (the modulus wins, and the tie goes by name).
  - The display shows `|ε| 0.41 (0.33-0.24i)`, and period 2π/√2 h.
  - Fails if ranking uses Re ε (the own links have Re 1/6 < 1/3, but this asserts the order exactly) or if the conjugate is listed twice.
- `test_a_zero_eigenvalue_gives_no_elasticities_and_the_other_mode_does`: J = [[−1, 0.5], [1, −0.5]] (a conserved total).
  - λ = 0 has `links is None`, τ None, and `why` contains "λ = 0".
  - λ = −1.5 has ε = [[4/9, 2/9], [2/9, 1/9]].
  - No inf or NaN appears anywhere in the result or in `explain`'s text.
  - Fails if the λ = 0 guard is removed (division by zero, or inf).
- `test_repeated_and_defective_eigenvalues_give_no_elasticities`: diag(−1, −1) and [[−1, 0], [1, −1]].
  - Every mode has `links is None` and `why` contains "repeated".
  - Fails without the closeness check (the defective pair splits by about 1e-8).
- `test_w_dot_v_near_zero_is_refused_on_its_own`: the elasticity helper, called with w orthogonal to v, returns the "repeated" why and no numbers.
- `test_inverse_iteration_at_an_exact_eigenvalue_finds_the_vector`: J = [[−1, 0], [1, −3]], with the vector helper called at λ = −1.0 and −3.0 exactly.
  - The residuals are within bound.
  - ε = [[1, 0], [0, 0]] and [[0, 0], [0, 1]].
  - Fails without the δ shift or pivot replacement (ZeroDivisionError).
- `test_qr_that_does_not_converge_says_why`: monkeypatch the iteration cap to 1 on a 3×3 coupled matrix. `why` mentions convergence and `modes == []`.
- `test_equations_that_fault_at_the_start_say_which`: a model where `flow.out` = `stock.x / stock.y` and y starts at 0.
  - `at_start(spec).why` names `flow.out` and "divided by 0", with no modes.
  - Fails if the fault check is dropped (the stepper's 0 substitution would give a J).
- `test_equations_that_raise_at_the_start_say_why`: monkeypatch `_Stepper.evaluate` to raise ValueError. `why` says the equations fail at the start, with the message.
- `test_a_non_finite_jacobian_entry_is_named` (parametrised nan and inf): monkeypatch `_Stepper.jacobian` to return that entry. `why` names "stock.y → stock.x", and no eigenvalues come out.
- `test_no_equation_reading_a_stock_gives_why_not_an_empty_answer`: equations exist but read only parameters. `why` is set and `explain` prints "Modes: not worked out".
- `test_more_than_most_stocks_returns_before_the_jacobian`: a generated model of MOST+1 chained stocks, with `extremes._at_start` and `_Stepper.jacobian` monkeypatched to raise. `why` names 41 > 40. Fails if the cap is checked after building.
- `test_the_model_pair_matches_its_matrix`: a model PAIR whose parameters give J = [[−1, 1], [−2, −4]]:
  - `x-in` from a cloud is `stock.y / 1h`;
  - `x-out` is `stock.x / 1h`;
  - `y-out` is `stock.y / 15m`;
  - `y-taken` is `stock.x / 30m`.

  Its J and the ε of the first test agree within 1e-6, and `explain` prints both modes with τ 30m and 20m.
- `test_the_diagonal_is_exactly_what_time_constants_used`: the TIMES model with a nonlinear drain (`stock.slow * stock.slow / ...`), so a different step would change the diagonal.
  - −J[(s, s)] == `_Stepper.diag[s]`, bit for bit.
  - 1/(−J[(s, s)]) == `time_constants(spec)[f"stock.{s}"]`, compared with `==`.
  - Fails if modes takes its own differences.
- `test_rates_is_unchanged_by_the_shared_jacobian`: on the PAIR and TIMES models, `rates()`'s bound, `diag` and `coupling` equal the row sums computed by hand from `jacobian()`. The existing simulate, extremes and closedloop tests also pass unchanged.
- `test_a_growing_mode_is_said_to_grow`: a stock with inflow `stock.x / 1h` and no drain. λ = +1, ε(own) = 1, and the text has "grows, e-folding every 1h".
- `test_explain_system_lists_the_modes_most_in_it`: TIMES with `fast` in system `a` and `slow` in system `b` (λ = −10 and −0.5).
  - `explain system.a` lists only λ = −10, and `explain system.b` lists only −0.5.
  - Fails if `most_in` is ignored or the participation is taken from v alone.
- `test_check_never_imports_modes`: in a fresh `python -I` subprocess, run `check` (the CLI's function) on the TIMES model (it has equations) and on `examples/first-loop`, then print whether `ergostat.numbers.modes` is in `sys.modules`. Both are False. Also run `explain` on `examples/first-loop`: it is not imported. Fails if `architecture.py` or `check` imports modes.

For each test, the report says which break was made and that the test then failed (lesson-9).

## Size budget

330 net lines outside `tests/` and `docs/`:
- `modes.py`: about 240 (Hessenberg and QR 70, inverse iteration and the complex solve 50, elasticities and participation 35, guards, caps and `at_start` 50, wording 35);
- `simulate.py`: about +15 net;
- `extremes.py`: about +10;
- `explain.py`: about +45.

An overrun needs a written reason in "Where it stopped".

## Notes from the plan review (answer each; not blocking)

- test_a_complex_pair_ranks_a_cross_link_first_by_modulus cannot fail on its named break: for J=[[-1,2],[-1,-1]] the cross links lead by both |ε| (√6/6 vs √3/6) and Re ε (1/3 vs 1/6), so ranking by Re ε gives the identical order. Replace with a hand-computed matrix where the |ε| order and the Re ε order differ, and assert the |ε| order (lesson-9).

## Where it stopped

Built, round 1. Every acceptance test above is in `tests/test_modes.py` and passes, with three more:
`test_a_complex_pair_ranks_by_modulus_not_by_real_part`, `test_equations_that_fault_only_when_a_stock_is_moved_say_which`
and `test_an_eigenvector_not_found_is_said`. Code: 307 net lines outside tests and docs (budget 330).

**The plan review's note.** The note is right: ranking by Re ε leaves the defined test green (it was tried). No 2×2
matrix can do what the note asks while keeping the test's claim ("a cross link first by modulus"). For a complex pair,
Re ε(own) = ad/2|λ|² for both own links and Re ε(cross) = −bc/2|λ|². |ε(cross)| > |ε(own a)| exactly when −bc > a²
(and likewise for d). So a cross link first by |ε| but not by Re ε would need ad > −bc > max(a², d²), and
ad ≤ max(a², d²) rules that out. The most reversible
step: the defined test stays as written, since it still checks the display, the period, the single listing and the
tie by name. A new test, `test_a_complex_pair_ranks_by_modulus_not_by_real_part`, uses J = [[−3, 2], [−2, −1]]
(λ = −2 ± i√3). There ε(x own) = 3/14 + 5√3/14·i and |ε| = 3/√21 lead, while the cross links lead by Re ε (2/7 against
3/14). It asserts the full |ε| order and fails when the ranking uses Re ε.

**Choices made alone (each easy to undo).**
- Ties in |ε| are taken to 9 decimals, then by name. Two links that are equal by hand differ in the last bits after
  inverse iteration, and the name tie the complex test asserts would otherwise depend on rounding.
- A fault seen only while a stock is moved by the difference step is said as "the equations fault when a stock is
  moved a little from the start (the difference step): flow.X, each fault taken as 0". `jacobian()` returns the
  equations' refs, not `faults()`'s words, as defined. A fault in the start evaluation itself is worded by
  `_Stepper.faults()`.
- `explain` turns any other exception from `at_start` into "Modes: not worked out: <type>: <message>", never into
  "no modes".
- When ‖J‖∞ = 0, or λ = 0, no eigenvectors are sought, so `most_in` is None for those modes.
- Inverse iteration: the δ shift and the zero-pivot replacement each cover for the other. On the exact-eigenvalue
  test, taking out either one alone leaves it passing; taking out both fails it with ZeroDivisionError.

**Not run here.** The clone has no `origin` remote: local `main` (0216e0e5) is already in the branch, and nothing
newer could be fetched (no network). The full unit suite, the four browser files and `demo_check` were not run by
the implementor (no example is changed); the factory runs them. The touched and stepper-path files were run one at a
time, all passing.

**After the factory's unit run failed.** The factory's `unit` suite (under `-n`) reported three failures, but the
tail it gave did not name them. Running the whole suite in one go was refused here. So every test file was run
instead, serially, in batches of 2 to 23 files. All passed except one, and only inside a batch:
`test_store_conformance.py::test_a_second_instance_threads_and_processes_lose_nothing[sqlite]`. Its spawned process
imported main's `dev/bin/queue.py` in place of the standard `queue` ("no attribute 'LifoQueue'"). It passes alone
(35 passed). This branch touches neither the store nor `dev/bin`, so it is order-dependent and comes from main, not
from this branch (lesson-13). The three failures are therefore not identified. One real cost against main was found
and fixed: `jacobian()` padded J by scanning every (live, live) pair and copying the dict on each call. `rates()` pays
that once per replay window. It now pads in place, and only the columns that no equation reads. The entries,
`rates()`'s sums and their order are unchanged (test_modes, closedloop, extremes, numbers, scale_caches and rates
pass).

**After the second unit run failed.** One F, at about 8% of the `-n` run, and the tail names no test. Every file near
that point in collection order (test_act_risk through test_cloud_arrivals, 12 + 6 files) and every file that calls
`explain` was run serially: all pass, `closedloop.risk`'s 40 runs take 0.9 s against its 15 s wall budget. So the
failure is still not identified and was not reproduced here. One more cost on the replay path was taken away: `rates()`
now calls `jacobian(state, pad=False)`, so the zero columns are written only for modes (they add nothing to |row|
sums). The spy in `tests/test_modes.py` forwards keywords; no assertion changed.

**After main (e1e778c1) was merged in, round 2.** `docs/proposals/architecture.md` §4 conflicted with main's
computed rung of aggregation. Both are kept: main's aggregation text, then the modes under *Computed today*;
*Not computed* keeps elasticity over the replay and the AI rung's proposal to aggregate. Main's "Would read" was
already gone on main, and it stays gone. GAPS' Modelling entry merged without a conflict but came out with both
versions interleaved (two *Left* lists). It is now one entry: aggregation candidates and modes under done; *Left*
keeps the relative gain array, the proposal to aggregate from loop dominance, elasticity over the replay and the
rest. Eigenvalue elasticity is no longer on it. Main changed none of the code files this branch touches. Run again
after the merge, one file at a time: test_modes (22), test_closedloop, test_extremes_closed, test_numbers,
test_rates, test_aggregation, test_architecture, all passing; ruff clean. The full unit suite, the browser files and
`demo_check` are left to the factory.

**Round 3: the review's finding (lesson-3, blocking).** The finding was right. `_Stepper.evaluate` takes a NaN as 0 and
clamps a value past ±1e12, and it counts that only in `clamped`. Neither the start check nor `jacobian()`'s `faulted`
read `clamped`, so a finite but wrong J came out. The fix:
- `jacobian()` now also lists an equation whose `clamped` count grew during the perturbed evaluations. `rates()`
  ignores `faulted`, so the replay path is unchanged, and `clamped` is not reset (the same as `errors`).
- `at_start` adds each start clamp to the start faults, worded "flow.X: not a number or past ±1e+12 N time(s), taken as
  0 or clamped". The words for a fault under the difference step now say "(or clamped, past ±1e12 or not a number)".
- SPEC's Modes paragraph says a NaN or a value past ±10¹² counts as a fault, at the start and under the difference step.
- New model tests: `test_an_equation_past_big_or_nan_at_the_start_is_said` (overflow: `EXP(stock.x)` at 100; nan:
  `EXP(x)·EXP(x) − EXP(x)·EXP(x)` at 700, which is inf − inf). It also asserts that `faults()` alone is empty there.
  `test_an_equation_past_big_only_when_a_stock_is_moved_is_said` uses `EXP(stock.x · 3e7)` at 0: it is 1 at the start
  and e³⁰ at the step.
- Each break was tried. Without the start-clamp check, both start cases fail. Without the `clamped` term in
  `jacobian()`, the step case fails.
- Check (d), a non-finite entry, is still reached in practice only through its monkeypatch: the stepper never leaves
  a non-finite V. It stays as a backstop.

Net code is now 315 lines against main (`git diff --numstat main...HEAD -- ergostat`; budget 330). Run one file at a time: test_modes (25), test_closedloop, test_extremes_closed,
test_numbers, test_rates, test_aggregation, test_architecture, test_scale_caches, all passing; ruff clean. No newer
main could be fetched (there is no origin remote and no network). The full unit suite, the browser files and
`demo_check` are left to the factory.

**Round 4: the review's findings.**
- *Blocking (lesson-3): an equation left out of the plan.* The finding was right. `plan()` drops an equation whose
  parameter has no value (for example one with `estimate: true` not yet fitted) into `pl.left_out`. `_data` then holds
  that equation at its record or at 0, so `stock.x / tau` gave J = [[0]] and "λ 0/h: no decay". `at_start` now reads
  `pl.left_out` straight after the 40-stock cap, before `_at_start` or any evaluation. If a left-out equation is a
  live stock's flow, reads a stock, or is read by an equation that is run, `why` says "an equation the stocks depend
  on is not run, a parameter has no value: flow.out (tau has no value)" and no modes are given. It comes before check
  (b) on purpose: a left-out equation that reads a stock is missing from `felt`, so (b) would wrongly say "do not
  feed back". New test: `test_an_equation_with_an_unfitted_parameter_says_why_not_lambda_0`. Its cases are the drain
  itself (`stock.x / tau`) and an auxiliary `1 / tau` that feeds the drain. It also asserts that `explain` prints
  "Modes: not worked out" and no "λ 0/h". Break tried: with the check disabled, both cases fail. SPEC's Modes
  paragraph lists this reason.
- *Non-blocking, round 1's start vector (lesson-12).* Inverse iteration started from all ones, which is exactly the
  λ = 0 left eigenvector of a conserved sum. It now starts from x_k = 1 + frac((k+1)·0.618…), a vector not tied to
  the structure. It still fails closed ("eigenvector not found") if the residual bound is not met. No assertion
  changed, and test_modes passes.
- *Non-blocking, the wrap width (lesson-12).* GAPS' Modelling entry, the over-long *Left* line, is reflowed.

Net code is now 323 lines against main (`git diff --numstat main -- ergostat`; budget 330). Local main is already
in the branch. There is still no origin remote, so nothing newer could be merged. Run one file at a time:
test_modes (27), test_closedloop (15), test_extremes_closed (14), test_numbers (55), test_rates (13),
test_architecture (9), test_aggregation (10), test_scale_caches (35), all passing; ruff clean. Refused here: a shell
`for` loop over the test files, a scratch script under /tmp run with `uv run python`, a `sed -i` break toggle (it was
done with the editor instead), and `git log -1 main; git merge-base ...; git remote`. The full unit suite, the browser
files and `demo_check` are left to the factory.

**Round 5: the merge of main (b9528e0e).** The only conflict was in `docs/SPEC.md`. Main's paragraph on the AI rung
(the Viable System Model and purpose coverage) and the branch's Modes paragraph had been added in the same place,
after the architecture notes. Both are kept: Modes comes first, beside time-scales as defined, and main's AI rung
paragraph follows unchanged. Main also changed `ergostat/spec/explain.py` (it added the VSM review line). That merged
cleanly beside the modes code. Net code is still 323 lines against main (budget 330). Run again after the merge, one
file at a time: test_modes (27), test_closedloop (15), test_extremes_closed (14), test_numbers (55), test_rates (13),
test_architecture (9), test_aggregation (10), test_scale_caches (35), test_vsm_review (16), test_spec_mcp_explain (4),
all passing; ruff is clean. The resolution was first tried as an inline Python edit through the shell, which was
refused, so it was done with the editor. The full unit suite, the browser files and `demo_check` are left to the
factory.
