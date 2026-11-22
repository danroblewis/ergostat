# finding-structure-from-residuals: the residual finder proposes a missing delay on a stock's inflow, as a third-order DELAY3 or as an unmeasured stock in transit, when the stock's one-step residuals are coloured and the change whitens and shrinks them
depends-on: []

The gap (`docs/GAPS.md`, *Finding structure from residuals*; `docs/proposals/parity/00-modeling-review.md` §2 "Against system identification" and milestone 3). `structural.from_residuals` (`ergostat/numbers/structural.py:825`) is a stub that returns `None`. The Fit page (`review.js:284`), `CANNOT` and SPEC §12b ("*Not yet*") all say it is the next piece of work. This branch ports the narrow core of SD Lab's `hidden.py`/`hidden_transit` and the "autocorrelated → hidden stock or delay" row of `residual-diagnostics.md`. It covers one kind of missing structure: a delay between an inflow and the measured stock it fills. It does not cover a missing outflow, a missing link or cause, a replaced form (a lookup for a line), or a delay on an outflow. Those stay in `CANNOT`.

This works out residuals from the record, not from the observer's run-time series. `observer/X/innovation` exists only for stocks with `observe: true` and only while the engine runs. The finder computes the same quantity from the record (the observer's "open-loop one-step errors", `spec/observer.py:15`), so it works on every measured stock and for both before and after a change.

## Definition of done

1. **The residual** (`ergostat/numbers/residuals.py`, new; standard library only). For a measured stock X, `residuals(spec, data, run, X)` gives one value for each bucket i where X has a reading in both bucket i and bucket i−1:
   e(i) = y(i) − y(i−1) − Σ± m_f(i), summed over X's flows (+ for an inflow, − for an outflow).
   m_f(i) is what flow f moved in bucket i:
   - `run.moved[f][i]` for a flow with an equation;
   - `data.counted[f].between(edge_i, edge_i+1)` for a counted flow;
   - the held value × the bucket width in hours for a flow read as a rate.

   If any flow's m_f(i) is unknown (`None`, or a flow neither measured nor worked out), that bucket's e(i) is `None`. It is never 0 (lesson-3).

   `run` is the **residual run**: `sim.replay(spec, data, sim.plan(spec, integrate=U))`, where U is every stock that has flows and no sensor. Every measured stock is taken as read. Each stock in U starts at the window's start from its `initial:` (point 6).
   - If X has a flow from or to a stock in U that has no `initial:`, X is not examined. `not_made` says so ("fed from S, never read and with no initial: its residual cannot be worked out").
   - X is also not examined when it has readings in fewer than 80% of buckets, or fewer than `MIN_POINTS = 40` residuals are left after warm-up. Each case gets a `not_made` entry with that reason.

2. **Whiteness, with Bartlett's correction.** `whiteness(e) -> (q, coloured)`. The sample autocorrelations r_k are taken over the residuals that are not `None`, using only pairs that are both present. Then:
   q = n · Σ_{k=2..10} r_k² / (1 + 2·r_1²)

   This is Bartlett's variance of r_k for k ≥ 2 under an MA(1) null. Under a right model, reading noise makes e = w + v(i) − v(i−1), which is MA(1) with ρ1 between −0.5 and 0, so lag 1 is excused and corrected for, not tested. `coloured` is q > `CHI2_9_99 = 21.666` (χ²(9) at 0.99), which means α = 0.01.

3. **The lag: which inflow, and how long.** `lag_of(e, u, kmax) -> (k, corr) | None`. For each k in 1..kmax (kmax = min(12, n // 4), hard capped at 12), the regressor is d_k(i) = u(i−k) − u(i), which is what a k-bucket delay on inflow u leaves in the residual. The function returns the k with the largest **positive** Pearson correlation between e and d_k, over the buckets where both are present. It returns `None` when that correlation is at or below 2.576/√n_k.

   The candidate inflows of X are its inflows f with m_f known, **excluding**:
   - (a) a flow whose equation contains `DELAY1`, `DELAY3`, `SMOOTH` or `SMOOTH3` anywhere;
   - (b) a flow drawn from a stock with no sensor (an inferred transit stock, `<X>-arrives`, or a declared unmeasured one);
   - (c) a flow measured by its stock's own changes (`ob.from_its_stock`).

   If X is coloured and every inflow is excluded, `not_made` says "X's residual is coloured (q …) but its inflows are already delayed, drawn from a stock ergostat cannot read, or measured by X itself". This is the repeat guard.

4. **Candidates, two forms**, for the inflow f with the best lag k (one form per order, so the two never repeat each other). τ is tried at 0.5, 1 and 2 times k·w hours, where w is the bucket width.
   - **`residual-delay`** (third order). If f has an equation and no `from:`, its equation becomes `DELAY3(<equation>, τ)`. Otherwise f's `to:` is taken off (it leaves its source at once) and a new flow `<X>-arrives` to X is added: `equation: DELAY3(flow.f, τ)`, `driven-by: +flow.f`. The delay's stages start in equilibrium at their input's first value (existing behaviour, `spec/equation.py:386`).
   - **`residual-hidden-stock`** (first order, drawn as a stock). A new stock `<f>-in-transit` is added with no sensor, the unit of X, `initial: <f's mean rate over its first max(k, 1) buckets × τ>` (its equilibrium), and `inferred:`. f's `to:` becomes that stock. A new flow `<X>-arrives` goes from it to X: `equation: stock.<f>-in-transit / <τ name>`, `driven-by: +stock.<f>-in-transit`.

   Both forms add a parameter `<f>-delay` (unit `h`, `estimate: true`, `inferred:`). Every added part carries `inferred: PENDING` and is stamped as today (`structural.stamp`).

5. **Which candidate is offered** (the after-residual, worked out by a named run). Each candidate's edit is compiled in memory (`tr.spec_after`). Its after-residual at X comes from the residual run of the **model it leaves**: `integrate=U'`, where U' is the stocks of that model with flows and no sensor. U' contains the new transit stock, which starts from the `initial:` the edit writes, through point 6. The DELAY3 form has no new stock and runs with U' = U.
   - Before and after are compared on the same buckets: those both have, after a warm-up of ⌈3·τ_max / w⌉ buckets.
   - A candidate is offered when SSE_after ≤ 0.8 · SSE_before and q_after < q_before. The best candidate per stock (lowest SSE_after) is offered. With n ≥ 40, a 20% fall in SSE with one added parameter also lowers AIC, and the reason says both numbers.
   - The others are listed in `not_made` with their numbers.
   - A candidate whose edit does not compile, whose after-run raises or is not valid (`run.invalid`), or whose after-residual cannot be worked out is **not offered**. `not_made` says why (it fails closed).

   The proposal's `reason` states:
   - X's q before and after (against 21.67);
   - the lag k and its correlation;
   - the τ chosen;
   - SSE before and after;
   - that the residuals are the stock's change less what the model's flows moved.

   `method` names the test (Ljung–Box over lags 2 to 10 with Bartlett's correction for lag 1) and the run. `touched` is `[stock.X]`.

6. **A stock never read starts from its `initial:`.** `observe.measured` gives a stock with no sensor and an `initial:` the start `(grid.since, initial)` in `data.started`. SPEC §5 already says `initial` is "a starting value, for simulation only". The replay (`sim.replay`) then integrates the stock from there instead of holding it at 0. A stock with a sensor, or with no `initial:`, is handled exactly as today. Without this, the gate's `fit_after` of a hidden-stock proposal replays the transit stock as 0 and refuses it.

7. **Bounded.** One `find` runs at most `MOST_REPLAYS = 30` residual runs, counted at the call site (before and after runs). It examines at most 12 lags per inflow and 3 τ values per form. Once the budget is used up, each stock not yet examined gets a `not_made` entry ("not examined: the finder's budget of 30 replays was used"). These are module constants, not configuration.

8. **Said in the product.**
   - `structural.CAN` gains "a missing delay on a stock's inflow, as DELAY3 or as an unmeasured stock in transit", with the method "coloured one-step residuals (Ljung–Box with Bartlett's correction), the lag that explains them, kept when the residuals fall by a fifth and whiten".
   - `CANNOT` keeps: a missing stock or flow that is not a delay on an inflow; a delay on an outflow; a part replaced by another form; a cause named for an auxiliary.
   - The module docstring's "Not yet", the `from_residuals` docstring and `review.js:284` say what it finds and what it does not.
   - SPEC §12b (the paragraph ending "*Not yet*…") describes points 1 to 7 and the `initial:` start (point 6, also in §5's `initial` row).
   - GAPS marks the gap done for this scope, with what is *Left*: outflows, other forms, the observer's run-time innovations as a trigger, and bench recall not measured.
   - Nothing claims bench recall or SD Lab parity.

9. **No change by default otherwise.** A model with no stock that is both never read and given an `initial:` replays bit-for-bit as before. A model whose residuals are white gets no residual proposal.

10. The unit suite and the four browser files pass with rc 0 and no page test skipped; ruff is clean; origin/main is merged in and the suites are run again (lesson-7).

## Files to touch

- `ergostat/numbers/residuals.py` (new): `residuals`, `whiteness`, `lag_of`, `inflows` (the candidates after the exclusions), the residual run.
- `ergostat/numbers/hidden.py` (new): the two candidate forms, their edits, the τ trials, the replay budget, the choice per stock.
- `ergostat/numbers/structural.py`: `from_residuals(c)` calls `hidden.find(c)`; `CAN`/`CANNOT`; the module and function docstrings.
- `ergostat/numbers/observe.py`: point 6 (a few lines in `measured`).
- `ergostat/web/static/review.js`: the sentence at line 284.
- `docs/SPEC.md` (§5 `initial`, §12b), `docs/GAPS.md`.
- `tests/test_residual_structure.py` (new), `tests/test_review.py` (the stub assertion at line 641).

## Risks

- **lesson-3** (failing open): a flow unmeasured in a bucket, a stock read too rarely, a stock fed from a never-read stock with no `initial:`, or an after-run that is invalid or cannot be worked out. Any of these could be taken as 0 or "fine", which would make a residual look coloured or a candidate look good. Each must drop the bucket, skip the stock with a `not_made` reason, or fail the candidate closed.
- **lesson-4** (a limit with a floor and no ceiling): residual runs multiply as stocks × inflows × forms × τ values. Without a hard cap a large model runs hundreds of replays every ten minutes (`STRUCTURAL_EVERY`). `MOST_REPLAYS`, the 12-lag cap and the 3 τ values are hard constants, checked before each replay.
- **lesson-8** (claims wider than the code): "finds missing structure" or "ports SD Lab" would overclaim. The claim is a delay on an inflow into a measured stock, in two forms, shown on planted synthetic records. Each docs sentence maps to a test below, and bench recall is not claimed.
- **lesson-9** (tests that cannot fail):
  - A whiteness test that passes without Bartlett's correction.
  - A lag test that the refit hides when the regressor's sign is wrong.
  - A not-offered-again test whose residual is already white, so it never reaches the guard.

  Each test below is built so that the named mistake makes it fail. The implementor breaks each one and says so in the report.
- **lesson-5** (stale state under a reused id): proposal ids mask numbers (`proposals.masked`). The same delay found again with a new τ has the same id. It must be revised in place with the new τ and fit (via `pr.admit`), and a dismissed one must not be made again.
- **lesson-7** (two branches that each passed alone): `proposals-drawn-dashed-in-both` (in review) and `redesign-beside-refinement` (leased) touch `review.js` and proposals. Merge origin/main and run the suites again before saying it is built.
- **lesson-13** (staying inside the gap): bench numbers that move because of point 6 (bench cases with unmeasured stocks that have `initial:`, such as `the-job-incidents.yaml`) are reported, not "fixed" in this branch.

## Acceptance tests

All in `tests/test_residual_structure.py` unless named otherwise.

- `test_the_residual_is_the_stock_change_less_what_the_model_moved`: on a hand-built `Data` and run, the values are exact for equation, counted and read flows. A bucket where one flow is unmeasured gives `None`, not a number (lesson-3; it fails if a missing value is taken as 0).
- `test_whiteness_q_matches_the_formula`: on a fixed 50-point series, q equals n·Σ_{k=2..10} r_k² / (1 + 2·r_1²) computed by hand in the test, to 1e-9. It fails if the denominator, the lag range or the pairing is changed.
- `test_a_right_model_with_reading_noise_is_rarely_called_coloured`: 400 seeded MA(1) series, e = v(i) − v(i−1) + 0.1·w(i) with n = 200. The share called coloured is ≤ 0.03. Without the correction about 11% are rejected (≈44 of 400), so dropping it fails the test reliably (lesson-9).
- `test_lag_of_finds_a_planted_delay`: u is seeded random steps, and e(i) = u(i−k) − u(i) + noise for k ∈ {2, 4, 6}. It asserts `lag_of` returns exactly k with a positive correlation. It returns `None` when e is noise independent of u. The test fails if the regressor is u(i) − u(i−k) or the sign test is dropped.
- `test_a_missing_third_order_delay_is_proposed`: a seeded project. The truth sends `arrivals` (read as a rate, a step pattern) to `queue` through DELAY3 of 6 buckets; the model has it arrive at once. One proposal is made with code `residual-delay` and target `stock.queue`. Its edit compiles. Its reason states q before > 21.67, the lag, and SSE after ≤ 0.8 × before.
- `test_a_missing_hidden_stock_is_proposed`: the truth is a first-order transit between two measured stocks. A `residual-hidden-stock` proposal is made with a new stock that has no sensor, `initial:` and `inferred: ergostat.model-change/<id>`, and `<X>-arrives` = `stock.<f>-in-transit / <f>-delay`. Its after-numbers exist. It fails if the after-run integrates nothing (`integrate=set()`), because the arrives flow then moves 0 and the candidate is not offered.
- `test_a_stock_never_read_replays_from_its_initial`: the full replay of the model the hidden-stock edit leaves moves a non-zero amount through `<X>-arrives` in its first bucket. A model with no stock that is both never read and given an `initial:` gives identical `run.values` with and without point 6 (point 9).
- `tests/test_residual_structure.py::test_review_refresh_admits_the_hidden_stock_through_the_gate`: through `review.refresh` on the hidden-stock world, the proposal is `pending`, not refused at the gate. It fails without point 6.
- `test_a_right_model_gets_no_residual_proposal`: the same worlds with the delay already in the model, over 5 seeds. No `residual-*` proposal is made.
- `test_not_offered_again_after_a_form_is_accepted[delay]` and `[hidden-stock]`: the proposal's edit is written and the model reloaded. Then the finder runs again on a record whose truth is a longer, third-order delay, so X's residual stays coloured. The test asserts the "already delayed, drawn from a stock ergostat cannot read" `not_made` entry for X (the guard ran) and that no `residual-*` proposal targets X. Removing the exclusions in point 3 makes each case fail (lesson-9).
- `test_a_stock_whose_residual_cannot_be_worked_out_says_why`: three cases (fed from a never-read stock with no `initial:`; read in under 80% of buckets; an inflow neither measured nor worked out). Each gets no proposal and a `not_made` reason (lesson-3).
- `test_a_candidate_whose_after_run_fails_is_not_offered`: the after-run is monkeypatched to be invalid, then made to raise. The candidate is not offered and `not_made` says why (it fails closed).
- `test_the_replays_a_find_runs_are_capped`: a model with 8 coloured stocks and a counting monkeypatch on the residual run. At most `MOST_REPLAYS` runs happen, and the stocks left over get the "budget" `not_made` entry (lesson-4).
- `test_a_residual_proposal_found_again_is_revised_and_a_dismissed_one_is_not_made_again`: with the record grown and τ changed, the same id carries the new τ in its edit. After a dismiss, the next refresh does not remake it (lesson-5).
- `tests/test_review.py::test_what_ergostat_can_and_cannot_propose_is_said_and_the_residual_finder_has_its_place` (updated): `CAN` names the delay and the hidden stock; `CANNOT` still names a delay on an outflow and a part replaced; "next piece of work" no longer appears in `structural.py` or `review.js`.
- The unit suite and the four browser files, rc 0, no page test skipped; ruff clean; run again after merging origin/main.

## Size budget

450 net lines outside `tests/` and `docs/` (expected: `residuals.py` about 150, `hidden.py` about 230, `structural.py`, `observe.py` and `review.js` about 40). An overrun needs a written reason in "Where it stopped".

## Notes from the plan review (answer each)

- Point 2's q = n·Σ_{k=2..10} r_k²/(1+2r_1²) is not χ²(9) under the MA(1) null: the r_k for k≥2 are correlated (Bartlett cov at lag offset 1 is 2ρ1, at 2 is ρ1²; at ρ1≈−0.5, corr≈−0.67), so Var(q)≈33 vs 18 and the real size at 21.666 is ≈3.5–4%, not α=0.01. The 'rarely coloured ≤0.03' test would fail and the α claim is false. Replace with the quadratic form q = n·r'Σ̂⁻¹r over r_2..r_10 (Σ̂ the banded Bartlett matrix from sample r_1), or prewhiten with a fitted MA(1) then Ljung–Box lags 1..10 with 9 df; update the formula test, method text, SPEC and reason to match.
- The statistic as written is Box–Pierce, not Ljung–Box: rename it or use the n(n+2)/(n−k) weights.
- 'Also lowers AIC with one added parameter' leaves out that the inflow, k (12), τ (3) and the form (2) are all chosen on the same data; narrow it or drop it, and run the right-model test on ≥20 seeds to bound false proposals.
- Point 6 changes replay for every model with a never-read stock that has an initial:; list in the report which bench cases and existing tests move.
- Charge a stock's full 6 after-runs against MOST_REPLAYS before starting it, so it is never offered on an incomplete τ set; test the case where exactly the budget is left.
- The two forms have different ids: say whether dismissing one should stop the other from being offered for the same stock, and test it.
- The MA(1)-with-ρ1∈[−0.5,0] claim assumes no equation flow is driven by a noisy reading; a reading-driven outflow adds lag-1 structure. Note it or test it.

## Where it stopped

Built: points 1 to 9 and every acceptance test named, in `tests/test_residual_structure.py` (19 tests, all passing) and
the updated `tests/test_review.py` test. 419 net lines outside tests and docs (budget 450). Choices taken without
anyone to ask, each the more reversible one:

- **Whiteness (answering the first two plan notes).** Measured first on the test's 400 seeded MA(1) series (n = 200):
  the formula in point 2 rejects 1.75% (reading noise 0.1) and 2.25% (noise 1.0). That is under the 3%, but not
  α = 0.01. The quadratic form q = n·r′Σ̂⁻¹r over r_2…r_10 (Σ̂ Bartlett's banded MA(1) matrix: 1+2ρ², 2ρ, ρ²)
  rejects 0.5% and 1.75%. Prewhitening with a fitted MA(1) rejects up to 36% (ρ1 ≈ −0.5 is at the edge of
  invertibility), so it was not used. Built: the quadratic form, with the sample r_1 taken in **[−0.45, 0]** for Σ̂.
  At −0.5 the matrix is singular. A positive r_1 is not excused: with it, Σ̂ expects r_2…r_10 to share one sign and
  discounts exactly the slow, persistent autocorrelation a missing delay leaves. On the planted queue record that took
  q from 14 (called white) to well past 21.67. `test_whiteness_q_matches_the_formula` computes this form by hand
  (Gauss–Jordan) and checks that it differs from the uncorrected sum. The size test also patches Σ̂ to the identity
  and asserts a rejection share above 6%. It is named a Box–Pierce portmanteau in the method, `CAN`, SPEC and the
  module docstrings, not Ljung–Box. Point 8's `CAN` text is reworded to match.
- **AIC (third note).** Dropped. The reason states the SSE and q before and after, and nothing about AIC. The
  right-model test runs on 20 seeds per world (40 records), with no residual proposal made.
- **Point 6 (fourth note).** Every stock with an `initial:` in `ergostat/bench/cases/*.yaml` has a sensor, so the case
  files' replay is unchanged; the bench itself was not run. Of the existing files I ran (`test_review`,
  `test_spec_compile`, `test_numbers`, `test_modes`, `test_churn_carry`, `test_cloud_arrivals`, `test_architecture`,
  `test_chains`, `test_exercised`, `test_bench`, `test_observer`, `test_gated_actions`, `test_churn`, `test_gate`,
  `test_slowjudge`), none moved. Point 9 is tested: the queue world's `run.values` are identical with point 6
  patched out.
- **Budget (fifth note).** The model's own residual run counts as 1. A stock's six after-runs are charged before it is
  started, so a stock is never offered on an incomplete τ set. `test_the_replays_a_find_runs_are_capped` covers both
  30 (4 of 8 stocks examined, 25 runs) and exactly-the-budget-left (13 = 1 + 2·6: two examined, the third told the
  budget was used).
- **The two forms' ids (sixth note).** Dismissing either form stops both for that stock. The finder reads the
  dismissed `residual-*` proposals and says "a delay on its inflow was dismissed: not proposed again". Tested in the
  revise/dismiss test; with that guard removed, the other form is offered after the dismissal and the test fails.
  Left: the finder reads the dismissals outside `pr.locked`. A dismissal landing between the finder's read and
  `pr.admit` stops the same id (admit re-checks it) but not, on that one pass, the other form's id.
- **Reading-driven flows (seventh note).** Noted in SPEC §12b. The queue and chain worlds' outflows are driven by the
  noisy stock readings (`k * stock.queue`), so the 20-seed right-model test covers it.
- **A flow with neither `from:` nor `to:`** (outside the files to touch: `spec/compile.py`, 9 lines). Point 4's
  DELAY3 form for an inflow from outside with no equation (the `arrivals` of the named test) takes its `to:` off,
  which compile refused (`flow-without-ends`). It is now allowed only when another flow's material delay
  (DELAY1/DELAY3) takes it in, since what it moves goes into the delay's stages. SPEC §7 says so.
- **Revised in place (lesson-5)** needed `review.refresh` (outside the files to touch, 8 lines). On the same model
  version it never re-admitted a pending structural change found with new numbers. It now does so for `residual-*`
  codes only, through `pr.admit`'s existing revise path. With that removed, the revise test fails.
- **Breaking each test (lesson-9), seen to fail:**
  - a missing flow value taken as 0 (2 tests);
  - the regressor written u(i) − u(i−k) (4);
  - the point-3 exclusions removed (both not-offered-again cases);
  - the residual run with `integrate=set()` (the hidden-stock test);
  - the budget check removed (both cap cases);
  - an invalid after-run accepted (the invalid case);
  - the revision in `refresh` removed;
  - the dismissed-stock guard removed.

  Point 6 is shown in-test by patching `ob.unread_start` out: the gate test and the initial-start test both depend on
  it.
- **Not done here:** the clone has no `origin` remote, so origin/main could not be fetched or merged. Local `main`
  (5617e225) is already in the branch. The unit suite and the four browser files were not run whole (the factory and
  the merge queue run them). No page test was run; the review.js change is one sentence of text.
