# upkeep-record-loops: event-log roll-up and forgetting, and measurement retention, drawn in `use: upkeep` as stocks held by goals and done by rule-tier controllers, under one cross-process compaction lock
depends-on: [upkeep-index-files]

## Definition of done

Today `runner._prune` runs `rollup.upkeep` every `storage: rollup: every`: roll-up, prune past `keep`, archive forget, and `measurements.roll`. `ergostat compact` runs the same from another process, and nothing stops the two overlapping. When this branch is done:

1. **One compaction lock.** Roll-up, prune and archive forget run only while holding `<state>/compact.lock`, an exclusive `flock` taken without waiting. `measurements.roll` runs under the same lock.
   - Every caller takes it: the engine's `_prune`, `ergostat compact`, and the new programs.
   - A caller that finds the lock held does nothing to the record and says `busy` (a log line, exit 0 for a program, a line from `ergostat compact`).
   - The lock is released when the holder's process dies (a `flock`, never a pid file).
2. **Measures**, added to the `ergostat.upkeep.*` family:
   - `ergostat.upkeep.rollup-due`: items with events past their roll-up horizon outside a snapshot. It is the same number `compact(p, cap=keep, dry=True)["items"]` gives, read without rolling anything.
   - `ergostat.upkeep.events-past-keep`: events older than the model's `keep`.
   - `ergostat.upkeep.measurements-due`: raw measurement rows past `storage: measurements: raw`, and tier rows past their tier's keep.

   A backend that cannot say gives no reading (`None`, said), never 0 (lesson-3). That covers `victoriametrics`, and an events store without the count.
3. **Template parts** (in `upkeep/template.yaml`):
   - stocks `rollup-due`, `events-past-keep`, `measurements-due`;
   - goals `record-rolled-up` (`rollup-due <= 0`), `record-within-keep` (`events-past-keep <= 0`) and `measurements-within-tiers` (`<= 0`);
   - controllers `record-compactor` (`type: program`, `run: ${lib} upkeep rollup`, `every: ${rollup-every}`, default 1h) and `measurement-retainer` (`type: program`, `run: ${lib} upkeep retain`, `every: ${retain-every}`, default 1h);
   - outflows measured `changes: falls`.

   `rollup-every` and `retain-every` must be between 1m and 1d, enforced at load and in the programs (lesson-4).
4. **Programs.**
   - `upkeep rollup` does the roll-up, prune and archive forget of `rollup.upkeep`, minus the measurements.
   - `upkeep retain` does `measurements.roll`.
   - Each prints one result line (what it did, or `busy`).
   - Each holds the compaction lock for all of its work.
5. **The engine stands down.** In a model with `use: upkeep`, `runner._prune` still rotates and trims the logs, but no longer calls `rollup.upkeep`; the two blocks do that.
   - `check` gives a finding when such a model also sets `storage: rollup: every`, which is then unused, naming `rollup-every` instead.
   - Without the template, behaviour is as on main, except for taking the lock.
   - If the blocks stop, the record only grows. Reads, folds and the item index stay right.
6. **Cancel or timeout.** A program killed at its block's timeout leaves the record whole: `p.events.replace` is the only write, as on main. The next program run takes the lock.
7. **Docs.** SPEC §4b says what `use: upkeep` changes, and documents the lock and `busy`. The *Upkeep* subsection gains these loops. The GAPS entry is updated.

## Files to touch

- `ergostat/rollup.py` (the lock; `upkeep` split so the measurements can run alone)
- `ergostat/runner.py` (`_prune`)
- `ergostat/cli/record.py` (`cmd_compact` takes the lock)
- `ergostat/library/run/upkeep.py`
- `ergostat/library/templates/upkeep/template.yaml`
- `ergostat/upkeep_measures.py` (or wherever sub-gap 1 put the family)
- `ergostat/spec/ir.py`
- the measurement store (`ergostat/store.py` or its SQLite measurements module): the count of rows due
- `ergostat/spec/findings.py` (or wherever storage findings live)
- `docs/SPEC.md`, `docs/GAPS.md`
- `tests/test_upkeep_record.py` (new)

## Risks

- **lesson-1.** Two compactors (engine and CLI, or the block and the CLI) each read what is due, decide, and replace it. *The fix:* the lock is held across read, decide and write.
- **lesson-3.** A store that cannot count, read as 0, would show the goals met. *The fix:* `None`.
- **lesson-4.** The `every` values need a floor and a ceiling.
- **lesson-6.** A roll-up killed at its timeout must not leave the lock held or the record half-written.
- **lesson-8.** "Fails safe" needs a test. So does the claim that `rollup-due` is the same number compact rolls.
- **lesson-9.**
- **lesson-10.** The lock test must use events (a `threading.Event` held inside a monkeypatched `compact`), not sleeps.
- **lesson-13.** Any unrelated store or roll-up flake is reported, not fixed.

## Acceptance tests

- `tests/test_upkeep_record.py::test_a_second_compactor_while_one_holds_the_lock_does_nothing`: `compact` is monkeypatched to wait on an Event while holding the lock. `ergostat compact` and `upkeep rollup` run meanwhile both say `busy`, and the record's event count and snapshots match one roll-up. Fails without the lock (lesson-1).
- `tests/test_upkeep_record.py::test_a_killed_compactor_releases_the_lock`: a subprocess holding the lock, made slow, is killed. The next `upkeep rollup` takes the lock and rolls up, and the items fold the same as before (lesson-6).
- `tests/test_upkeep_record.py::test_rollup_due_is_what_compact_would_roll`: on a record with old events, the measure equals `compact(..., dry=True)["items"]` and is 0 after `upkeep rollup` (lesson-8).
- `tests/test_upkeep_record.py::test_a_store_that_cannot_count_gives_no_reading`: a VictoriaMetrics-configured measurements store and a stub events store without the count give `None` (lesson-3).
- `tests/test_upkeep_record.py::test_with_upkeep_the_engine_rolls_nothing_up_and_without_it_does`: `_prune`'s step is run once in each kind of model; only the model without the template calls `rollup.upkeep`.
- `tests/test_upkeep_record.py::test_compaction_stopped_grows_the_record_and_nothing_breaks`: with `use: upkeep` and the blocks never run, items, flows counted from items, and `archived()` all read right.
- `tests/test_upkeep_record.py::test_every_out_of_range_is_refused` (lesson-4).
- `tests/test_upkeep_record.py::test_storage_rollup_every_with_upkeep_is_a_finding`.
- Existing: `tests/test_rollup.py`, `tests/test_storage.py`, `tests/test_item_index.py` (all).
- The report says each new test was seen failing against broken code (lesson-9).

## Size budget

300 net lines outside `tests/` and `docs/`.

## Notes from the plan review (answer each; not blocking)

- test_a_killed_compactor_releases_the_lock kills the lock holder directly, so it cannot fail on lesson-6 as DoD 6 states it (killed at the block's timeout): if the engine kills only an `sh -c` wrapper, the python child keeps the flock and keeps writing. The test must drive `record-compactor` through the engine with a short timeout and a slowed compaction, then show no process left in the group, the next `upkeep rollup` taking the lock (not busy), and items folding the same as before.

## Where it stopped

Built, round 1: every item of the definition, by its acceptance tests. 281 net lines outside `tests/`, `docs/` and `dev/` (330 added, 49 removed), within the 300 budget.

**The plan review's note, answered.** `test_a_killed_compactor_releases_the_lock` drives the template's own `record-compactor` through `Engine.run_block`. Its `run:` is the template's command with only the module swapped for a script that slows `rollup.record` inside the lock. It runs under the engine's `sh -c` run wrapper, so the python is a grandchild. The block's timeout is made to fire once the child is inside the lock: `stream.follow` is wrapped to wait for the child's flag, then given an immediate deadline. The test then shows no live process left in the run's process group, the next `upkeep rollup` taking the lock and rolling up (not busy), and items folding as before. Breaking `runner._kill` to kill only the wrapper's pid made it fail, with the python child and its `sh` still alive in the group.

**Choices made alone (the most reversible; each a line or two to undo):**
- The programs take `--every D` (`run: ${lib} upkeep rollup --every ${rollup-every}`, and the same for `retain`), not the bare `upkeep rollup` the definition shows. This is so they can refuse a value outside 1m to 1d at run time (lesson-4, exit 2).
- "One result line": `upkeep rollup` prints one JSON line moving `flow.rolled-up` (items), with `events`, `pruned` and `archive_forgot` beside it. `upkeep retain` prints one line moving `flow.measurements-forgotten` (rows). `events-forgotten` is measured only by its stock's falls. `busy` is said as words (`busy: ...`, exit 0), not JSON, so the engine logs it and moves nothing.
- Flow names: `rolled-up`, `events-forgotten`, `measurements-forgotten`. A parameter `due-every` (10m) says how often the three stocks are read. `rollup-due` is a dry roll-up, too heavy for the 1m `count-every`.
- `events-past-keep` counts what `prune` would forget (`Events.prunable`, `Segments.prunable`, sharing `prune`'s own predicate), not every event older than `keep`. The model's history and each loop's last crossing are never forgotten, so counting them would leave `record-within-keep` off forever.
- `measurements-due` is 0 for a store with no tiers, because `roll` then forgets nothing.
- Template params of type `duration` may now carry `min:`/`max:` as durations (`library/templates.py`, `expand.coerce`). That is the load-time check.
- `Storage.every_set` records that `storage: rollup: every` was written, for the `unused-rollup-every` finding.
- `ergostat compact --dry-run` takes no lock, since it writes nothing. `vacuum` runs after the lock is let go, as it reads and decides nothing about the record's content.
- `runner._prune`'s step is the module function `runner.prune_once(p, say)`, because `spec/engine.py` runs `Runner._prune` with the Engine as `self`.
- The existing `tests/test_upkeep_template.py::test_upkeep_expands_to_the_index_files_loop` pinned the template's exact part sets. It now lists the new parts too.

**Each new test seen failing against broken code (lesson-9):**
- No `flock` (always held): the lock test, the flock-across-processes test and the engine test's busy half fail.
- `_kill` killing only the wrapper's pid: the killed-compactor test fails.
- `rollup-due` read from the item index's candidates: `test_rollup_due_is_what_compact_would_roll` fails, after an item with one old event was added so the two numbers differ.
- A store that cannot count read as 0: the no-reading test fails.
- The engine not standing down: the engine and stopped-compaction tests fail.
- No `min`/`max` in the template, and the program's range check off: the range test fails.
- The finding off: the finding test fails.

**Run, one file at a time:**
- test_upkeep_record (12), test_upkeep_template, test_rollup, test_storage, test_item_index and test_templates: 170 passed.
- test_store_conformance, test_scale_caches, test_runner_and_state and test_resilience: 153 passed, 7 skipped (VictoriaMetrics, no server).
- ruff: clean.

**Not run:** the whole unit suite, the four browser files and `demo_check`. No example was touched. They are left to the factory's runs. There is no `origin/main` in this clone, and `main` has nothing this branch lacks, so there was nothing to merge.

**Left on the machine.** The lesson-9 run that broke `_kill` left two processes of its own: process group 513, an `sh` and a python asleep holding a lock in a pytest temp folder. `ps` and `kill` were refused in this session, so they could not be removed. The test now kills its own group if that assertion fails.
