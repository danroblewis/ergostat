# status-projections-in-the-index: the status answer's event-log reads become indexed tables in the item index

The owner, 2026-11-22: queries should come from a standard, indexed database; the event log is kept as the record. The SQLite item index (`ergostat/spec/itemindex.py`, `<state>/items/<key>.db`) already is that database. **Do not add a second store, a JSON cache or files of projections.**

Change: add what the status snapshot now reads with `p.events.query` as indexed tables or columns of the item index: the inbox entries and their stats, interventions, stored actions, requests, proposals, lease attention, crossings, and unrouted messages and drafted reports. They are followed by the index's existing fold under its existing write lock, rebuilt with it, and covered by its fresh-fold check. Fields that requests filter on (an action's state and class, an intervention's state) are real indexed columns, not decoded from `body`.

This gap builds and proves the tables. It does not yet move the status answer onto them (`status-reads-the-projections`).

Definition of done:
1. For randomized event sequences, on both event stores, each table's answer equals a fresh fold from the record (a property test).
2. An existing index upgrades by rebuilding; a crash part way leaves a state that resumes or rebuilds correctly; several processes may read while one follows.
3. A roll-up, a prune or a fresh record leaves the tables correct.
4. SPEC §4b says what the index holds and that the record stays the truth.

## Where it stopped

Built, round 1. `ergostat/spec/projections.py` (new) and `ergostat/spec/itemindex.py` (VERSION 6): four tables in the
item index file, created with its schema, emptied by its `_reset`, folded in `_step` inside the same `begin immediate`
transaction as the chunk of items, and read through `Index.records`, `Index.marked`, `Index.asked` (each under the
index's lock and healing, like its other reads). Net code outside tests/docs/dev: 276 lines of the 600.

- `records`: ergostat's own items, one row each: gated actions, messages, reports, model changes (proposals), modelling
  requests (requests) and model requests (interventions' classes). `state` and `cls` (an action's class or action, a
  change's kind, a request's code, a model request's class) are real indexed columns; an intervention's state is its
  model request's `state`. The answer is keyed and shaped as each module's `stored()` (or `changes()`,
  `requests_now()`) gives it, including their quirks (an action or report whose first event is not its start is left
  out; a message wholly rolled up is not read; one whose first message event is not its receipt is read whole, from
  its snapshot), so the next gap can swap reads without changing answers.
- `marks` and `voids`: every event of the types the status reads by type and time (loop crossings, breakers, step
  tests offered and approved, daemons given up and revived, leases expired, the events of model changes and modelling
  requests, `ergostat.forgotten`), whole; `marked()` answers as `events.query` does, `unvoided` included.
- `asks`: the person and advised blocks' asks and how each was answered (`inbox.entries.asks`), per block and chain.

Decisions taken alone (the reversible option each time):
- The inbox entries, a class's weekly record (stats), the interventions list and lease attention are not stored as
  finished answers: they also depend on the model's blocks, goals, `messages: {done:}`, the step-test decisions file
  and alarm readings, while one index file is shared by every model with the same item kinds (`kinds_key`). Every
  event-log read they make is a table here; assembling them stays a read-time step for `status-reads-the-projections`.
- The tables hold the fold as of what the index has folded: `records` has no `until` (the status asks about now when
  live). An `until` earlier than the index's last seq is still a read of the record.
- `asks` answers equal the record's windowed read when event times follow the record's order (each event stamped as
  added); an answer stamped earlier than its ask's window start is counted by the table and not by the windowed read.
- After a roll-up or prune (the record's generation changed), `records`, `marks` and `voids` are folded again from what
  the record holds up to the index's seq (one read of those types and of the families' items, as often as roll-ups
  run); an ask whose event is gone is dropped (an answer is never older than its ask, so none is left behind).
- `agent.ran` is read beside the items' events (it answers a person's ask), so each catch-up makes one more query.

Tests (all pass): `tests/test_index_projections.py` (11: the property test on both stores, 3 seeds, followed a chunk
at a time, read cold and reindexed; roll-up, prune and fresh record on both stores; older layout rebuilt; crash part
way resumes from the last commit; another process reads what was committed while one follows, not blocked), and
`tests/test_item_index.py`'s example test now also runs the tables' check. Seen to fail: with `projections.again`
removed the roll-up/prune test fails on both stores; with the chunk cut on the loose events removed 7 of 11 fail.
Also run, passing: test_item_index, test_rollup, test_item_about, test_lease_refused_cost, test_repair_verify,
test_run_budget, test_counts (226.8 s with the change, 230.2 s with the loose read turned off: no slowdown),
test_finished_states, test_index_files, test_item_search, test_relations_asof, test_relations, test_reload_safety,
test_resilience, test_upkeep_template. Not run here: the whole unit suite and the four browser files (no page changed);
the factory runs them.
