# merge-queue-in-docker: the merge queue's suites run in containers, on CPUs of their own

depends-on: []

The owner (2026-11-21): "can we do something to add cpu caps to the implementor and merge docker containers? ... it would be really nice to know that they arent blocking eachother", and "the merge queue could also run in a docker container". Today the queue's suites run directly on the Mac (`fac.suite(..., slot=False)` in `dev/bin/queue.py`), outside every Docker limit, so they and the builders compete for the same cores and timing tests fail under load. The instance has a stopgap (`limits_for` in `dev/bin/agents.py`, `[agents] session_cpus`, `session_cpuset`, `suite_cpuset` in `factory.local.toml`) that covers sessions and per-gap tests only.

## Definition of done
1. `[agents]` in `dev/factory.toml` holds `session_cpus = 1.5`, `session_cpuset = "0-7"`, `suite_cpuset = "8-11"`, `queue_cpuset = "12-23"`, each with a comment. Docker's VM has 24 CPUs. An empty cpuset means no pinning.
2. With `[suites] queue_container = true` (the default), every suite the queue runs (ruff, unit, browser, demo, the quarantined tests beside them, the named rerun, flake triage's runs) runs in a container of the agent image with `--cpuset-cpus` from `queue_cpuset`, no network, the merge checkout mounted, and limits sized so unit and browser can run at once (unit 8 CPUs, browser 4). `false` runs them on the Mac exactly as today, so this can be turned off with one line.
3. The Mac's `.venv` in the checkout is never used or changed by a container, and a container's files never break the Mac's use of the checkout.
4. What the queue reads from a run still works in a container: logs, exit codes, `SKIPPED` counts, the coverage output under `run/coverage/`, and the watchdog (`suite_watch`).
5. A stopped or killed queue run stops its containers. The load interlock and `suites-running` count them.
6. The four demos and all four browser files pass in the container on a real merge of main. The real run's times, beside the same suites on the Mac, are written in *Where it stopped*.
7. *Where it stopped* names the instance's stopgap as ready to delete.

## Files to touch
`dev/bin/queue.py`, `dev/bin/agents.py`, `dev/bin/fac.py`, `dev/bin/triage.py`, `dev/factory.toml`, `tests/test_agents.py`, `tests/test_factory.py`.

## Risks
- The queue is the factory's one path to main: a container failure to start must fail the run as an infrastructure failure (lesson-3), never read as a green suite and never blamed on a gap.
- Demos bind local ports and start servers: each must run inside its own container's network namespace.
- `implementor-loop-stays-light` and `build-suite-configurable` touch `agents.py`, `onmain.py` and `factory.toml`: merge main often.

## Acceptance tests
- each queue suite's command runs in a container with the queue's cpuset and no network when `queue_container` is true
- with `queue_container = false` the commands are the same as today's
- a container that cannot start fails the run as infrastructure, with no gap blamed
- a stopped run leaves no queue container behind
- sessions, per-gap tests and queue suites get their three different cpusets

## Size budget
120 net lines of code outside `tests/` and `docs/`.

## Where it stopped (round 1, 2026-11-22)

**Built (points 1-5, 7):**
- `dev/factory.toml` `[agents]`: `session_cpus = 1.5`, `session_cpuset = "0-7"`, `suite_cpuset = "8-11"`,
  `queue_cpuset = "12-23"`, with comments. `[suites] queue_container = true`.
- `agents.limits(cfg, kind, cpus)`: LIMITS with that kind's `--cpus` and `--cpuset-cpus` (an empty cpuset pins
  nothing; a cpuset that does not parse raises and is never dropped). Sessions and their `finish` get `session`,
  a gap's own suites (`contained`) get `suite`, and the queue's and triage's get `queue`.
- `agents.queued(...)`: the queue's container. It runs the agent image with `--network none` (a demo's servers
  in its own namespace), the checkout at /work, unit at 8 CPUs, browser at 4 and the rest at 4. The name is
  `ergostat-factory-suite-queue-*` (triage's is `-suite-triage-*`), so the load interlock and `suites-running`
  count it by their existing `name=ergostat-factory-suite-` filter.
- `fac.suite(..., box="queue"|"triage")`: wraps the command when `queue_container` is not `false`. The
  container is killed by name in the suite's finally, and `fac.stop_suites` (the queue's stop path) kills every
  running one by name. Docker's own exit codes 125, 126 and 127 raise `agents.NotStarted`. The run then fails
  and main is undone, with no `queue-failed`, no flake and no gap blamed. A failing thread also stops its sibling.
- Every queue suite passes `box="queue"`: ruff, unit, browser, demo, the quarantined tests (`alone`) and the
  named rerun. Triage's rerun and its quarantined run pass `box="triage"`. Triage now calls
  `fac.stop_on_term()`, so a stopped triage run reaches its finally.
- A queue run killed with SIGKILL has no finally. The next queue run removes that run's containers first
  (`agents.sweep_box("queue")`, under the queue's lock, so none of them belongs to a live run).
- Point 3, the Mac's checkout. The container runs on the image's own environment
  (`UV_PROJECT_ENVIRONMENT=/opt/venv`, set again explicitly). An empty tmpfs covers `/work/.venv` when the
  checkout has one. Bytecode (`PYTHONPYCACHEPREFIX`) and ruff's cache go under the container's /tmp. The git
  directory is mounted read-only (a worktree's common dir at its own path, for triage).
- Point 4. Logs and exit codes are docker run's own stdout and exit code, written by `fac.suite` as before.
  `SKIPPED` counts are read from that log. `run/coverage/` is mounted at its own path, as `ERGOSTAT_COVERAGE`
  names it, and the line files are relative to the root, so the Mac-side report reads them. `suite_watch` runs
  inside the container as part of each command and watches that container's processes.

**Not done: point 6.** No suite has run in a real container from this session. Docker could not be reached: my
first look, `docker version 2>&1 | head -3; nproc; ls ~/ergostat 2>&1 | head -2`, was refused, and this clone
is not the owner's Mac. So the four demos and the four browser files have not been seen to pass in a queue
container on a real merge of main, and there are no times to set beside the Mac's. What is left, on the Mac
with the agent image built: one queue run of a real merge with `queue_container = true` and one with `false`,
the suite times of both written here. Until then, the claims in points 3 and 4 hold only by construction and
in the stand-in Docker, not in a real container. Points 3 and 4 that only a real run settles:
- that `uv run` in /work builds nothing into the checkout;
- that the coverage report is made from a container's line files;
- that `demo_check` finds what it needs offline in the image. The pillow and numpy cache are in it (Dockerfile).

**The instance's stopgap is ready to delete** once this lands: `limits_for` in the instance's
`dev/bin/agents.py`, and `[agents] session_cpus`, `session_cpuset` and `suite_cpuset` in its
`factory.local.toml`. They are now defaults here, with the same values. The local keys would still override
them, so delete them to have one source.

**Choices made alone (the most reversible):**
- A command inside the container that exits 126 or 127 (for example `uv` missing) also counts as not started.
  A Docker CLI failure with any other code reads as a red suite, and triage's rerun in its own container then
  fails to start and raises.
- `sweep_box` runs only with `queue_container` on. A missing `docker` then fails the run (fail closed).
  Triage's containers left by a SIGKILL are swept by `agents.sweep` after 70 minutes, not at once (no lock lets
  only one triage run).
- Memory stays at LIMITS' 12 GB per container, so unit and browser at once ask 24 GB of Docker's VM. That size
  was not checked here.
- The test fixture (`tests/test_factory.py` `Factory`) sets `queue_container = false`. The new tests turn it
  on with a stand-in `docker` on PATH that runs the command in the mounted folder.
- `dev/README.md` is not updated (not in the files to touch). The queue's module docstring says it.

**Size:** 92 net lines in `dev/bin/` and `dev/factory.toml` (108 added, 16 removed).

**Tests** (in `tests/test_agents.py`):
- `test_each_queue_suite_runs_in_a_container_on_the_queue_cpuset_with_no_network`
- `test_with_queue_container_false_the_commands_are_todays`
- `test_a_container_that_cannot_start_fails_the_run_with_no_gap_blamed`
- `test_a_stopped_queue_run_leaves_no_container_behind` (SIGTERM, then SIGKILL and the next run)
- `test_sessions_gap_suites_and_queue_suites_get_their_own_cpusets`

Each was seen to fail on a break (lesson-9):
- the queue cpuset dropped: tests 1 and 5;
- the NotStarted raise removed: test 3;
- the sweep at a run's start removed: test 4;
- both kills by name removed: test 4;
- `queue_container = false` ignored: test 2.

**Runs here** (one file at a time; my runs under `scripts/suite_watch.py` were refused):
- `tests/test_agents.py`: 9 passed.
- `tests/test_factory.py` (`-n 8`): 126 passed, 2 skipped. The skipped two are its tests that need Docker and the
  agent image (`docker_ready`).
- `tests/test_queue.py`: 5 passed.
- `tests/test_code_health_coverage.py`: 11 passed.
- `uv run ruff check ergostat tests scripts`: clean.

Not run here: the full unit suite, the four browser files, and `demo_check`. They are the queue's to run.
