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
