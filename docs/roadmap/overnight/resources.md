# resources: the machine's CPU, memory and disk as the factory's binding constraint

depends-on: []

Branch `resources`, from main. Asked by the owner (2026-11-20): "our bottleneck will be computer resources, cpu and
memory and disk. we should start tracking our system resources in the factory, maybe that will be easier with docker
containers?" The pools are now three implementors and two reviewers on a large AI budget, so the machine (macOS, 28
cores, 256 GB, the Docker Desktop VM) is what binds, not money.

## Definition of done

The factory's model measures the machine and holds the sessions to what it fits:

- **Sensors** (`dev/bin/resources.py`, `dev/model/resources.yaml`, system `resources` under oversight): host CPU
  (load average, utilisation), memory (used, free, pressure, utilisation), disk free on the volumes holding
  `<live>` and Docker's data, Docker's own disk use (`docker system df`), the machine's thread total, the Docker VM's
  CPUs and memory (`docker info`) and the containers' use against them (`docker stats --no-stream`). One snapshot,
  taken under a lock and shared by every reading (at most one measurement per 25 s; Docker's disk and the factory's
  folders at most every 10 minutes), each command under a timeout. macOS (`sysctl`, `vm_stat`, `iostat`, `top`) and
  Linux (`/proc`) both.
- **Per session**: each factory container's CPU % and memory is sampled while it runs (from the snapshot) and kept
  as its peak and mean: on the gap item (`resources`, appended; the implementor's session and its suites, the
  reviewer's session) and in `run/resources/sessions.jsonl`.
- **Goals with setpoints**, written once in `dev/model/resources.yaml` and read from there by the program (as the
  daily cap is): CPU utilisation <= 0.8, memory utilisation <= 0.8, disk free >= 25 GB (the coordinator: this Mac has 36 GB free), Docker VM memory <= 0.85,
  the machine's threads <= 10,000, and the factory's own folders within their size.
- **Capacity headroom** (`session-headroom`): how many more sessions fit, the least over host CPU, host memory, VM
  CPU and VM memory of (setpoint x capacity - in use) / per-session use (the median measured peak of a session plus
  one of its suites; `[resources]` defaults until three are measured); 0 while disk or threads are past their goal.
- **The pool decision**: the effective pool is `min(risk target, busy + headroom)`. The risk target is the pool
  stock (`implementor-pool`, `reviewer-pool`: today the streak tuner's, tomorrow whatever `pool-control` sets);
  headroom is a separate cap on top of it, in the gates (`implement-when`, `review-when`: `busy < min(pool, busy +
  room)`, and closed while the headroom is stale or under one, the goal `sessions-fit` with `on-stale: off`) and in
  each run (`pools.my_turn`: the run's place among its block's leases must be under `min(pool, running + headroom)`).
  Neither can raise the other: resources only ever lower what risk allows.
- **Disk hygiene**: measures of `<live>/sessions` and of the installs other than current and previous; a goal on
  them; a program (`dev/bin/cleanup.py`, block `disk-cleanup`) that removes session folders older than
  `[resources] session_keep_hours` and installs other than current, previous and those younger than the same age,
  deleting only names the factory makes (`<branch>-<role>-<14 digits>-<6 hex>`, a 40-hex sha that is a worktree of
  the checkout), never anything else.
- `dev/bin/status.py` prints a resources line.

## Acceptance tests

- `tests/test_factory_resources.py::test_macos_readings_parse`: `sysctl`, `vm_stat`, `iostat` and `top` fixtures give
  CPU, memory, pressure and threads.
- `tests/test_factory_resources.py::test_linux_readings_parse`: `/proc/stat`, `/proc/meminfo`, `/proc/loadavg` and
  `/proc/pressure/memory` fixtures.
- `tests/test_factory_resources.py::test_docker_outputs_parse`: `docker stats`, `docker info` and `docker system df`
  fixtures; only `ergostat-factory-*` containers are the factory's.
- `tests/test_factory_resources.py::test_headroom`: the least resource binds; disk or threads past their goal give 0;
  measured sessions replace the defaults.
- `tests/test_factory_resources.py::test_gates_respect_headroom`: the model's `implement-when` and `review-when` exprs
  close at headroom 0 and when stale, and never open past the pool however large the headroom.
- `tests/test_factory_resources.py::test_my_turn_respects_headroom`.
- `tests/test_factory_resources.py::test_cleanup_deletes_only_the_factorys_folders`: old session folders and old
  installs go; current, previous, young ones, and every other name (files, symlinks, a lookalike, a non-worktree sha
  folder) stay.
- `tests/test_factory.py::test_the_factory_model_loads` with the new goals and blocks.

## Size budget

350 net lines of code outside `tests/` and `docs/` (all of it is in `dev/`).

**Over budget, with the reason:** it came to about 640 net lines, all in `dev/` (none of ergostat's core:
`fac.net_lines` counts 0). About 170 are the model (`dev/model/resources.yaml`: nineteen sensed auxiliaries, seven
goals and three blocks, five lines each, the owner having named each reading), about 120 the cleanup (its name
checks are the safety), and about 320 the sensors, parsers for two platforms and Docker, the shared snapshot, the
per-session sampling and the headroom. Nothing in it is optional to what was asked; cutting further would mean fewer
of the readings the owner listed.
