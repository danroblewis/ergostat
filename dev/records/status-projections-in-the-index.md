# status-projections-in-the-index: the status answer's event-log reads become indexed tables in the item index

The owner, 2026-11-22: queries should come from a standard, indexed database; the event log is kept as the record. The SQLite item index (`ergostat/spec/itemindex.py`, `<state>/items/<key>.db`) already is that database. **Do not add a second store, a JSON cache or files of projections.**

Change: add what the status snapshot now reads with `p.events.query` as indexed tables or columns of the item index: the inbox entries and their stats, interventions, stored actions, requests, proposals, lease attention, crossings, and unrouted messages and drafted reports. They are followed by the index's existing fold under its existing write lock, rebuilt with it, and covered by its fresh-fold check. Fields that requests filter on (an action's state and class, an intervention's state) are real indexed columns, not decoded from `body`.

This gap builds and proves the tables. It does not yet move the status answer onto them (`status-reads-the-projections`).

Definition of done:
1. For randomized event sequences, on both event stores, each table's answer equals a fresh fold from the record (a property test).
2. An existing index upgrades by rebuilding; a crash part way leaves a state that resumes or rebuilds correctly; several processes may read while one follows.
3. A roll-up, a prune or a fresh record leaves the tables correct.
4. SPEC §4b says what the index holds and that the record stays the truth.
