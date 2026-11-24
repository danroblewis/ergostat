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
