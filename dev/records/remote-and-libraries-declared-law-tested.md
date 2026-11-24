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

## Where it stopped

Built, round 1: every definition-of-done item is in the code, with its acceptance test.

- Item 1: `external.declared(p, spec, name, since, until)` takes identify's own grid and split (it calls `identify`,
  cached), steps the declared law (`control/laws.law(known, dt)` on the grid's period) with `extlaw.run` and judges it
  with `extlaw.judge`: `{kind, law (skill, r2, points), why, beaten}`. Too little record: `law` None, `why` identify's
  own words. The result is kept in the identification's cache entry, keyed by the law as declared (a changed law under
  the same block is worked out again, lesson 5).
- Choices made alone (the most reversible, each a line or two):
  - The declared law's delay is searched, 0 to 6 samples, by its one-step error on the first three quarters only, as
    identify searches a delay for its laws (a declaration says nothing of the sensors' lag); only that delay counts
    against it in the score, its declared numbers being given, not fitted. "Lower by the parsimony rule's margin" is
    read as: the identified law's score (n ln(SSE/n) + k ln n, its own k) is below the declared law's (k = its delay).
  - An HPA's `every` is replaced by the grid's period, as identify's laws are on that period.
  - `/api/loop-control`'s top-level `declared` is already the goal's declared process (control/loop.py), so the
    declared law is given in `controller.declared` beside `controller.identified`, with one more field, `worse`
    (whether the finding holds), and `{kind, why}` when not judged. The loop-control answer is made in
    `ergostat/control/loop.py` (`external()`), not in `ergostat/web`, so that is the file changed.
  - The panel's table keeps its six rows (tests/test_graph_cli_web.py pins them): the *held-out fit* row adds both
    laws' fit for an external controller.
- Item 4: with no `law:`, `declared` returns None before anything is worked out; test_extlaw.py, test_demo_check.py
  and the Blocks golden hash in test_known_laws.py pass unchanged.
- Tests shown to fail when the code they guard is broken: `beaten` set whatever the score (the matching test fails),
  `disagrees` never true (the wrong-target test fails), the *fits its record worse* words dropped from the table (the
  browser test fails).
- Not run here: the whole unit suite and the four browser files (the factory and merge queue run them); main had
  nothing past this branch's base to merge.

## Entry

- **A declared law tested against the record** (SPEC §12d, *Known laws*): an external block's `law:` is stepped on the
  record's measured input on identify's grid and judged on the same held-out quarter (skill, R², points);
  `external-law-disagrees` when its skill is below 0 or the identified law scores lower, claiming only that it fits its
  record worse; `/api/loop-control` gives `controller.declared`, and the loop's table writes both laws' held-out fit.
  *Left*: the declared law run in the projection.
