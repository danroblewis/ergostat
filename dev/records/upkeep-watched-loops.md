# upkeep-watched-loops: the engine's stall watchdog, expired leases and the worktree pool drawn in `use: upkeep`, and a heartbeat goal whose limit the outer watcher reads
depends-on: [upkeep-index-files]

## Definition of done

Today these protective functions run in the code with constants:
- the watchdog (`spec/watchdog.py`): `STALL`, back-off in `restarts.py`, `heartbeat.json` every `BEAT` s;
- lease expiry (`leases/dispatch.py`);
- the outer watcher (`watcher.py`), which restarts an engine whose heartbeat is older than `STALE = 180`.

The measures `ergostat.leases.*` and `ergostat.workspaces.*` exist. None of these loops is drawn. Protective functions stay in the code: no goal or block can turn them off or bypass them (`coordinator/08-modes-and-protection.md` §5.3). When this branch is done:

1. **Measures**, added to the `ergostat.upkeep.*` family:
   - `ergostat.upkeep.heartbeat-age`: seconds since `heartbeat.json`'s last pass. No reading when the file is missing or unreadable, never 0 (lesson-3).
   - `ergostat.upkeep.stalls`: `ergostat.engine.stalled` events over the last hour.
   - `ergostat.upkeep.restarts`: `ergostat.engine.restarted` events over the last day.
2. **Template parts** (in `upkeep/template.yaml`):
   - stocks `heartbeat-age`, `stalls`, `restarts`;
   - goal `heartbeat-fresh`: `heartbeat-age <= ${stale}`, default 180, within 60..3600, enforced at load;
   - goal `no-stalls`: `stalls <= 0`;
   - `type: external` blocks (observed, never run by ergostat): `watchdog` (the engine's own, `goal: no-stalls`) and `outer-watcher` (`ergostat run --service`, the runner or launchd, `goal: heartbeat-fresh`). Each description names the code that does the work.
   - With `leases: true` (default false): stocks from `ergostat.leases.overdue` and `ergostat.leases.expired`, goal `no-overdue-leases` (`<= 0`), and a `type: external` block `lease-expiry` (`leases/dispatch.py`).
   - With `pool: NAME` (default empty): stocks from `ergostat.workspaces.free@NAME` and `ergostat.workspaces.quarantined@NAME`, goal `no-quarantined-workspaces` (`<= 0`), and a `type: person` block `pool-keeper` that asks the owner to free a quarantined slot (`ergostat` workspaces free). Ergostat never frees one by itself.
   - Nothing appears for leases or a pool unless asked for (invariant 12).
3. **The heartbeat goal is read from outside.**
   - In a model with `use: upkeep`, the engine writes the goal's limit into `heartbeat.json` as `"stale": N`. The file is written whole each beat, so a model without the template writes no `stale` key.
   - `watcher.look` uses `stale` when it is a number within 60..3600. Missing, malformed or out of range, it uses `STALE` (180), said once in `run.log`.
   - The goal moves when the watcher restarts. It never changes whether the engine's own watchdog runs.
4. **No controller reads what it manages.**
   - The watcher reads only `run.pid`, `heartbeat.json` and `stopped`, as on main.
   - The engine's sensor reading `heartbeat-age` is a drawing, not a protection: a frozen engine reads nothing, and the outer watcher is the layer that acts.
   - SPEC says the layers in this order: the engine's watchdog, then the outer watcher or launchd, then the owner.
5. **Docs.** SPEC's *Upkeep* subsection gains these loops, the layers and the `stale` key, with the 60..3600 bounds and the fallback. SPEC §9.1's watcher paragraph names `stale`. The GAPS entry is marked done, with what is left.

## Files to touch

- `ergostat/library/templates/upkeep/template.yaml`
- `ergostat/upkeep_measures.py` (or wherever sub-gap 1 put the family)
- `ergostat/spec/ir.py`
- `ergostat/spec/watchdog.py` (`heartbeat` writes `stale`)
- `ergostat/watcher.py` (`look` reads it, bounded)
- `docs/SPEC.md`, `docs/GAPS.md`
- `tests/test_upkeep_watched.py` (new)

## Risks

- **lesson-3.** A missing heartbeat read as age 0 would show the goal met. A malformed `stale` read as 0 or infinity would make the watcher restart in a loop, or never restart. *The fix:* the measure gives no reading, and the watcher uses the bounded default.
- **lesson-4.** `stale` has a hard floor and ceiling, at load and in the watcher.
- **lesson-5.** A `stale` from a model that used the template must not survive once the template is removed. *The fix:* the file is written whole.
- **lesson-8.** Two claims need tests: "protective functions cannot be turned off by a goal", and "the watcher reads only its three files".
- **lesson-9.**
- **lesson-10.** Watcher tests pass `now=` and fake files, with no sleeps.
- **lesson-13.** Unrelated watchdog or lease flakes are reported, not fixed.

## Acceptance tests

- `tests/test_upkeep_watched.py::test_upkeep_draws_the_watchdog_and_watcher_as_external_blocks`: the expansion has the stocks, goals and `type: external` blocks named above. With `leases: true` and `pool: p`, it adds the lease and pool parts; with neither, none of them.
- `tests/test_upkeep_watched.py::test_heartbeat_age_reads_none_without_a_heartbeat`: it gives `None` with no file or a garbled file, and the right age with a file (lesson-3).
- `tests/test_upkeep_watched.py::test_the_watcher_restarts_at_the_goals_limit`: `heartbeat.json` with `stale: 600` and a pass 300 s old gives no restart. With `stale: 600` and 700 s it restarts. Fails if the watcher ignores `stale`.
- `tests/test_upkeep_watched.py::test_a_bad_stale_falls_back_to_the_default`: `stale` of `0`, `-5`, `1e9`, `"x"` or missing, with a 200 s old pass, restarts (180 applies). With 100 s it does not (lesson-3, lesson-4).
- `tests/test_upkeep_watched.py::test_stale_is_dropped_when_the_template_is`: a beat from a model with the template, then from the same state without it, leaves no `stale` key (lesson-5).
- `tests/test_upkeep_watched.py::test_stale_out_of_range_is_a_load_error`.
- `tests/test_upkeep_watched.py::test_the_watchdog_runs_whatever_the_goals_say`: a model with `use: upkeep` and `stale: 3600` still has the engine's watchdog replace a wedged pool at `STALL`, as in `tests/test_watchdog.py` (lesson-8).
- Existing: `tests/test_watchdog.py`, `tests/test_resilience.py`, the watcher's tests, and `tests/test_templates.py::test_every_built_in_template_checks_with_its_example`.
- The report says each new test was seen failing against broken code (lesson-9).

## Size budget

250 net lines outside `tests/` and `docs/`.

## Notes from the plan review (answer each)

- lesson-8: Risks names 'the watcher reads only run.pid, heartbeat.json and stopped' as a claim needing a test, but no acceptance test covers it. Add one, e.g. `test_the_watcher_reads_only_its_three_files`: record every path `watcher.look` opens (monkeypatch `open`/`Path.read_text`) and fail on any path outside the allowlist.
- lesson-9 appears under Risks with no text. Say what the risk is (e.g. a fallback test passing because 180 and the given stale happen to agree), and in the report name the break used for each new test: watcher ignoring stale, no range check, writer merging the old file, measure returning 0 when the file is missing.
- `test_a_bad_stale_falls_back_to_the_default` should also cover `true` (a bool is an int in Python), `NaN` and `Infinity` (Python's json reads both), `59` and `3601`. The range check must be written as `60 <= x <= 3600` on a real non-bool number, so NaN fails it.
- `test_stale_out_of_range_is_a_load_error` has no body. Name the cases: 59, 3601, a non-number. Also check that 60 and 3600 both load.
- lesson-3 for `stalls`/`restarts`: if the event log is missing or unreadable, the measure must give no reading, not 0, because 0 shows `no-stalls` as met. Test it.
- lesson-3 for `heartbeat-age`: a last pass stamped in the future gives a negative age, which reads as fresh. Give no reading (or clamp it, and say which) and test it.
- 'Said once in run.log': a missing `stale` is the normal case for a model without the template, so don't log it as a fault. Log only a malformed or out-of-range value, once per value or per watcher process, and say which.
- SPEC must say plainly that `stale` lets the watched engine relax the outer watcher's limit to at most 3600 s and never disable it. Do not claim the goal 'cannot weaken' protection.
