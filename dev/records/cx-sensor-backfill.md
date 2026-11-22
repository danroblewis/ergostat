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

## Where it stopped

Built, round 1: every item of the definition and every named acceptance test; 150 net lines outside tests, docs and dev.
Choices taken without asking (each the more reversible one):
- The ledger's tables (`backfills`, `backfilled`) are in `measurements.db` for `sqlite`; for `victoriametrics` they are in a SQLite file, `measurements.backfilled.db`, beside `measurements.forgotten.json` (a JSON file would have to be rewritten whole, with no lock held between its read and its write). The ledger is read and written in one `begin immediate` transaction that also writes the readings (lesson 1).
- Every backfill call is a row in the ledger, one that wrote nothing too (count 0), as "per backfill call" says.
- An `at` exactly equal to a live reading's is not in the ledger, so a backfilled reading is still written there.
- At most 200,000 readings a backfill (lesson 4), so VictoriaMetrics takes them in one import.
- Outside "Files to touch": `ergostat/cli/parts.py` (two lines: `cmd_part` hands `--backfill`/`--backfilled` to `spec_cmds.backfill`), `ergostat/goodmodel.py` (`--backfill` classified as an act and `backfill` as a write for the read-only fallback, `--backfilled` and `--from` as reads; tests/test_cli_fallback.py checks that every flag is classified) and `ergostat/victoria.py` (the server backend's module the definition names).
- `docs/SPEC.md` has no CLI table, so the two commands are a table of their own in §6 (Sensors), with a line in §4b about where the ledger lives.
- `Measurements.range` changed by one condition: after a roll, a series' oldest reading came back once per tier (the 1h and 10m tiers' first buckets begin before the 1m tier's, and each was read for the gap). A bucket whose last reading lies past its part of the span is now read where that part ends. This was there on main for any rolled series, and `test_twice_after_the_roll_writes_nothing_new` ("the range holds each once") needs it. The same overlap still makes `count` (and maybe `first`) count that reading more than once for a span reaching back to the series' start. Not changed here: it is outside this gap.
Not run: the VictoriaMetrics case of the conformance suite (no server in the container: `ERGOSTAT_TEST_VM_URL` unset), the whole unit suite (left to the factory's build step).
