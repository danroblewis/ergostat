# advise-gate-that-works: The advice for gating a block that takes items actually works

depends-on: []

Audit 2026-11-21, reproduced: the error for `mode: advise` on a block that takes items, and SPEC, say to gate it with "a block a person commands". The obvious reading is a `type: person` block, but `--done` records work and never sets a command, so `check` passes, the person answers, and the items stay `ready` forever. The merged test uses an `expr` gate. The working form is a `sensor: {manual: true}` read by an `expr` block.

## Definition of done
The message and SPEC name the working form and say it opens for all items, not per item. `check` refuses a person block used as such a gate.

## Files to touch
`ergostat/spec/compile.py`, `docs/SPEC.md`, the check tests.

## Risks
- lesson-8: the documented form is the one the test runs.

## Acceptance tests
- `tests/test_leases.py::test_the_documented_gate_opens_for_items`
- `tests/test_leases.py::test_check_refuses_a_person_block_as_a_gate`

## Size budget
25 net lines of code outside `tests/` and `docs/`.
