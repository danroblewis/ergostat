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
