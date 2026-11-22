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

Round 2: the one review finding (store.py `_replace`: late readings dropped across every tier's dropped buckets, so a late reading outside the span, in a dropped coarse bucket but in a finest bucket not dropped, was lost) is fixed. The waiting late readings are now cleared only over the span and the finest tier's dropped buckets, the ones made again from the raw readings (which hold those late readings); every other waits for the next roll and is merged into every tier then. This replaces the round-1 choice "Late readings are dropped across all the dropped buckets". SPEC's "Replacing a span" says so. Net lines outside tests, docs and dev unchanged (81).
New conformance case `test_backfill_replace_keeps_a_late_reading_outside_the_span` (the review's trace: tiers 60/600 s, raw 3600 s, roll, a late reading at now-7130, replace [now-6700, now-6650], roll; the 1m bucket at now-7140 and the 10m bucket at now-7200 hold it). Seen to fail with the old widening (`[tiers]`: 1.0 where 3.0 is due); passes with the fix on `sqlite` and `tiers`.
Found and left alone: a finest bucket whose raw readings were forgotten by a roll but which has a late reading written raw since is made again from that late reading alone, so its earlier readings outside the span are lost and not counted in `replaced`. Telling a bucket whose raw readings are whole from one that holds only late ones needs where raw was last cut, which main does not record (the same root as the `_sources` issue above); it is narrow (one finest bucket at each edge of the span, only with a late reading in it), so it is left for its own gap.
Not run, round 2: the VictoriaMetrics cases (no server); the whole unit suite and the browser files (left to the factory).

Round 3: the one review finding (store.py `_replace`: only the finest tier's dropped, unrebuilt buckets counted, so a span older than the finest tier's keep reported `replaced: 0`) is fixed. Every tier's dropped bucket that is not made again now counts its readings, less what the source under it already counted: for the finest tier, the raw readings deleted in it that were not waiting as late (late ones are not in a bucket's count yet); for a coarser tier, the finer tier's dropped buckets in it. This also removes a double count the round-2 code had: a finest bucket wholly inside a span still kept raw was counted both as raw readings and as a dropped bucket. SPEC's "Replacing a span" says what `replaced` counts, and that only raw readings can be kept one by one in `forgotten` (a bucket holds a count and a sum). Net lines outside tests, docs and dev: 89.
New tests: `tests/test_sensor_backfill_replace.py::test_replace_older_than_the_finest_keep[30-15, 120-30]` (the default tiers through the CLI, spans 30 and 120 days old: "15 set aside" / "30 set aside", the count left in the range, the hour after and the 10m buckets beside the dropped ones untouched); conformance `test_backfill_replace_past_the_finest_keep` (tiers 1m/1d, 10m/7d, a span 3 days old: `replaced` 10, the buckets beside it whole) and `test_backfill_replace_counts_each_reading_once` (a span still raw: 31, not 61).
Checked that they can fail: with only the finest tier counted (round 2), the three tiered cases of the first two fail (`0 set aside`, `0 == 10`); without the subtraction of what lies under, `test_replace_after_the_roll` (30 where 10 is due) and `test_backfill_replace_counts_each_reading_once[tiers]` (61 where 31 is due) fail; without leaving the late readings out of what lies under, `test_backfill_replace[tiers]` fails (16 where 17 is due).
Choice taken without asking: a coarser bucket's readings are taken to equal the sum of the finer buckets inside it (both tiers merge the same late readings, and a tier is forgotten in whole buckets of the next), so a bucket counts only what is beyond the finer ones'. Where that does not hold (the round-2 "found and left alone" case of a late reading in a raw-forgotten finest bucket), the count can be short, as stated there.
Not run, round 3: the VictoriaMetrics cases (no server; its `_replace` has no tiers and was not changed); the whole unit suite and the browser files (left to the factory). Main has no commits past the branch's last merge.
