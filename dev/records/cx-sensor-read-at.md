# cx-sensor-read-at: `sensor --read V --at T` no longer records now

depends-on: []

Branch `cx-sensor-read-at`, from main. Core. Found while planning the complexity backfill.

## The problem

`ergostat sensor PART.SENSOR --read 5 --at 1d` parses the global `--at` and then records the reading at the present time (`read_manual` in `ergostat/cli/spec_cmds.py` calls `measurements.add(series, value)` with no time). A person believes they recorded yesterday's value. The global `--at` means "as it was then" for reads; using it as a write time would give one flag two meanings.

## The change

`--read` together with `--at` is refused.

## Definition of done

1. `--read V --at T` exits 2, writes nothing, and says: `--at` views the past and records nothing; a reading at a past time is recorded with `--backfill` (named only if that option exists in the parser at build time, else the sentence stops before it).
2. `--read V` alone is unchanged.
3. `docs/SPEC.md` says so where `--read` is described.

## Files to touch

`ergostat/cli/spec_cmds.py`, `docs/SPEC.md`, `tests/test_sensor_read_at.py` (new).

## Acceptance tests

- `test_read_with_at_refused_and_nothing_written`.
- `test_read_without_at_unchanged`.
Unit suite rc 0, ruff clean.

## Size budget

10 net lines outside `tests/` and `docs/`.

From the owner's request of 2026-11-22: measure ergostat's code complexity in many forms and slices, as stocks on main, backfilled from git history.
