# cx-backfill-replace: a changed definition can reach the record

depends-on: [cx-sensor-backfill]

Branch `cx-backfill-replace`, from main. Core.

## The problem

`--backfill` skips a reading whose time is already recorded, which is right for sending a file twice and wrong when the measure's definition changed: the new values have the same times as the old, all are skipped, and the record keeps the old definition. Old and new readings left side by side would also be read by `changes` flows as rises and falls that never happened. `forget` sets readings aside by value only, not by time.

## The change

`ergostat sensor PART.SENSOR --backfill FILE --replace`.

## Definition of done

1. With `--replace`, every reading of the series whose time is within the file's first and last `at` (inclusive) is set aside first, as `forget` sets readings aside (kept in the forgotten table with when and why: the `--from` text), live and backfilled alike; then the file is written. One transaction where the backend has them; otherwise under the compaction lock.
2. Buckets of every tier that overlap the span are made again from what is left and the new readings (or dropped and refilled at the next roll, where the raw readings are gone); readings waiting as late in the span are dropped.
3. On a backend that cannot delete a span, the series is rewritten whole under the lock (read out, the span removed, the file added, written back); the result is the same and the conformance test is the same.
4. The ledger's entries for the span are replaced by this call's; `--backfilled` shows the earlier backfill as replaced, with when.
5. Readings outside the span are untouched. The event `sensor.backfilled` says `replaced: N`.
6. Refused without `--from`.
7. `docs/SPEC.md` describes it beside `--backfill`.

## Files to touch

`ergostat/store.py`, the server measurements backend's module, `ergostat/cli/spec_cmds.py`, `ergostat/cli/__init__.py`, `docs/SPEC.md`, `tests/test_sensor_backfill_replace.py` (new), `tests/test_store_conformance.py`.

## Acceptance tests

- `test_replace_swaps_the_values_in_the_span`: ten readings, then the same times with other values and `--replace`: the range holds the new ones, each once.
- `test_replace_removes_live_readings_in_the_span`.
- `test_replace_leaves_readings_outside_the_span`.
- `test_replace_after_the_roll`: the span is ten days old and rolled into buckets; after the replace and a roll, the buckets hold the new values only.
- `test_changes_flow_sees_no_false_step`: a `changes: rises` flow over the span reads the new history's rises only.
- `test_replaced_readings_are_kept_aside`.
`tests/test_store_conformance.py::test_backfill_replace` on every backend. Unit suite rc 0, ruff clean.

## Size budget

130 net lines outside `tests/` and `docs/`.

From the owner's request of 2026-11-22: measure ergostat's code complexity in many forms and slices, as stocks on main, backfilled from git history.
