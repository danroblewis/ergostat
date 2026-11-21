# build-failures-counted: The build-failure kill rule counts failures

depends-on: []

Audit 2026-11-21: `build_failures` has no `sum` in the gap kind's `fold`, so it stays at 1 (`1 -> 1` nine times on one gap). The limit of 6 is unreachable and a failing build can retry forever: 20 refused runs cost $17.95 in one hour.

## Definition of done
Each failed build adds one to `build_failures`, and the limit parks the gap. A later successful build or a continued gap starts from what the definition of the kill rule says, stated in `dev/README.md`.

## Files to touch
`ergostat.yaml`, `dev/bin/implement.py`, `dev/README.md`, `tests/test_factory.py`.

## Risks
- lesson-9: the test must use the real fold, not a stand-in's field.

## Acceptance tests
- `tests/test_factory.py::test_build_failures_add_up_in_the_real_fold`
- `tests/test_factory.py::test_the_sixth_failed_build_parks_the_gap`

## Size budget
15 net lines of code outside `tests/` and `docs/`.
