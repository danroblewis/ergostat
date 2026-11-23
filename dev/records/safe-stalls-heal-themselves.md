# safe-stalls-heal-themselves: a lease whose process is gone is released, and a stall is said where it is seen

On 2026-11-22 the merge queue stopped for 40 minutes behind a lease whose process had died. The pipeline manager diagnosed it correctly within minutes, in a record nobody was shown, and nothing acted. An engine restart did not end the lease either.

Change:
- The engine releases a lease as soon as the process of the run holding it is gone (the run record's pid and start time), given back **uncounted** when the cause was outside the item (the engine, Docker or a restart). A lease on a remote or detached run is left alone.
- When an engine starts, it ends the leases of runs that no longer exist.
- A run that fails because Docker or the AI service is unreachable is an outage: it pauses and retries, and does not spend the item's attempts or park it.
- The pipeline manager's latest finding is shown on the page's attention list, not only stored in its situation.

Definition of done:
1. A test kills a run's process and its lease is released within one dispatch pass, uncounted, and the queue takes its next batch.
2. A live run's lease is never released, including across a pid reuse.
3. A Docker outage during a run parks nothing, and the items run again when it returns.

## Where it stopped

Built, round 1. Net lines outside tests/, docs/ and dev/: about 210 (budget 600).

- Done 1: `tests/test_lease_gone.py::test_a_killed_runs_lease_is_released_in_one_pass_uncounted_and_the_next_is_taken`
  (one `watch()` releases it, `count: false`, one attempt allowed and the item not a dead letter, then `tick()` takes
  the next), and `::test_a_running_engine_releases_it_once_its_process_is_killed` (a started engine).
- Done 2: `::test_a_live_runs_lease_is_never_released_and_a_reused_pid_is_not_it` (a live pid kept over five passes; a
  pid whose start time differs is gone; no start time or an unreadable record is unknown, never gone; nothing
  signalled), `::test_an_engines_own_live_run_is_never_released`, `::test_a_run_record_tells_gone_from_unknown`.
- Engine start: `::test_at_start_a_lease_of_a_run_that_no_longer_exists_is_ended`.
- Done 3: `tests/test_factory_outage.py::test_a_docker_outage_during_a_queue_run_parks_nothing_and_it_lands_when_docker_returns`
  (the queue's run on its last attempt, Docker down: an uncounted nack put off 10m, nothing parked, sent back or
  failed, main as it was; Docker back: it lands), and the implementor/reviewer path through `fac.guarded`.
- Finding on the attention list: `tests/test_finding_attention.py`.
- Mutations seen to fail the tests: the `count: false` dropped, unknown read as gone, `max` made `min` for the latest
  finding, the queue's outage branch bypassed.

Choices made with nobody to ask, each the more reversible one:
- "Uncounted when the cause was outside the item" is read as: a lease whose run this engine is *not* following (an
  engine gone, a restart) is given back uncounted. A run this engine follows and that is killed from outside still
  ends as any run does (a counted `exited -9`), unchanged.
- "Remote or detached" is read as: any lease whose block is not one this engine runs with a run record (a daemon's
  block, a block of another shard or engine, a block no longer in the model) is left to its TTL, as before.
- The "no record" rule (the run no longer exists) applies only on the engine's first full watchdog pass, as the
  definition says; later a lease with no record is left to its TTL.
- A released run's files (`runs/RUN.*`) are left in place, not deleted; its output was never read.
- Outage detection is an allowlist: the AI service by connection-error words; Docker by words naming Docker confirmed
  by `docker info` failing. An outage retries every 10 minutes for as long as it lasts (a bounded rate, no ceiling on
  the count), and its session hours are not added toward the kill rule.
- The finding is shown through a new, generic kind key `attention: FIELD` (SPEC §5a), set in the factory's
  `ergostat.yaml` on `situation` as `attention: finding`, and the manager writes `finding` on `situation.handled`.
  "Latest" is by the item's latest event time, then its id. No page code changed: the entry has the shape the page
  already draws (like a precedence cycle's), so no browser file was run for it.

Two existing tests pinned the old behaviour (only a TTL ended a dead engine's lease) and were updated:
`tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth` and
`tests/test_resilience.py::test_a_hard_restart_spends_no_attempt`; two in `tests/test_leased_workspaces.py` now give
their hand-made run a record naming a live process.

Not mine, left alone: `tests/test_agents.py::test_a_rerun_is_timed_by_the_suite_that_failed` fails alone, before
any change of this branch to dev/bin, on `ModuleNotFoundError: No module named 'flakes'` (dev/bin/onmain.py:25).
