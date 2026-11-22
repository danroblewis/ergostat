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

## Where it stopped

Built, round 1. Everything in the definition of done is in the branch, with the acceptance tests passing. What
was decided without anyone to ask, each the more reversible option:

- **`type: external` blocks take no `goal:` key** (the loader refuses it), so `watchdog`, `outer-watcher` and
  `lease-expiry` read their goal as `in: goal.NAME`, the form SPEC's own external example uses. `pool-keeper` (a
  person) takes `goal:` as written.
- **Flows the definition did not list.** `test_every_built_in_template_checks_with_its_example` wants no finding
  from the template's own parts. A goal whose block moves no flow of its stock is *missing feedback*, and a stock
  with no flow is *stock-without-flows*, so each loop gets its flows, all read from their stock (`changes:`):
  `heartbeat-renewed` and `restarts-made` (the outer watcher's), `restarts-aged-out`, `stalls-mended` (the
  watchdog's), `overdue-leases-expired` and `leases-expired` (lease expiry's), `expired-leases-aged-out`,
  `free-workspaces-moved` (two-way, `net`) and `quarantined-workspaces-freed` (the pool keeper's). A flow between
  two stocks cannot be read by `changes:`, so none chains two stocks. `restarts` has no goal; the definition gave it none.
- **`stale` in the watcher** is read by `limit()`, checked by `ir.stale_ok`: a real, non-bool number with
  `60 <= x <= 3600`, so NaN, ±Infinity and `true` fail it. A missing `stale` is the normal case and is said
  nowhere; a malformed or out-of-range one is said in `run.log` once for each distinct value, per watcher process.
- **The engine writes `stale`** from the model as it is at each beat (`ir.heartbeat_stale(eng.spec)`), only when
  the use is ergostat's own `upkeep` and its `heartbeat-fresh` is `<= N` within the bounds. The heartbeat the run
  writes as it starts (`cli/running.py`) carries no `stale`, so the watcher uses 180 until the first beat (5 s).
- **heartbeat-age with a pass in the future** gives no reading (not clamped); so does a non-finite or non-number pass.
- **stalls / restarts**: an event log that raises, or none, gives no reading.

The plan review's notes, each answered:

- *Reads only its three files*: `test_the_watcher_reads_only_its_three_files` records every `open`, `io.open` and
  `os.stat` during `watcher.look`. A look that does nothing touches only `run.pid`, `heartbeat.json` and `stopped`.
  A look that restarts also touches its own back-off (`restarts.json`, with its temp file) and `run.log`, as on main;
  SPEC says so.
- *lesson-9's risk*: a fallback test passing because the default and the given value agree, or a test of a guard
  that never reaches it. The 100 s / 200 s pair sits between 59 and 180 and between 180 and 3601, so neither bound
  passes by luck. The breaks used, each seen failing its test and then reverted:
  1. `limit()` returning `STALE` always (the watcher ignoring `stale`): `test_the_watcher_restarts_at_the_goals_limit`.
  2. `limit()` taking any number, no range check: `test_a_bad_stale_falls_back_to_the_default` for 0, -5, 1e9,
     true, NaN, Infinity, 59 and 3601 (`"x"`, `null` and `[600]` are caught by the type check that break kept).
  3. `heartbeat()` merging the old file into the new: `test_stale_is_dropped_when_the_template_is`.
  4. `heartbeat_age` and the event measures giving 0 when their file or log cannot be read:
     `test_heartbeat_age_reads_none_without_a_heartbeat` and `test_stalls_and_restarts_count_their_windows_and_read_none_without_a_log`.
  5. the future-pass guard removed: `test_heartbeat_age_reads_none_without_a_heartbeat`.
  6. the template's `min:`/`max:` on `stale` removed: `test_stale_out_of_range_is_a_load_error[59]` and `[3601]`.
  7. `look` also checking the model file: `test_the_watcher_reads_only_its_three_files`.
  8. the watchdog skipping its look under `use: upkeep`: `test_the_watchdog_runs_whatever_the_goals_say`.
- *Bad stale cases*: `0, -5, 1e9, "x", true, NaN, Infinity, 59, 3601, null, [600]` and missing, at 100 s (no restart)
  and 200 s (restart). Each checks the `run.log` line is said once (none when missing).
- *Load-error cases*: 59, 3601 and `"x"` are errors naming `stale`; 60 and 3600 load
  (`test_stale_at_its_bounds_loads`).
- *lesson-3 for stalls/restarts*: tested, as above. *For a future pass*: no reading, tested.
- *Logging*: only malformed or out-of-range values, once per value per watcher process.
- *SPEC*: says `stale` lets the watched engine relax the outer watcher's limit to at most 3600 s (or tighten it to
  60 s) and never turns it off; it makes no "cannot weaken" claim.

**Size.** 295 net lines outside `tests/`, `docs/` and `dev/`: 45 over the 250 budget. About 99 are Python. The rest
is the template's YAML: the parts the definition names, a dozen lines of `reading:`, and the 9 flows above (about
70 lines, block style like the rest of the template) that the existing template check needs. They are what pushed
it over. A reviewer who prefers it under budget can fold the sensors into flow-style maps
(`sensor: {changes: falls, over: "${over}", every: "${watch-every}"}`), about 40 lines.

**Existing test changed.** `tests/test_upkeep_template.py::test_upkeep_expands_to_the_index_files_loop` asserted the
template's exact set of parts; it now adds the default watched parts to each set.

**Not run here**: the full unit suite under the watchdog, the four browser files and `demo_check` (no example is
touched). Those are the factory's to run. origin/main is not merged in: this clone has no `origin/main` ref, and
local `main` has no commit past this branch's base (`git log HEAD..main` is empty).

### Round 2

The queue's blocking finding was the size, 295 against 250. It is now **175 net lines** outside `tests/`, `docs/` and
`dev/` (`git diff main --numstat -- ergostat/`): template 74, `upkeep_measures.py` 52, `watcher.py` 21, `ir.py` 20,
`watchdog.py` 6, `measures.py` 1, `compile.py` 1. No behaviour was cut to get there. The watched parts the template
adds (7 stocks, 10 flows, 4 goals) are now each one flow-style map on one line, the form `repair/template.yaml`
already uses for its stocks, flows and goals. The index-files parts from sub-gap 1 are left as they were, in block
style. The parsed template is the same as before apart from the new flow below: the `${...}` values that were plain
scalars are now quoted, and YAML parses both to the same string.

The round-1 review's two non-blocking findings (lesson-12):

- *heartbeat-age had only an outflow; its inflow, time passing, was not drawn.* It is drawn now: the inflow
  `heartbeat-aged` (`changes: rises`), whose description says a reading of an age that resets on every pass is
  mostly this sawtooth. SPEC says the stock fills by it. `test_upkeep_template.py`'s exact set of parts includes it.
  The template check still finds nothing in the default expansion or with `leases: true, pool: p`.
- *events() counts an in-memory log, unlike the other measures, and does not say so.* Kept as it is: a log held only
  in memory still holds the events being counted, while a folder or file that is not there gives nothing to count.
  The module docstring now says this, and says that "kept nowhere on disk gives no reading" covers only the index files
  and the heartbeat.

Run in round 2, one file at a time: `tests/test_upkeep_watched.py`, `tests/test_upkeep_template.py`,
`tests/test_templates.py`, `tests/test_watchdog.py`, `tests/test_resilience.py` and the watcher test in
`tests/test_graph_cli_web.py` (`-k watch`). All pass, and ruff is clean. No new test was added this round, so the round-1 breaks still
stand. The same items as round 1 were not run. origin/main is still not merged, for the same reason (this clone has no
`origin/main`, and `git log HEAD..main` is empty).

### Round 3

The queue's finding was that the push of its merge (ce282fdaf099) was denied and the merge undone. That commit is
not in this clone, so the reason for the denial could not be read here. What the branch itself got wrong is fixed:

- **lesson-7, a merge splice.** The merge of main (2af3876b) brought back an old copy of the *From upkeep's fault
  injection* entry in `docs/GAPS.md`, just after this gap's entry. Main has already moved and rewritten that entry,
  which the branch still has further down, so the file held two contradictory copies. The stale copy is removed.
  `git diff main -- docs/GAPS.md` now shows only this gap's lines.
- **Wrap width.** A SPEC line this gap added (the `heartbeat-aged` / `restarts` bullet) ran past the wrap width. It is
  reflowed, along with the two §9.1 sentences this gap edited.

No code changed. The size is still 175 net lines outside `tests/`, `docs/` and `dev/`. `git log HEAD..main` is still
empty, so there is no newer main to merge. Run in round 3, one file at a time: `tests/test_upkeep_watched.py`,
`tests/test_upkeep_template.py`, `tests/test_templates.py` (72 passed), `tests/test_watchdog.py`,
`tests/test_resilience.py` (43 passed), and
`tests/test_graph_cli_web.py::test_the_service_text_runs_this_repositorys_watcher`. Ruff is clean. The unit suite,
the four browser files and `demo_check` were not run here.
