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

## Where it stopped
Built, round 1. Changes to the plan, each the most reversible choice, made with nobody to ask:
- The `advise-with-takes` message and the lease checks live in `ergostat/leases/compile.py::check`, not
  `ergostat/spec/compile.py`; the change is there (about 11 net lines of code). `spec/compile.py` is untouched.
- The message, SPEC §9.5 and the agent guide no longer offer `goal:` as a person's gate. A goal is held by
  a controller, not by a person, so it was not the form a person can open. The older
  `test_mode_advise_on_a_block_that_takes_is_refused` now asserts the new form instead of `goal:`.
- The new refusal is `person-gate`: a `type: person` block wired to command a block that takes, written on either end
  (`in: block.P` on the taker, or `out: block.TAKER` on the person). It is direct only: a person block that feeds
  an expr gate is not followed.
- docs/GAPS.md's entry for the earlier gap (mode-advise-on-a-block-that) is left as the record of what that gap did.

After the factory's unit run: its output stops at 28% with no failure or error shown, which looks like a run that
was cut off, not a test that failed. Nothing in the branch was found to change. These pass, one file at a time:
tests/test_leases.py (31), tests/test_spec_schema.py and tests/test_parity.py (34), and the six other files with
person blocks: test_blockdiagram, test_inbox, test_closedloop, test_incremental, test_triggers2, test_spec_watch
(146). No example has a person block wired to a block that takes, so `person-gate` refuses none of them. The full
unit suite was not run here; the factory's watched run must show it green.
