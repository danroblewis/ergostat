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
