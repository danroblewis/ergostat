# status-is-a-maintained-projection-join-1: confirm the status is read from maintained projections, and record that the gap is done

depends-on: [status-reads-the-projections, status-projections-in-the-index]

## Definition of done
- Nothing new is built in `ergostat/`. Every point of the gap's entry is already on main:
  - The status snapshot (`state.snapshot`, `actions/record.py`, `inbox/`, `numbers/requests.py`,
    `numbers/proposals.py`, `leases/measures.py`) reads the item index's tables through `ergostat/spec/projections.py`.
  - The old folds are deleted and survive only as the test oracle in `tests/status_before.py`.
  - The status answer carries `as_of` (seq, made) and `age`.
- `dev/records/status-is-a-maintained-projection-join-1.md` is written with these parts:
  - An `## Entry`, restated from main's real names. The entry's `ix.records`, `ix.marked` and `ix.asked` are named as
    the tables main actually has (records, marks, asks, latest, ticks) and the projections functions that read them.
  - Each point of the entry, matched to the commit and the test on main that meets it.
  - The results of running, on current main, `tests/test_status_reads_projections.py` (4 tests, none xfailed) and
    `tests/test_index_projections.py`, each with its pass count.
- If any of those tests fails on main, the failure is reported in "Where it stopped" with its output, not fixed here
  (lesson-13). The gap is then not called done.

## Relation to other work
- status-reads-the-projections: merged; it built everything this join checks.
- status-projections-in-the-index: merged; it built the tables.
- perf-answers-carry-only-what-is-drawn (building): it touches the status poll's payload. This join does not edit
  those files.

## Files to touch
- `dev/records/status-is-a-maintained-projection-join-1.md` (new)

## Risks
- lesson-8: the record states more than main holds, such as the entry's table names or "never replayed" for as-of
  reads, which still fold one item from the record when its matched fields may have changed. The record must name
  that case and the test that guards it.
- lesson-10: the 100 ms test is a wall-clock bound, marked `serial`. A failure under load is reported with a rerun,
  not called a regression or a pass without one.

## Acceptance tests
- `tests/test_status_reads_projections.py::test_a_status_request_makes_no_segment_query_and_answers_in_100_ms`: no
  segment query once the index is current, and an answer in under 100 ms.
- `tests/test_status_reads_projections.py::test_once_the_index_is_current_the_status_reads_none_of_the_tables_from_the_log`:
  no log read, while the old code reads every tabled type.
- `tests/test_status_reads_projections.py::test_the_answer_equals_the_old_codes_field_by_field`: equality with the
  old code.
- `tests/test_status_reads_projections.py::test_the_answer_says_how_old_it_is`: the answer gives its `as_of` and age.
- `tests/test_index_projections.py::test_as_of_a_moment_only_an_item_whose_matched_fields_may_have_changed_is_folded_again`:
  the as-of case named in the record.

## Size budget
0 net lines
size: S (confidence: high)

## Entry

Page status is read from projections the item index keeps current, not replayed from the event log per request.

- The item index (`ergostat/spec/itemindex.py`, one SQLite file per item-kinds key) holds, beside its item tables,
  the tables of `ergostat/spec/projections.py` (`TABLES`): `records` (ergostat's own items: actions, messages,
  reports, model changes, modelling requests, model requests; `state` and `cls` indexed columns), `marks` and `voids`
  (every event of the `MARKS` types, whole, and the ids an `ergostat.forgotten` set aside), `asks` (each person or
  advised block's asks and how each was answered), `latest` (each item's newest event of the `LATEST` types) and
  `ticks` (what each run and opening adds to the window's tallies). They are folded by `projections.follow` in the
  index's own `_step` transaction, emptied and rebuilt with it, and folded again by `projections.again` after a
  roll-up or prune. What the gap's first sketch called `ix.records`, `ix.marked` and `ix.asked` are the index's
  methods `Index.records`, `Index.marked`, `Index.asked` (with `Index.latest_of`, `ticks_of`, `ticked`, `amounts`,
  `newer`), each `projections.<same name>` wrapped in the index's healing guard (`itemindex.py:975-982`).
- The status snapshot (`state.snapshot`, `actions/record.py`, `messages/record.py`, `reports/record.py`, `inbox/`
  entries, stats and interventions, `numbers/requests.py`, `numbers/proposals.py`, `leases/measures.py`) reads them
  through `projections.stored`, `query`, `asks`, `latest`, `runs`, `opened`, `openings` and `opened_amounts`. One
  status answer catches the index up once.
- The old folds are deleted from `ergostat/`; they survive only as the tests' oracle, `tests/status_before.py`
  (`old(monkeypatch)` puts them back).
- The snapshot carries `as_of: {seq, made}` (`state.py:437`); the status API answer gives it with `age` in seconds
  (`state.age`, `web/server.py:848`).
- Where it still reads the record (what "never replayed" does not cover):
  - a read as of an earlier moment (`until`). `projections.stored` answers from `records` unless one of the family's
    items has an event after `until` (`Index.newer`); then it folds that family's events up to `until` in memory.
    `projections.latest` reads the record for an item whose newest event is after `until`. The item index's as-of
    fold (`items._late`) folds again from the record only an item changed since the moment whose matched fields an
    event since may have changed, or whose events came out of time order around it (`Index.still`). Guarded by
    `tests/test_index_projections.py::test_as_of_a_moment_only_an_item_whose_matched_fields_may_have_changed_is_folded_again`
    (and the as-of checks in `test_each_table_is_a_fresh_read_of_the_record`).
  - a record with no index file made yet, or one that cannot be read and cannot be rebuilt (`projections.index_of`
    gives None): every read takes the record path, folded the same way. Guarded by
    `tests/test_index_projections.py::test_with_no_index_made_or_one_unreadable_the_reads_make_no_file_and_read_the_record`.

## Where it stopped

Done: nothing was built in `ergostat/` (0 net lines); every point of the entry was found on main as of 500c6e75 (the
branch's base, main's 666d65d6 plus this record), and the tests below pass there.

Decision taken alone (the reversible option): the definition says the file changes only by a "Where it stopped"
section, and also asks for an `## Entry`. Both are appended after the definition's text, which is left as it was.

Each point, its commit and test on main:
- The tables (`records`, `marks`, `voids`, `asks`): 3a3ad97d (status-projections-in-the-index); `latest`, `ticks`,
  `records.last` and `Index.still`: 2bf5fa38. Test: `tests/test_index_projections.py::test_each_table_is_a_fresh_read_of_the_record`
  (both stores, 3 seeds), `test_a_rollup_a_prune_and_a_fresh_record_leave_the_tables_right`,
  `test_an_index_of_an_older_layout_is_rebuilt`, `test_a_crash_part_way_resumes_from_what_was_committed`,
  `test_another_process_reads_what_was_committed_while_one_follows`.
- The status snapshot reads the tables through `projections.py`: 074b9d34 (records, marks, asks) and 2bf5fa38
  (latest, ticks, the as-of fold, one catch-up per answer); 98bacccd (no index file made by a read; an unreadable
  index reads the record). Tests:
  `tests/test_status_reads_projections.py::test_once_the_index_is_current_the_status_reads_none_of_the_tables_from_the_log`
  and `::test_a_status_request_makes_no_segment_query_and_answers_in_100_ms`.
- The old folds deleted, kept only in `tests/status_before.py`: 074b9d34 and 2bf5fa38. Test:
  `tests/test_status_reads_projections.py::test_the_answer_equals_the_old_codes_field_by_field` (and the first test
  above, which shows the oracle reads every tabled type from the log).
- `as_of` (seq, made) and `age`: 074b9d34. Test: `tests/test_status_reads_projections.py::test_the_answer_says_how_old_it_is`.
- The as-of case (an item whose matched fields may have changed is folded again): 2bf5fa38. Test:
  `tests/test_index_projections.py::test_as_of_a_moment_only_an_item_whose_matched_fields_may_have_changed_is_folded_again`.

Results on current main (this branch, which changes only this file), each file run alone through
`scripts/named_tests.py`:
- `tests/test_status_reads_projections.py`: 4 passed, none xfailed (31.81 s). The 100 ms test passed on its one run;
  it is a wall-clock bound marked `serial`, and was not rerun here, so this is one passing run, not a measure of its
  margin under load.
- `tests/test_index_projections.py`: 14 passed (25.10 s).

Not run here: the whole unit suite and the four browser files (no code or page changed); the factory runs them.
`uv run ruff check ergostat tests scripts`: all checks passed.
