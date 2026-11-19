# resilience-core: upkeep's faults, without the CLI's fallback

**The gap** (GAPS.md; `docs/proposals/upkeep.md` §4; split from `resilience` after its third gate review): nothing
restarts an engine killed or frozen whole, and `status` shows a dead engine's last reading as alive; the watchdog
restarts without finding the cause, every 6.5 minutes while the cause lasts, sees no hang while starting, and finds a
wedged pool at 130 s; an `alarm` block raises nothing anyone sees; block logs, `threads.txt`, `transcripts.json` and
`run.log` grow without limit, and the folders of projects whose repository is gone pile up.

**Split out:** item 1 of `resilience` (the command line using the engine's last good model while the YAML is
broken) stays on branch `resilience`, parked: its fallback could load a model that never existed (includes settled
against the live files). See that branch's definition file.

## Definition of done

1. **A dead engine restarted.** `ergostat run --service` prints a user LaunchAgent (macOS, `KeepAlive`) or systemd
   user unit (`Restart=always`) running the outer watcher (`python -m ergostat.watcher`), named per repository and
   running the Python of an installed `ergostat` (launchers, `.venv`s and temporary ones passed over);
   `--install` installs and loads it, `--uninstall` removes it. The watcher starts a dead engine unless `ergostat run
   --stop` left `<state>/stopped`, stops and starts one whose heartbeat is stale, backs off, and records
   `ergostat.engine.restarted` only for a start that succeeded. The heartbeat is written at start and every 5 s.
   `status` says "engine not running (last seen …)" and shows loops as they were. `--stop` and `--uninstall` work
   with the YAML broken (the state folder found without the model).
2. **The watchdog finds the cause and backs off.** Stall dumps name what holds the item index (the thread with its
   stack, other processes with the file open); restarts that did not help back off 60 s, 2 m, … 30 m
   (`restarts.json`); a startup deadline; only readings begun set the pool-wedge limit; a late reading from a replaced
   pool touches nothing of the new.
3. **Alarms show.** One line in needs attention and "alarm raised" on its block in Blocks (existing styles); an
   alarm's sensors read on a pool of their own, watched as the sensors' pool is; a failing alarm is cleared.
4. **Caps.** `storage: logs:` (block 5MB, run 5MB, threads 1MB, transcripts 30d); `ergostat compact --projects
   [--yes]`, deleting only folders whose repository is gone (its parent there), no engine running, no symlinks.

## Acceptance tests (`tests/test_resilience.py`)

The tests of `resilience` for these items (service, watcher, status, watchdog, back-off, startup, wedge timing, the
alarms' pool, alarms shown, caps, transcripts, compact), plus
`test_stop_and_uninstall_work_with_the_yaml_broken`. The four suites with rc 0, no page test skipped.

## Size budget

600 net lines of code outside `tests/` and `docs/`.

## Where it stopped / overrun

Done. Net 620 lines outside `tests/` and `docs/`, of which 26 are `schema/ergostat.schema.json` (the `storage: logs:`
schema, data rather than code): 594 lines of code, within the budget.
