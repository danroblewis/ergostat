# cx-sensor-backfill: record a sensor's readings at past times

depends-on: []

Branch `cx-sensor-backfill`, from main. Core. From the owner's request to backfill the complexity stocks from git history; it serves any measure with a history outside ergostat.

## The problem

The measurements store takes a time (`Measurements.add(at=)`, `add_many`; late readings are merged into their buckets at the next roll), but no command passes one through. A history computed from git can only sit in a side file, where the charts, the fit and `changes` flows never see it. Raw readings are kept two days and events without an item thirty, so neither can say later which readings were backfilled or whether a file was already sent.

## The change

`ergostat sensor PART.SENSOR --backfill FILE` (`-` for stdin): JSON lines `{"at": <epoch seconds>, "value": <number>}` written to that sensor's series in one `add_many`, and a ledger in the measurements store that is never rolled up or pruned.

## Definition of done

1. Accepted for a sensor that records a value (`run`, `query`, `manual`, `daemon`); refused with a clear message for `items`, `changes` and `builtin`, which ergostat derives.
2. Refused as a whole, nothing written: a line that is not JSON, an `at` or `value` that is not a finite number, an `at` in the future. Two lines with one `at` in a file: the last is kept, and the count says so.
3. **The ledger.** The store keeps, per backfill call, `(id, series, from, written_at, first, last, count)` and, per reading, `(series, at, id)`. It lives with the measurements on every backend (beside `measurements.forgotten.json` where the readings are in a server) and is outside every tier's roll and every `keep`.
4. A reading whose `(series, at)` is in the ledger is skipped, whatever has rolled since: the same file sent twice writes nothing the second time, two days later or two months later. The printed and `--json` counts (written, skipped) come from the ledger, never from comparing against buckets.
5. `ergostat sensor PART.SENSOR --backfilled [--json]` lists that series' backfills (when, from, first, last, count), so a backfilled span stays distinguishable from live readings for as long as the series exists.
6. One event `sensor.backfilled` (count written, count skipped, first and last `at`, the free `--from TEXT`); it may be pruned like any event, the ledger is what lasts.
7. Works on both measurement backends; readings older than the raw tier land in their buckets after the next roll.
8. `docs/SPEC.md` (the sensor section and the CLI table) describes it, including that a bucket keeps the last of two readings in it, so two readings closer together than an old tier's bucket are one point there.

## Files to touch

`ergostat/store.py` (the ledger), `ergostat/cli/__init__.py`, `ergostat/cli/spec_cmds.py`, the server measurements backend's module, `docs/SPEC.md`, `tests/test_sensor_backfill.py` (new), `tests/test_store_conformance.py`.

## Acceptance tests

`tests/test_sensor_backfill.py`:
- `test_past_readings_are_in_range`: three readings a day apart are returned by the series' range at their times.
- `test_twice_writes_nothing_new`.
- `test_twice_after_the_roll_writes_nothing_new`: readings ten days old, a roll, then the same file: 0 written, and the range holds each once.
- `test_future_or_malformed_refuses_all`.
- `test_same_at_in_one_file_keeps_the_last`.
- `test_derived_sensors_refused`: an `items` and a `changes` sensor.
- `test_backfilled_lists_the_span_after_events_are_pruned`.
- `test_changes_flow_reads_backfilled_history`: a `changes: rises` flow on a manual-sensor stock reads a rate from backfilled readings.
`tests/test_store_conformance.py::test_backfill_ledger_and_late_merge` on every backend. Unit suite rc 0, ruff clean.

## Size budget

150 net lines outside `tests/` and `docs/`.

From the owner's request of 2026-11-22: measure ergostat's code complexity in many forms and slices, as stocks on main, backfilled from git history.
