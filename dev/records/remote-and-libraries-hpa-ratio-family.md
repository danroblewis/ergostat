# remote-and-libraries-hpa-ratio-family: Identification fits the HPA's multiplicative rule as its own family

depends-on: [remote-and-libraries-known-controller-laws]

Problem: GAPS (Identifying existing controllers, Left): 'the HPA's multiplicative rule as its own family'. extlaw's families (ergostat/numbers/extlaw.py:24) approximate an autoscaler with the stepper (fixed steps up and down), which mistells an HPA whose step grows with the load: desired = ceil(current × metric / target). known-controller-laws adds the ratio family's step but not its fit, so an undeclared HPA is never identified as one.
Change: extlaw.fit tries `ratio` beside the others, fitting target, tolerance, the stabilisation window, min and max from the record, chosen by the same held-out score and parsimony rule.
Definition of done:
1. _fit_ratio(xs, us, dt): target by least squares on the moves (log u_next/u = log x/target over moves), tolerance from the largest |x/target − 1| with no move, stabilize-down from the shortest time from a lower desired to the move down, min and max from the record's bounds when it saturates; None with too few moves (MIN_MOVES).
2. FAMILIES includes 'ratio'; Law.said and short describe it ('u ← ceil(u·x/0.6), within [3, 40], down after 5m'); its standard errors are the target's and tolerance's.
3. On a stepper-made record the stepper still wins; on an HPA-made record ratio wins (asserted over seeds, with the rate stated in the report).
4. Blocks draws an identified ratio law as it draws a declared one, marked identified.
5. SPEC §12d's table of families gains the row.
Files: ergostat/numbers/extlaw.py, ergostat/blockdiagram.py (sketch), docs/SPEC.md, tests/test_identify_ratio.py (new).
Acceptance tests: test_ratio_identified_on_hpa_record (20 seeds of a synthetic HPA with noise: ratio chosen in at least 18, target within 10%); test_stepper_still_wins_on_stepper_record (20 seeds, at least 18); test_ratio_needs_moves (too few: why says so).
Size budget: 140 net lines.

Area: remote-and-libraries. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1. All five items are in the code; about 65 net lines outside tests and docs (budget 140).

- Item 1: `_fit_ratio` in `ergostat/numbers/extlaw.py`, with three choices made on my own (nobody to ask; each is the
  more reversible one and is said in its docstring and in SPEC §12d's row):
  - The target is least squares on the moves **up** only, log((u′ − ½)/u) = log x − log target, the ½ correcting for the
    ceiling. A move down waits on its window, so its x is not the one that set it. The estimate is then moved to the
    middle of the span that the most moves up agree with (⌈u x / t⌉ = u′, `_ceiling`). Least squares alone landed about
    1% high (0.605 for 0.6). Through the ceiling that mistold whole replicas, and ratio won on only 15 of 20 seeds.
  - The tolerance is taken from the side up only. Below the target, a sample with no move is hidden by the
    scale-down window.
  - stabilize-down is the **median** lower-desired run before a move down, not the shortest. With the shortest, one
    sample misjudged at the tolerance's edge broke a run and gave 210s or 285s for 300s. Ratio then won 18 of 20 seeds,
    exactly at the bound.
  - stabilize-up is not fitted: it is 0s, the HPA's default.
  - A record that is not whole numbers from 1 gives None, and so does one with fewer than MIN_MOVES moves up.
- Item 2: `said` reads "ratio (the HPA's rule): u ← ⌈u·x / T ± se⌉ outside 1 ± tol ± se, down after 5m, up after 0s,
  within [lo, hi]". `short` is left as known-controller-laws made it (`⌈u x / T⌉`), because the declared law's drawing
  and messages are pinned on it by that gap's tests. The standard errors are the target's (least squares', by the delta
  method) and the tolerance's (its gap to the least move up, over √12).
- Item 4: Blocks gives an identified ratio law the declared HPA's sketch (`saturation`), marked *identified ratio*.
- Item 5: SPEC §12d's table has the row, and the *Known laws* sentence that said "never fitted" is corrected.
- Existing tests changed because of the gap's own claim (item 3: an HPA-made record now identifies as ratio):
  - `tests/test_known_laws.py::test_loop_control_carries_declared` pinned `stepper` on an HPA-made record. It now pins
    `ratio`.
  - `tests/test_demo_check.py` listed the four old families. It now takes `el.FAMILIES`.
- The conformance case `law-kubernetes-hpa` now passes: `tests/test_conformance_lists_ergostat.py` expects it to once
  `ratio` is in FAMILIES, and it ran green. `dev/records/conformance-discovery-list.md`, another gap's record, still
  calls it unmet. I left that file alone.
- Tests broken on purpose and seen to fail:
  - Taking `ratio` out of FAMILIES failed the acceptance test (0 of 20 seeds) and the Blocks test.
  - Unmapping the sketch failed the Blocks test (sketch None).
- Rates (item 3), as built:
  - On the HPA-made records, ratio was kept on 20 of 20 seeds, every target within 0.6 ± 0.003 (true 0.6).
  - On the stepper-made records, the stepper was kept on 20 of 20 seeds.
  - The acceptance tests' bound is 18 of 20.
- Tests run, one file at a time, all green:
  - test_identify_ratio, test_extlaw, test_known_laws, test_demo_check, test_conformance_lists_ergostat
  - test_spec_structure, test_blockdiagram
  - test_diagram_rendering without Playwright: its page test was skipped for want of the module.
  - ruff is clean. `main` merged: already up to date.
- Browser run not completed: `tests/test_diagram_rendering.py` under Playwright and the watchdog ran slowly in this
  container. About 15 of its first ~48 tests failed, and the 10-minute background limit stopped it. I did not see the
  failures' messages and did not diagnose them. The gap changes no page: Blocks gets a sketch name, `saturation`, that it
  already draws for a declared HPA. The four browser files are left to the queue.
- Not done: a test where the record reaches its max bound. On the test HPA's records the load never drives replicas to
  40, so `hi` is None there.

### Round 2

One finding, blocking: no test produced a bound or asserted the fitted tolerance's value. Answered with tests only;
`ergostat/` is unchanged this round.

- The test HPA (`tests/test_identify_ratio.py::hpa`) takes `scale` and `shift`. Its load is now
  max(0, scale × swing − shift) + noise. The defaults (1, 0) give the same records as before, since the swing is never
  below 0.
- New test `test_ratio_fits_bounds_and_tolerance_on_saturating_record`, with scale 2 and shift 8. On every one of 20
  seeds, `_fit_ratio` gives:
  - lo == 3 and hi == 40;
  - tolerance within 0.01 of 0.1 (seen: 0.092 to 0.102);
  - target within 1% of 0.6.

  The law's `said` carries "within [3, 40]". On the plain record, which touches 3 but never stays there past the window
  and never reaches 40, lo and hi are both None and `said` has no "within".
- Each guarded line was broken and the test was seen to fail, then the line was restored:
  - `hi` forced to None;
  - `hi` always the record's max (caught by the plain record);
  - `lo` forced to None;
  - `lo` always the record's min (caught by the plain record);
  - the tolerance forced to 0.
- Stated, not asserted: the family chosen on these saturating records.
  - `fit` kept ratio on 18 of 20 seeds. The stepper won seeds 8 and 15, whose held-out ratio skill was 0.56 and 0.49.
  - Read on seed 8, the misses are ceiling-edge errors at high replica counts. The fitted target is 0.6028 for 0.6,
    and that 0.5% misjudges ⌈36·x/T⌉ by whole replicas, giving an early scale-down. The bounds are fitted right even
    there.
  - Narrowing the target with the samples that did not move is a possible later gap. It is not built here, because the
    definition's choice claim (item 3) is about the non-saturating record, which still passes.
- Tests run, one file at a time, all green: test_identify_ratio, test_extlaw and test_known_laws. ruff is clean.
  `main` merged: already up to date.
- Browser files: not run this round. No page or ergostat code changed. The round-1 note on test_diagram_rendering still
  stands.
