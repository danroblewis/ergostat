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

## Where it stopped

Built in full; nothing is left. Choices made alone, each the more reversible one:
- Only the target's current state counts. A target that moves on from a `starts_at` state to one not named (and not
  finished) blocks again, and so does a target held under a lease (state `leased`), unless `leased` is named. So name
  every state from which on the dependent may start. SPEC §5a and the agent guide say so.
- "Finished" for the refusal means the states `messages: done:` declares, or the kind's last state when it declares
  none (the item index's fallback is read at run time and cannot be checked statically). "Paused" means
  `messages: paused:`.
- A relation naming several kinds: a state is refused only when none of them has it.
- `starts_at` also takes one state as a string (the schema agrees). Any other shape is `bad-relation`.
- Codes: `starts-at-unknown-state`, `starts-at-not-precedence` (a group, `precedence: false`, or a remote's kind),
  `starts-at-finished`.

### Round 2 (answers both findings of round 1; the first and second bullets above are replaced by these)

- A leased target counts by the state it was taken from (its lease's `back`, `precedence.starts`), in the status,
  `takes: {unblocked: true}` (both in the graph and past its caps) and the Items API's `waiting`. One taken from
  `approved` still lets its dependent start; one taken from its first state still blocks it. `leased` in `starts_at`
  is refused (`starts-at-leased`): it would say nothing about where the target was taken from. Test:
  tests/test_precedence.py::test_a_leased_target_counts_by_the_state_it_was_taken_from (seen to fail with the
  lease's `back` not read). SPEC §5a and the agent guide now say so.
- The finished fallback is the kind's last state not counting the `leased` and `dead` that leases.check appends to a
  taken kind; `dead` in `starts_at` is refused as `starts-at-finished`. Test:
  tests/test_relations.py::test_starts_at_on_a_taken_kind_with_no_done_reads_its_own_last_state (a block takes the
  kind, no `messages: done:`; seen to fail with the old `t.states[-1:]`). SPEC §5a says so.
