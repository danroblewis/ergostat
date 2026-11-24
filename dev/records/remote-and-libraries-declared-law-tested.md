# remote-and-libraries-declared-law-tested: A declared law is tested against the record: does the controller behave as configured

depends-on: [remote-and-libraries-known-controller-laws, ui-a-loop-s-panel-starts-with-a-table-law-process-h]

Problem: external-systems.md: 'where it is declared, the declaration is tested against what the controller actually did: the fit says whether it behaves as configured'. After known-controller-laws a declared law is drawn but never compared with the record; identification (ergostat/numbers/external.py:59-74, extlaw.judge at extlaw.py:349) runs only on its own fitted laws.
Change: run the declared law on the record's measured input with extlaw.run, and judge it with the identification's measures on the same held-out quarter.
Definition of done:
1. external.declared(p, spec, name, since, until) returns the declared Law judged on the record (skill one step ahead, R² run free, points), using the same grid as identify, or why not (too little record, as identify says).
2. A finding `external-law-disagrees` when the declared law's held-out skill is below 0 or the identified law's held-out error is lower by the parsimony rule's margin (the identification's own scoring): 'block B: declared kubernetes-hpa (short) fits its record worse than ...: it does not behave as configured', with the points and the window. `external-law-holds` is never a finding; the loop's panel table shows held-out fit for the declared law beside the identified one.
3. /api/loop-control for a goal whose loop holds the block includes `declared: {kind, short, skill, r2, points}`.
4. With no `law:` nothing changes (the identify tests pass unchanged).
5. SPEC §12d documents the test and its finding, with the claim limited to 'fits the record worse', not 'misconfigured'.
Files: ergostat/numbers/external.py, ergostat/web (the loop-control answer's module), docs/SPEC.md, tests/test_known_laws.py.
Acceptance tests: test_declared_law_that_matches_holds (a synthetic HPA record made by the declared law: no finding, skill > 0.5); test_declared_law_with_wrong_target_disagrees (the record made with target 0.5, declared 0.8: external-law-disagrees naming the window); test_too_little_record_says_why; test_loop_control_carries_declared.
Size budget: 150 net lines.

Area: remote-and-libraries. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
