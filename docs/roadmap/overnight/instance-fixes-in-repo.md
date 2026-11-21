# instance-fixes-in-repo: the running factory's two remaining local fixes are in the repository

depends-on: []

A switch replaces the instance's `dev/`, so any fix that lives only there is lost, and the factory cannot upgrade itself without a person re-applying it. Two have no gap yet (`implementors-can-clean-up` and `manager-sessions` carry the others).

## Definition of done
- `resources.per_session`: when machine-wide suite slots are set (`[suites] slot`), a new session is charged only its own CPU and memory. The suites are capped by the slots and the load reading already includes those running. Charging one per session held the implementor pool at about 4 of 9.
- `dev/knowledge/decisions.md` holds two decisions: a branch carrying another gap's unlanded merge is continued, not rebased, once that merge lands; and areas the coordinator deferred stay deferred (a gap parked with `deferred: true` gets no rebuild, continue or re-plan until reopened).

## Files to touch
`dev/bin/resources.py`, `dev/knowledge/decisions.md`, `tests/test_factory_resources.py`.

## Risks
- lesson-3: a session cost that cannot be read falls back to the settings, never to zero.

## Acceptance tests
- `tests/test_factory_resources.py::test_a_session_is_charged_only_its_own_cost_when_suites_have_slots`
- `tests/test_factory_resources.py::test_a_session_is_charged_a_suite_without_slots`

## Size budget
15 net lines of code outside `tests/` and `docs/`.
