# status-reads-the-projections: the status answer reads the indexed tables and never scans the event log

Depends on `status-projections-in-the-index`. Move every event-log read of the status snapshot (`state.snapshot`, `inbox/`, `actions/record.py`, `numbers/requests.py`, `numbers/proposals.py`, `leases/measures.py`) onto those tables, and delete the old folding code it replaces.

Definition of done:
1. On a generated record of the factory's size, a status request makes no event-log scan once the index is current (a test counts segment queries) and answers in under 100 ms.
2. The status answer is equal, field by field, to the answer from the old code on that record, apart from fields that were capped before.
3. The answer says how old it is.

## Where it stopped

Not started: this gap waits for `status-projections-in-the-index`, which is not on main as of the clone (63439d64).
The item index (`ergostat/spec/itemindex.py`, layout VERSION 5) holds only `items`, `moves`, `left`, `reached` and
`links`. No tables project the inbox, actions, requests, proposals or leases for the status snapshot to read, and no
record of that gap exists in `dev/records/`. Building those tables here would mean building the dependency inside
this gap, so nothing in `ergostat/` was changed (the most reversible option). The whole definition of done above is
left: once that gap is on main, move the status snapshot's event-log reads (`state.snapshot`, `inbox/`,
`actions/record.py`, `numbers/requests.py`, `numbers/proposals.py`, `leases/measures.py`) onto its tables, delete
the folding code they replace, and write the three acceptance tests: no segment query once the index is current, and
an answer in under 100 ms, on a record of the factory's size; field-by-field equality with the old answer; the
answer's age.

## Where it stopped

Parked by the factory (review/status-reads-the-projections-1, 2026-11-23 01:18).

Nothing is done beyond the definition of done and a 'Where it stopped' note. The branch was cut from ead497d1, before status-projections-in-the-index landed, so the tables it depends on did not exist in its clone. Still to do, all of it: merge origin/main (which now holds 38d367b4); move the status snapshot's event-log reads onto the tables in ergostat/spec/projections.py; delete the folding code those reads replace; write the three acceptance tests (no segment query once the index is current plus under 100 ms on a factory-sized record; field-by-field equality with the old answer; the answer says its age). It stops because the dependency was missing when the work ran. That dependency is now on main, so the gap can resume immediately.

## Where it stopped

Round 1 resumed on main as of 22f1d7bb (status-projections-in-the-index is on it). Done items 2 and 3 are built and
pass. Done item 1 is met only for the reads the dependency's tables hold. The rest of the snapshot's reads have no
table, and the 100 ms bound is not met (measured below). Net code outside tests, docs and dev: +14 lines (141 added,
127 deleted) of the 600.

What is built:
- Every read the status makes of what `spec/projections.py` tables hold now reads the tables. `projections.stored`
  (records), `query` (marks) and `asks` are used by `actions.record.stored`, `messages.record.stored`,
  `reports.record.stored`, `numbers.proposals.changes`, `numbers.requests.stored`, `inbox.interventions.requests_now`,
  `inbox.entries.asks`, the inbox's breakers and step tests, `inbox.stats.asked` (step tests approved, model changes,
  modelling requests), `interventions.read` (daemons given up and revived) and `_ran`, `leases.measures` (expired
  leases), and `state.snapshot`'s loop crossings (`_crossings`, `crossings_of`, each loop's last crossing).
- The folding code they replace is deleted: each module's own fold of the record in those functions, proposals'
  `_FOLDED` cache and requests' `_moved_at` (the table keeps `moved`). The old code survives only as the tests'
  oracle, `tests/status_before.py`.
- An as-of read (`until`) is answered from the table unless one of the family's items has an event after `until`. A
  new `records.last` column (index layout VERSION 8, so an existing index is rebuilt once) tells which. Otherwise, and
  for a record kept nowhere on disk, the same `follow` runs over the family's events up to `until`, in an in-memory
  table. The check and the read are made under the index's lock.
- The snapshot carries `as_of: {seq, made}` (the record's last seq as it was read, and when the answer was made).
  The status API answer carries `as_of` with `age`, in seconds (`state.age`).
- SPEC §4b says what the status reads from the tables, how `until` is answered, the age, and what still reads the
  log.

Done item 1, measured on a copy of the factory-size fixture with ergostat's own items seeded (400 gated actions, 80
messages, 15 reports, 60 model changes, 50 modelling requests, 12 model requests, 12 person blocks' asks). The index
was current and one new event had arrived. One status snapshot: old code 2,624 segment queries and 599 ms; this branch
594 and 500 to 530 ms (one machine, not under load; the factory's container numbers will differ). None of the 594 is
of a type the tables hold. They are:
- 87 each of `agent.ran`, `agent.failed` and `agent.started`: each agent's latest.
- 60 `controller.decided` and 41 `valve.opened`: each loop's latest decision and opening.
- 1 read of the claims contradicted in the window.
- 231 reads of a single item's events: the item index's own as-of fold (`its.moved` → `_late`) of items changed after
  a reading's time.
- Beside these, `events.runs`/`opened` tallies, which read the segments' columns.

None of these is in the dependency's tables. Moving them needs new tables in the item index (each (type, item)'s
latest event; the window's run tallies and openings per agent and valve; an as-of answer for items changed since),
which is a dependency of this gap, not part of it. It is not built here. Suggested gap:
`status-latest-and-tallies-in-the-index`. With it, the strict xfail
`test_a_status_request_makes_no_segment_query_and_answers_in_100_ms` should pass; remove its mark then.

Decisions taken alone (the reversible option each time):
- `messages.record.stored(n=)` keeps its parameter but caps nothing now. The status's unrouted messages read the
  newest 2,000 message events before; this is the "capped before" field the definition allows. The oracle keeps the
  cap, and the seeded record stays under it.
- `inbox.entries.asks` reads the `asks` table for any `until`. Its one known difference from the windowed read is
  the dependency's: an answer stamped before its ask's window start.
- The acceptance test counts `Segments._scan` calls outside the index's own catch-up. A read of a single item's events
  is attributed to the item index's as-of fold, not to these tables. `agent.ran` counts as a table read only beside a
  person's ask.
- The dependency's property test (`tests/test_index_projections.py`) compared the tables with the modules' `stored()`.
  Those now read the tables, so it compares them with the old code in `tests/status_before.py` instead. It also
  covers the modules, the in-memory path and the as-of path.

Tests:
- `tests/test_status_reads_projections.py`: 3 pass and 1 strict xfail.
  - `test_once_the_index_is_current_the_status_reads_none_of_the_tables_from_the_log` also checks that the old code,
    counted the same way, does read those types.
  - `test_the_answer_equals_the_old_codes_field_by_field`.
  - `test_the_answer_says_how_old_it_is`.
  - the xfail above.
- `tests/test_index_projections.py`: 11 pass.
- Seen to fail, each with its break in place:
  - with `projections.query` reading the log, the first test fails;
  - with the `command` field dropped from an action's table view, the equality test fails at `inbox`;
  - with `as_of` renamed in the status answer, the age test fails;
  - with the `newer` check removed, the as-of check in test_index_projections fails.
- Also run, passing: test_inbox, test_interventions, test_leases, test_messages, test_gated_actions, test_reports,
  test_modelling_core, test_modelling_core2, test_modelreview, test_improve, test_changesets, test_churn, test_modeller,
  test_modeller_budget, test_modelling_ai_cap, and test_churn_carry, test_factory and test_intent together (251
  passed, 2 skipped; the skip reasons were not looked at).
- Not run here: the whole unit suite and the four browser files (no page changed; the status answer gained a field).
  The factory runs them.

## Where it stopped

Parked by the factory (review/status-reads-the-projections-2, 2026-11-23 11:21).

Done: items 2 and 3. The inbox, its stats, interventions, gated actions, messages, reports, model changes, modelling requests, leases' attention and loop crossings read projections.stored, query and asks. The old folds are deleted (kept only as the test reference in tests/status_before.py). As-of reads are answered from the table when no item of the family has a newer event (records.last, index VERSION 8), else by an in-memory fold. as_of and age are in the snapshot and the status API, and the field-by-field equality test is in place. Left: done item 1, the whole of it. Every remaining event-log read of state.snapshot (each agent's latest run, failure and start, each loop's latest decision and opening, the window's run tallies and openings, the item index's as-of fold of items changed since, refused_expiries) must move onto index tables, and the status must answer in under 100 ms on the factory-size fixture, so that the strict xfail passes. It stops because this is the second failed review. The gap's own work is incomplete, and the reason given (it needs another gap) is not one the definition allows, since those reads are named in it. Whoever resumes should either build those tables here within the budget, or have the owner split the definition so that item 1 waits for a real, named gap.

## Where it stopped

Round 1 of the continued gap (gap/status-is-a-maintained-projection-2-continued-2), on main as of 278f54a4 (merged).
All three done items are built and their tests pass, with the strict xfail removed. Net code outside tests, docs and
dev: +325 lines (522 added, 197 deleted) of the 600, for the whole branch.

The review's finding: done item 1 was not met (the snapshot's remaining event-log reads, and 100 ms). What changed:
- Each agent's latest run, failure and start, and each loop's latest decision, opening and auxiliary set: a new
  `latest` table in the item index (each item's newest event of the `LATEST` types, by seq). A read as of a moment
  before that newest event reads the record for that item (exact). `projections.latest`.
- The window's run tallies and openings (`events.runs`, `opened`, `times`, and the ladder hint's amounts): a new
  `ticks` table (what each run and opening adds to `segments.TALLIES`, with its time and its amount as written).
  One query per tally for all agents or valves. `projections.runs`, `opened`, `openings`, `opened_amounts`.
- Claims contradicted: now one of `MARKS`.
- The item index's as-of fold of items changed since a reading (`items._late`, from `state.counted`): the index now
  keeps, per item, when each top-level field was last touched by an event (a snapshot or a `set` touches all of them;
  more is safe), and the span where its events came out of time order. An item changed since the moment is folded
  from the record only when an event since may have changed a field it is matched on, or the moment falls in that
  span (`Index.still`). Otherwise its fields now and its moves up to then are its fields and moves as of then.
- An action's why (its work item's impact and tests, `inbox.entries._why`) was a fold of the item from the record. It
  is now read from the item index, batched (`items.current`).
- `refused_expiries` already read the item index. It folds from the record only an item the index does not hold, and
  on the fixture it reads no segment.
- The old reads are deleted where they were replaced, and kept only as the tests' oracle (`tests/status_before.py`,
  which now also puts back the old latest, tally, opening, work-item and as-of reads).

For the 100 ms, beyond the event log:
- One status answer catches the index up once (`itemindex.pinned`). Before, each of about 260 reads looked for what
  was new.
- The measurements store's `first_time` was one `min(time)` over every reading (34 ms). It now reads each series'
  first reading by the `samples_series` index (a recursive skip-scan, the same minimum).
- The window's readings of every sensor are read in one connection (`Measurements.ranges`). They are used only where
  the raw readings answer alone (raw held from the span's start, as `_sources` decides), else the store's own read.
  `sampled` works out its sources once for its count and its read.
- The newest reading of each sensor comes from the store's `newest()` when it is at or before the moment asked about.
- The sensors are indexed by what they measure; `lease_attention` reads only each kind's dead items; the inbox's
  stats read only the waiting changes (`_changes`), not the whole inbox again; actions are filtered by state in SQL;
  `Index.name(None)` no longer reloads every name; the log's head keeps its earliest time.

Measured on the factory-size fixture with the seed (this container, load average about 9 on 24 cores): 62 to 95 ms
over five status answers (median 67). It was 455 ms with 1,188 log reads at the start of this round. Once the index is
current, the answer makes no segment query: the only ones left are the index's own catch-up of the new event, which
the test leaves out.

Decisions taken alone (the reversible option each time):
- A run or opening whose number field is not a number counts as one, adding nothing. Before, the segments' tally
  raised.
- The ladder hint reads an opening's amount as written when it is a number, else None. Before, a string or a boolean
  was kept as it was.
- Amounts are summed by SQLite's `total()`, not in Python segment by segment. Amounts that are not exact in binary
  may differ in their last bits.
- The why reads the transcript-less index. A transcript's events fold only into `transcripts.FIELDS`, never `impact`
  or `tests`. One case is not covered, a kind with `if-unchanged` rules: there a transcript's lines would change the
  event count those rules compare.
- The index layout stays VERSION 8. Main is at 7, and this branch's 8 never landed.
- After a roll-up or prune, `latest` and `ticks` are folded again from what the record holds. That reads every run
  and opening once per change of the record's generation.
- The 100 ms test is marked `serial` (a wall-clock bound, per the house rule). It is a single answer's time, not the
  best of several.

Tests:
- `tests/test_status_reads_projections.py`: 4 pass, none xfailed.
  - `test_a_status_request_makes_no_segment_query_and_answers_in_100_ms` (was the strict xfail).
  - `test_once_the_index_is_current_the_status_reads_none_of_the_tables_from_the_log` (now no read at all; the old
    code reads every one of the types and over 20 single items).
  - `test_the_answer_equals_the_old_codes_field_by_field` (the seed now gives work items an impact, so the why is
    compared).
  - `test_the_answer_says_how_old_it_is`.
- `tests/test_index_projections.py`: 13 pass. The randomized record now holds runs, failures, starts, openings
  (amounts of every kind and none), decisions and claims. `latest`, `runs`, `opened`, `openings` and the amounts are
  compared with the record's reads through catch-up, rebuild, roll-up and prune, with and without an index. New:
  `test_as_of_a_moment_only_an_item_whose_matched_fields_may_have_changed_is_folded_again`, on both stores.
- `tests/test_measurements_read_together.py` (new): 2 pass, `ranges` and `first_time` against the store's own reads.
- Seen to fail, each with its break in place:
  - `touches` ignoring data keys: the as-of test fails.
  - the out-of-order check removed: the as-of test fails (on its written-late case; the random draws alone did not).
  - `ranges` without its raw-held condition: the measurements test fails.
  - `latest` without its as-of fallback: test_index_projections fails (10 of 13).
- Also run, passing: test_item_index, test_store_conformance, test_leases (142 passed; the 12 skips are the
  VictoriaMetrics store with no server and stores with no tiers), test_inbox, test_interventions, test_gated_actions,
  test_runner_and_state, test_observer, test_graph_cli_web, test_quiet_system, test_off_by_words, test_model,
  test_claims, test_dynamics_view, test_scale_caches, test_goal_per, test_numbers, test_daemons, test_messages,
  test_reports, test_upkeep_record.
- One failure seen, not reproduced: `test_upkeep_record.py::test_a_killed_compactor_releases_the_lock` failed once
  (`timed == [5.0]`) when run beside test_messages and test_reports on the loaded machine. It passed alone and when
  the same three files were run again. It covers `Engine.run_block` and `stream.follow`, which this branch does not
  touch.
- Not run here: the whole unit suite and the four browser files (no page changed). The factory runs them.

## Where it stopped

Round 2 of the continued gap (gap/status-is-a-maintained-projection-2-continued-2), on main as of 59600738 (merged;
its one conflict, `_Head.__init__` in `ergostat/segments.py`, keeps both main's `by_key` and the branch's `t_min`).
All three done items stay built and their tests pass. Net code outside tests, docs and dev: +330 lines (527 added, 197
deleted) of the 600, for the whole branch.

The review's one finding, and what changed:
- `state._sensor_for`'s module-level `_BY` cache was checked and then read again with nothing held between, so another
  thread or model replacing it in that gap could hand a call another model's sensors (lesson-1). The cache is now a
  tuple read once into a local and replaced whole by assignment; the check and the read use that one tuple, so a
  swap by another caller changes only what later calls see. Keying it per model (a WeakKeyDictionary) was the other
  option; the tuple keeps one model's cache as before and needs no hashable or weak-referenceable model.
- No other module-level mutable state was added by the branch (`_PIN` and `_NEWEST` are thread-local, `TICKS` is a
  constant).

Tests:
- `tests/test_state_sensor_cache.py` (new): 2 pass. The first puts the competing write in the gap: a sensors dict
  whose `len()` makes another model take the cache between the check and the read. Seen to fail with the old read of
  the shared cache put back (`['theirs'] == ['ours']`).
- Run again after the merge, passing: test_status_reads_projections (4), test_index_projections (13),
  test_segments_keyed (7), test_lease_watch_slices (2), test_measurements_read_together (2), test_runner_and_state
  (47), test_item_index (59), test_store_conformance (46 passed, 12 skipped: VictoriaMetrics with no server, stores
  with no tiers). Ruff clean.
- Not run here: the whole unit suite and the four browser files (no page changed). The factory runs them.

## Where it stopped

Round 3 of the continued gap (gap/status-is-a-maintained-projection-2-continued-2), on main as of b9341591 (already
merged, nothing new). All three done items stay built and their tests pass. Net code outside tests, docs and dev:
+340 lines (538 added, 198 deleted) of the 600, for the whole branch.

The queue's findings (a batch of 9 failed to merge; two tests then failed on this branch alone), and what changed:
- `tests/test_item_about.py::test_status_with_an_unreadable_index_says_unknown`: once the index could not be read and
  could not be built again, the status raised `DatabaseError` from the new table reads (`projections.opened` →
  `ticks_of`). The old code read those from the log. Now `projections.index_of` probes the index under its healing
  guard. When it cannot be read (`sqlite3.DatabaseError`, `OSError`), it returns None, and every table read takes its
  existing no-index path: the record's own events, folded the same way. This is not a fail-open: the record is the
  truth, so the answer is the same, only slower. The about line still says "unknown", as before.
- `tests/test_upkeep_template.py::test_the_tidier_block_moves_its_two_flows_through_the_engine`: a block run delivers
  messages (`deliver.for_context` → `messages.record.stored` → `projections.stored`), and that now opened the item
  index. Opening it made a new index file, so the tidier counted one more file and tidied 3, not 2. Now the status's
  table reads never make an index file: `itemindex.index_for(..., made=True)` gives None when no index file exists and
  none is open, and the read takes the record path, as before this branch. Whatever made the index before (the item
  folds, sensors, the page) still makes it. Decision taken alone, the reversible option: keep the other gap's test as
  it is and change this branch. The other option was to accept the new file and change that test's expected count.
  Cost: until something else makes the index, a status answer reads the log at the old speed.
- SPEC §4b says both.

Tests:
- `tests/test_index_projections.py`: 14 pass. New:
  `test_with_no_index_made_or_one_unreadable_the_reads_make_no_file_and_read_the_record` (no file made by the reads;
  the answers equal the old code's with no index, and again with an unreadable one that cannot be healed). It was seen
  to fail with `made=False` put back (a file made) and with the probe and its catch removed (`index_of` gives the
  broken index). Its seed also showed a bug in this branch's own `_check`: an action with neither `class` nor `action`
  made it ask `records(cls=None)`, which means no filter. That one test line now skips None.
- The two queue failures pass, and both failed before the change (seen above).
- Also run, passing: test_item_about and test_upkeep_template whole, test_status_reads_projections (4),
  test_item_index, test_inbox, test_messages (116), test_runner_and_state, test_gated_actions, test_reports (70).
  Ruff clean.
- Not run here: the whole unit suite and the four browser files (no page changed). The factory runs them.
