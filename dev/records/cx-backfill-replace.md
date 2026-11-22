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

## Where it stopped

Built, round 1: every item of the definition and every named acceptance test, plus `test_a_store_from_before_the_columns_takes_a_replace`; 81 net lines outside tests, docs and dev.
Choices taken without asking (each the more reversible one):
- "why" is a new column, `forgotten.why`, and "replaced, with when" a new column, `backfills.replaced` (a time). Both are added to an existing file by `alter table` at open, the way `events.change` already was (`store.ADDED`). On `victoriametrics` the readings set aside go to `measurements.forgotten.json` with a `why` key.
- An earlier backfill is marked `replaced` when its first-to-last span overlaps the new one, even if only in part. Its ledger entries outside the span stay, so those readings are still skipped.
- `replaced: N` counts the raw readings set aside, plus the readings of finest-tier buckets that were dropped because their raw readings were gone. A dropped bucket that overlaps the span's edge loses its readings outside the span too, and those are in N. Coarser buckets are made again from the next finer tier, where it still holds them. SPEC says this.
- Late readings are dropped across all the dropped buckets, not only inside the span. Late readings are also raw readings, and the finest buckets are remade from the raw readings, so keeping them would count them twice at the next roll.
- On `victoriametrics` the compaction lock (`compact.lock`) is taken with waiting, together with the ledger's transaction. It does not stop the engine's live writes: a reading sent between the read-out and the delete is lost. If the import after the delete fails, the series is left without its readings: the ledger rolls back, but the server cannot. `forget` already had both windows. SPEC states the first.
- Outside "Files to touch": `ergostat/goodmodel.py` (`replace` listed with the read-only flags; it only modifies `--backfill`, which is already an act) and `ergostat/victoria.py` (the server backend's module the definition names).
Found and left alone (lesson 13; already on main): after a roll has forgotten a series' raw readings, one late reading written raw makes `Measurements._sources` treat raw as holding everything after it. Until the next roll, `range` then hides the buckets after that reading. `test_backfill_replace` reads its "outside" baseline before the late reading so this does not affect it.
Checked that the tests can fail: with the overlapping buckets dropped but not remade, `test_backfill_replace[tiers]` fails; with late readings left, it fails; with the span's raw readings not deleted, four of the six named tests fail.
Not run: the VictoriaMetrics case of the conformance suite (`ERGOSTAT_TEST_VM_URL` unset, no server in the container); the whole unit suite and the browser files (left to the factory). No page changed.
