# model-check-ratchet: a gap may not add findings to the factory's own model

depends-on: []

One reviewed, green gap (`state-times`) added 137 `ergostat check` findings to the factory's model, because the merge gates run `check` only for errors. Findings then pile up where nothing is looking.

## Definition of done
- The implementor's program compares `ergostat check` findings on the branch with those on the main it merged, by code and part. New findings send the build back into its next round with the list, before the suites.
- A definition may allow a named finding with a reason (`allows-findings: [code part: why]`). The reviewer sees each allowance.
- Calibration and fit findings, which depend on the record rather than the change, are not counted.

## Files to touch
`dev/bin/implement.py`, `dev/bin/fac.py`, `dev/prompts/definition.md`, `dev/README.md`, `tests/test_factory.py`.

## Risks
- lesson-3: a `check` that could not run on either side is a failure to compare, never "no new findings".

## Acceptance tests
- `tests/test_factory.py::test_a_build_adding_a_check_finding_is_sent_back`
- `tests/test_factory.py::test_an_allowed_finding_passes_and_is_shown_to_the_reviewer`
- `tests/test_factory.py::test_record_dependent_findings_are_not_counted`

## Size budget
70 net lines of code outside `tests/` and `docs/`.

## Where it stopped

- **The factory's unit run after round 1.** Its tail shows no test output: it stops just after `uv` installed the
  package, with no progress line, no pytest summary and no closing line from `suite_watch.py`. So no assertion stopped
  it; it was stopped from outside, or it never started its tests. I could not tie that to this branch. These files were
  re-run one at a time and all pass: test_factory (62 passed, 2 skipped), test_factory_knowledge (52 passed), and
  test_factory_sessions with test_factory_manager (23 passed). The whole suite collects (2,127 tests) and ruff is
  clean. No code was changed for it. The whole suite was not run here, because the brief forbids running it in
  parallel.
- Beyond the files to touch, `dev/bin/review.py` (the reviewer is shown each allowance) and `dev/factory.toml` (the
  `check` command) were changed. The definition asks for both, and the named files alone cannot do it.
- **Round 2 (review/model-check-ratchet-1), each finding:**
  - Extreme-conditions findings depend on load (blocking): when either side carries an `extremes-running` or
    `extremes-skipped` note, no `extreme-conditions` finding is compared on either side (implement.py new_findings,
    `fac.UNFINISHED`). The README now says this, and says a new one goes unseen until a run where both sides finish.
    Running check with no wait was the other option. It needs a new flag on `ergostat check`, which is outside the
    files to touch, so I took the narrower, reversible fix. The test (in test_record_dependent_findings_are_not_counted)
    has the branch finish one more test than main: with a note it is built, without one it is sent back. The case
    where only main is unfinished is not tested apart, because the branch inherits main's files; the code treats both
    sides the same (`mine | theirs`).
  - A finding about no part can now be allowed, as `code: why` (fac.allowances). It is tested, and definition.md and
    the README say so.
  - The brief's list: the stand-in now removes a finding's file only when the brief names that finding. So the
    second round of test_a_build_adding_a_check_finding_is_sent_back is built only if the list reached the session.
  - Scope: unchanged from round 1 (above).
  - I broke each change and watched its test fail: the unfinished drop (record test), the brief's list (sent-back
    test, which parked), and the lone-code regex (allowed test). `RECORD_FINDINGS` is now a regex instead of globs,
    to stay inside the budget: dev/bin is at 70 net lines.
  - The merge of main (9ec5588e) conflicted only in dev/factory.toml. Both sides were kept: the branch's `check` line,
    and main's `queue_coverage` and `[code_health]`.
