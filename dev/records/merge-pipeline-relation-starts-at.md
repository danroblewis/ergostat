# merge-pipeline-relation-starts-at: A precedence relation may name the target states at which a dependent may start

depends-on: []

## Problem
Precedence is finish-to-start only. A dependent is unblocked once each target is in a finished state (ergostat/precedence.py:93-105; ergostat/leases/ready.py:75-84). The factory's gaps wait for a dependency to be reviewed, queued, merged and pushed before they start (ergostat.yaml:115, 291; dev/model/building.yaml:209), though work could start from an approved branch. A team modelled in ergostat has the same need (a ticket that can start once another is in review). This gap is the engine part only. The factory does not use it yet.

## Change
A relation's map form takes `starts_at: [STATE, ...]`, states of the target kind (ergostat/spec/relations.py REL_KEYS, the Relation IR). A target in one of those states does not block for `takes: {unblocked: true}` or for precedence status: the item is `unblocked`, not `blocked`. The CPM forward pass and the schedule stay finish-to-start, which is conservative, and the docstring and SPEC say so. check refuses:
- a state the target kind lacks;
- starts_at on a relation that is not precedence;
- a finished or paused state named in starts_at (meaningless).
The item index and the Items API expose starts_at with the relation.

## Definition of done
1. `depends_on: {kind: gap, starts_at: [approved]}`: a gap whose only dependency is approved is taken by an `unblocked: true` block. With the dependency in fix, it is not.
2. Precedence status says unblocked for it. The critical path still waits for the dependency's finish.
3. check gives one finding for each refusal above, with a stated code.
4. SPEC §5a (Relations) and §9.5 (takes) say what starts_at does and does not change.
5. The schema (schema/ergostat.schema.json) knows the key.

## Files to touch
ergostat/spec/relations.py, ergostat/spec/ir.py, ergostat/precedence.py, ergostat/leases/ready.py (if the waiting list is built there), schema/ergostat.schema.json, docs/SPEC.md, tests/test_relations.py, tests/test_precedence.py.

## Acceptance tests
- tests/test_precedence.py::test_starts_at_lets_a_dependent_start_on_an_approved_target
- tests/test_precedence.py::test_starts_at_leaves_the_critical_path_finish_to_start
- tests/test_relations.py::test_starts_at_naming_an_unknown_state_is_refused
- tests/test_relations.py::test_starts_at_on_a_group_relation_is_refused

## Size budget
90 net lines.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
