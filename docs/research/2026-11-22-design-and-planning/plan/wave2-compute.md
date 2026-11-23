# Wave 2: compute systems, as buildable gaps (2026-11-22)

Source: `docs/proposals/compute-systems.md` (landed tonight, `gap/compute-systems-proposal` merged), its section 7
milestone of 11 gaps. Read against current main. Every milestone gap but `compute-runner-interface`,
`compute-run-spec`, `compute-secrets` and `compute-calls-from-node` is over the ~300-line budget as written, so the
worker (milestone 3) splits into five, the pools (milestone 4) into four, and the work in/out (7) into two. 21 gaps.

## What the code says (checked, file:line on current main)

- `Engine._ran` is `ergostat/spec/engine.py:981-1184`; the local process path is `engine.py:1060-1110`
  (`runrecord.files`, `Measured`, `runrecord.write`, `old.LIVE`, `self.procs`, `self.live`, `SAMPLER.track`,
  `reap.Watch`, `stream.follow`, `runrecord.remove`, `SAMPLER.finish`). The environment is `{**os.environ, ...}`
  at `engine.py:995-997`.
- Processes are reached outside `_ran` in four places, all of which the interface must take: `stop_run`
  (`engine.py:1855-1865`, `self.procs`), `close` (`engine.py:1985-2001`, `old.kill_all` or `self.live`),
  the lease kill (`ergostat/leases/kill.py:39-62`, `eng.live`, `proc.watch`), and `old.LIVE`/`kill_all`
  (`ergostat/runner.py:38-59`).
- Daemon runs (`engine.py:1046-1051`) do not go through the run files; the proposal keeps daemons engine-local, so
  the interface leaves that branch alone.
- The proposal's SPEC citation `docs/SPEC.md:2201` has drifted: the sentence "Taking up a run left behind by a
  stopped engine is not built yet" is now `docs/SPEC.md:2379-2380`.
- Built-in pool measures to mirror: `WORKSPACES`/`WORKSPACES_MEASURES` (`ergostat/spec/ir.py:205-212`), read in
  `ergostat/numbers/measures.py:180`, listed at `measures.py:190` and `:201`, recognised at `ir.py:308`.
- A top-level section compiled by its own module: `ergostat/workspaces/compile.py:15-41`, called from
  `ergostat/spec/compile.py:1066-1068`. Machine block keys: `compile.py:86-92`.
- Dispatcher room: `ergostat/leases/dispatch.py:193-203` (daemon cap at `:197-198`); take and fence
  `dispatch.py:253-315`; watchdog look/expire/activity `dispatch.py:458-525`.
- A refused start given back uncounted: `outcome["nack"] = {..., "after": POOL_FULL_AFTER, "count": False}`
  (`engine.py:1170-1171`, `POOL_FULL_AFTER` at `engine.py:59`).
- CLI topics register in `ergostat/cli/__init__.py:356-369` (e.g. `cli/remote.py:19-30`).
- The call socket: `engine.py:1817-1819` (`_listen`), `ERGOSTAT_SOCKET` at `engine.py:1005-1008`; `ergostat/calls/`.
- Demo check: `scripts/demo_check.py`; a demo with its own test: `examples/remote-pair/`, `tests/test_remote_pair.py`.

## Overlaps with filed gaps

- `gap/rs-adopt-continued` (parked): "A starting engine adopts the runs still alive". That is the local half of
  milestone gap 6. It is **not** re-proposed. Milestone gap 6 is split: `compute-reattach` (a session to a node cut
  and reconnected within one engine process: needs no adoption) and `compute-adopt-node-runs` (an engine restarted
  takes up its node runs), which depends on `rs-adopt-continued`. Recommendation for the groomer: when
  `rs-adopt-continued` is resumed, add `compute-runner-interface` to its `depends-on` and build the adoption on the
  handle (`alive`, `follow` from an offset), so one mechanism serves both, as the proposal asks.
- `gap/shard-supervisor` (ready) touches `ergostat/runner.py`'s process supervision, not run processes; no overlap,
  but `compute-runner-interface` edits `runner.py:38-59` (`LIVE`, `kill_all`): merge origin/main before review.
- Nothing else filed is about compute, workers, nodes or SSH.

## The graph

```
wave A (no deps):     compute-runner-interface   compute-pools-config   compute-worker-protocol
wave B:               compute-run-spec(<-iface)  compute-worker-keeper(<-protocol)
                      compute-node-connection(<-pools-config, protocol)
wave C:               compute-worker-output, compute-worker-readings, compute-worker-restart-states,
                      compute-worker-lease-clock (each <-keeper);  compute-capacity-measures(<-connection)
wave D:               compute-remote-backend(<-iface, run-spec, connection, worker-output)
                      compute-docker-backend(<-keeper, readings)
wave E:               compute-lease-renew-on-node(<-remote-backend, lease-clock)
                      compute-reattach(<-remote-backend, restart-states)
                      compute-secrets, compute-work-in, compute-calls-from-node (each <-remote-backend)
wave F:               compute-work-out(<-work-in)  compute-adopt-node-runs(<-reattach, rs-adopt-continued)
                      compute-demo(<-capacity-measures, lease-renew-on-node, reattach)
```

Width: 3 at once in wave A, 3 in B, 5 in C, 2 in D, 5 in E.

## Risks the implementors must be told

- The worker is one standard-library module that runs on its own (`python3 -I worker.py --stdio`): no
  `from ..` imports in `ergostat/compute/worker.py`. Gaps 4-9 and the docker gap all edit it; they are serialised by
  `depends-on` through `compute-worker-keeper`, then four run in parallel on one file: each keeps to its own
  functions and merges origin/main before review. If the file passes ~900 lines, the keeper may move to
  `ergostat/compute/keeper.py` loaded by path, still standard library only.
- Linux-only parts (`CLOCK_BOOTTIME`, `PR_SET_PDEATHSIG`, `/proc`, cgroups) need tested fallbacks on macOS
  (`time.CLOCK_MONOTONIC`, which on Darwin counts sleep: the implementor checks this; no death signal; `ps`). The
  factory's sessions and merge queue run in Linux containers; the owner's Mac runs the unit suite too.
- Load-test safety (the Mac has kernel-panicked): worker tests cap runs per test (at most 8 processes) and every
  started process is killed in a fixture's teardown.
- The fence (`engine.py:2061-2085`) and the watchdog (`dispatch.py:458-504`) are never changed by these gaps; a node
  adds a second stop only.
- Docker tests skip when `docker` is absent (`shutil.which`), as the factory's container tests do.

## The gaps

### compute-runner-interface (incremental)

A runner interface in the core, its first backend today's local runs

depends-on: []

Problem. A machine block's run reaches its process directly in five places, so nothing but this machine can execute one (docs/proposals/compute-systems.md section 1, milestone gap 1). `Engine._ran` starts it inline (ergostat/spec/engine.py:1060-1110: runrecord.files, Measured, runrecord.write, old.LIVE, self.procs, self.live, SAMPLER.track, reap.Watch, stream.follow, runrecord.remove, SAMPLER.finish); `stop_run` kills `self.procs[name]` (engine.py:1855-1865); `close` calls `old.kill_all` or kills `self.live` (engine.py:1985-2001); the lease kill looks the run up in `eng.live` and reads `proc.watch` (ergostat/leases/kill.py:39-62); `runner.LIVE`/`kill_all` hold every run (ergostat/runner.py:38-59).

Change. New `ergostat/compute/__init__.py` and `ergostat/compute/runner.py`: a `Runner` protocol with `start(spec) -> Handle`, `follow(handle, take, timeout, offset=0) -> bool` (timed out; the offset taken kept on the handle), `alive(handle)`, `kill(handle, why, grace) -> bool`, `resources(handle) -> dict | None`, `cleanup(handle)`, and `local`, a backend that is today's code moved behind it unchanged (the wrapper and run files, Measured, the sampler, stream.follow, reap.Watch, registration in runner.LIVE). `_ran`, `stop_run`, `close` and `leases/kill.py` reach runs only through handles (`self.live` maps run id to a Handle; `kill.py` calls `handle`'s stop with the grace, recording `ergostat.run.killed` exactly as now). `runner(spec, block)` returns the backend for a block: always `local` in this gap. Daemon runs (engine.py:1046-1051) stay as they are. No behaviour changes.

Definition of done.
1. `ergostat/compute/runner.py` defines the protocol and the `local` backend; `_ran` holds no `Measured`, `runrecord` or `stream` call of its own.
2. `stop_run`, `close` and `leases/kill.py` reach a run through its handle; `eng.live` holds handles.
3. The records a run writes (agent.started, agent.ran/failed with exit, note, resources; ergostat.run.killed with signal and pids) are byte-for-byte the same shape as before.
4. The unit suite and the four browser files pass unchanged; no test is edited except imports.
5. SPEC §9.1 names the interface in one paragraph.

Files: ergostat/compute/__init__.py (new), ergostat/compute/runner.py (new), ergostat/spec/engine.py, ergostat/leases/kill.py, ergostat/runner.py (only if LIVE registration moves), tests/test_compute_runner.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_runner.py::test_ran_reaches_processes_only_through_the_runner: a monkeypatched backend records every start, follow, kill and cleanup of a program block's run; `subprocess.Popen` patched to raise inside `_ran` is never called.
- ::test_lease_kill_goes_through_the_handle: an expired lease's kill calls the backend's kill with the grace and records ergostat.run.killed with the same fields as tests/test_lease_kill.py expects.
- ::test_stop_run_and_close_kill_through_handles.
- tests/test_lease_kill.py, tests/test_streamed_output.py, tests/test_sampler_ramp.py pass unchanged.

Size budget: 250 net lines outside tests/ and docs/ (mostly moved; net near zero in engine.py).

### compute-run-spec (incremental)

A run as one JSON-able spec handed to its runner

depends-on: ['compute-runner-interface']

Problem. What a run is (command, input, cwd, environment, limits) is spread over local variables of `_ran` (ergostat/spec/engine.py:1002-1059): `cmd, stdin = self.program(...)` (engine.py:1002, 1041), `env = {**os.environ, ...}` (engine.py:995-1027), `cwd` (engine.py:1046), `b.timeout`. A backend on another machine can take none of it, and the engine's whole environment (every secret it was started with) is in each run's (docs/proposals/compute-systems.md section 1 and 2.6, milestone gap 2).

Change. `ergostat/compute/spec.py`: a `RunSpec` dataclass with `to_json()`/`from_json()`: run id, block, block type, command, input, cwd, `env` (only the `ERGOSTAT_*` variables `_ran` sets today), `secrets` (names only), `limits` (`wall` from the block's timeout; cpus, memory, pids, disk, network, log: None unless given), `work` (repo name and commit, None by default), `out` (bundle, artifacts, transcripts; empty by default), `lease` (fence, ttl, expires). `_ran` builds one and passes it to `runner.start`. The `local` backend still runs with `{**os.environ, **spec.env}` (today's behaviour, said in a comment); `RunSpec.allowlisted_env()` returns `PATH`, `HOME`, `LANG`, the `ERGOSTAT_*` variables and the secrets named, which later backends use. Run ids are checked against `^[0-9a-f]{32}$` for any backend but local.

Definition of done.
1. `_ran` builds exactly one RunSpec per run and hands it to the runner; the local backend's process sees the same environment, input, cwd and command as before.
2. A RunSpec round-trips through JSON unchanged for every machine block type that runs a process (program and ai; a leased run, an event-started run, a commanded run).
3. `allowlisted_env()` never contains a variable of the engine's own environment beyond PATH, HOME and LANG.
4. No secret value is a field of RunSpec (names only).

Files: ergostat/compute/spec.py (new), ergostat/compute/runner.py, ergostat/spec/engine.py, tests/test_compute_spec.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_spec.py::test_spec_of_each_block_type_round_trips.
- ::test_local_run_environment_unchanged: a program block printing `env` sees the same variables before and after (an engine variable set in the test included).
- ::test_allowlist_holds_no_engine_variable: an `ENGINE_ONLY=x` in os.environ is absent from `allowlisted_env()`.
- ::test_leased_spec_carries_fence_ttl_expires.

Size budget: 180 net lines.

### compute-pools-config (incremental)

compute: and runs-on: in the model, with their check findings and ceilings

depends-on: []

Problem. A model cannot say where a block's runs execute: there is no `compute:` section and no `runs-on:` key (machine keys are ergostat/spec/compile.py:86-92; top-level sections such as `workspaces:` are compiled by their own module, ergostat/workspaces/compile.py:15-41, called at compile.py:1066-1068). The proposal's model (docs/proposals/compute-systems.md section 4) and ceilings (sections 2.7, 3) need a home and a `check`.

Change. `ergostat/compute/compile.py`, called from the spec compiler beside `workspaces`: `compute:` pools (`nodes: [{ssh: HOST} | {connect: [argv]}]`, `backend: process|docker`, `image`, `slots`, `limits: {cpus, memory, pids, disk, wall, network, log}` with sizes like `4g` and durations like `30m`, `repos: {name: path}`, `secrets: {NAME: file}`, `labels`) into a `ComputePool` in the IR (ergostat/spec/ir.py beside `WorkspacePool`, ir.py:503); `runs-on: POOL|local` on machine blocks into `Block.runs_on` (ir.py:695-725, default None = local). Errors, each with where it was written: unknown pool; unknown key; a bad size or duration; nodes over 64; slots over 64; the sum over pools of nodes x slots over 256; wall over a day; log over 1 GiB; `network: none` on the process backend; `docker` without `image`; a `runs-on` block that is a daemon, a sensor, an `ai` block (later), or whose command names `ERGOSTAT_CMD`, `ERGOSTAT_SOCKET` or `ergostat ` (calls from a node are a later gap); a pool used by blocks of two shards (SPEC §9.8, dispatch.py:96-100); a node entry naming an address or a user (`@` in `ssh:`; a host must be a name in the owner's ssh config). Nothing runs differently yet: the engine ignores `runs_on` until compute-remote-backend.

Definition of done.
1. A model with `compute:` and `runs-on:` compiles; the IR holds the pools and each block's `runs_on`.
2. Each refusal above is an error with its code and place.
3. A model without `compute:` compiles to an identical IR (no new fields set).
4. SPEC gains a `compute:` subsection in the model reference (section 4 of the proposal, trimmed), and `runs-on` in the machine block keys.

Files: ergostat/compute/compile.py (new), ergostat/spec/compile.py, ergostat/spec/ir.py, tests/test_compute_compile.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_compile.py::test_pool_and_runs_on_compile.
- ::test_each_ceiling_refused (parametrised over every limit above).
- ::test_network_none_on_process_refused, ::test_runs_on_unknown_pool_refused, ::test_runs_on_ai_or_daemon_refused, ::test_runs_on_using_calls_refused, ::test_pool_across_shards_refused, ::test_ssh_with_user_refused.
- ::test_no_compute_section_ir_unchanged.

Size budget: 260 net lines.

### compute-worker-protocol (incremental)

ergostat worker --stdio: the protocol's frame, hello, beat and ping

depends-on: []

Problem. Nothing on another machine can speak to the engine: there is no `ergostat worker` (ergostat/cli/__init__.py:356-369 lists every topic) and no protocol (docs/proposals/compute-systems.md sections 2, 2.1, 3; milestone gap 3, split here: this gap is the frame and registration only).

Change. `ergostat/compute/worker.py`, standard library only and with no package-relative imports, so `python3 -I worker.py --stdio` runs it with no ergostat installed; `ergostat worker --stdio [--root DIR]` (new `ergostat/cli/worker.py`, registered in cli/__init__.py) calls the same `main`. It reads one JSON object a line on stdin and writes one a line on stdout, diagnostics to stderr. Every line has `v` (1), `seq` (per direction from 1) and `type`, at most 1 MiB (a longer one answered `error` and the session ended); requests carry `id`, answers repeat it. First line `hello`: `node` (a random 32-hex id made once and kept in the root, never a host name, address or user), `cpus`, `memory`, `disk.root`, `arch`, `os`, `backends` (['process']), `images` ([]), `labels` (from `labels.json` in the root), `slots` (its config `slots.json`, at most its CPUs, at most 64), `runs` ([] until compute-worker-restart-states). `beat` every 10 s with slots free and disk free; `ping` answered `pong` at once; a line of another `v` answered `error` then exit; an unknown `type` answered `error` without ending. The root defaults to `~/.local/state/ergostat-worker/` and the worker writes nowhere else. A tiny test helper `tests/compute_pipe.py` starts the worker over a pipe and reads its lines.

Definition of done.
1. `python3 -I ergostat/compute/worker.py --stdio --root R` and `ergostat worker --stdio --root R` both answer `hello` then `pong` to a `ping`.
2. The node id persists across restarts and matches `^[0-9a-f]{32}$`.
3. `seq` increases by one on every line out; a gap in the engine's seq is said on stderr.
4. An over-long line, a wrong `v` and an unknown type are each answered as above.
5. Nothing is written outside the root (a test lists the filesystem diff under a temporary HOME).
6. SPEC gains a short *Compute systems* section naming the worker and protocol v1.

Files: ergostat/compute/worker.py (new), ergostat/cli/worker.py (new), ergostat/cli/__init__.py, tests/compute_pipe.py (new), tests/test_compute_worker_protocol.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_worker_protocol.py::test_hello_then_pong_standalone (run with `python3 -I`, no PYTHONPATH).
- ::test_node_id_kept, ::test_beat_every_interval (interval shortened by a hidden flag), ::test_wrong_version_ends, ::test_overlong_line_ends, ::test_unknown_type_answered, ::test_writes_only_under_root.

Size budget: 220 net lines.

### compute-worker-keeper (incremental)

The worker starts a run under its keeper, which holds its deadlines

depends-on: ['compute-worker-protocol']

Problem. A run started by an SSH-launched worker would die with the session or outlive every deadline: a local run's wrapper only writes the exit (ergostat/spec/runrecord.py:22-30) and holds no timeout (the timeout lives in the engine's follower, ergostat/spec/stream.py:36-38). The proposal puts the deadlines in a detached per-run keeper (docs/proposals/compute-systems.md sections 2.2 process backend, 2.4, 2.7 wall timeout; milestone gap 3).

Change. In ergostat/compute/worker.py: `start` (run id checked `^[0-9a-f]{32}$`, else `refused bad name`; `full` past slots; `limits over the node`) makes `runs/RUN/` in the root with `run.json` (run id, block, lease fence, backend, limits, wall deadline, keeper pid and start time), `in`, an empty folder as cwd, the first `deadline` file, then starts the keeper `python3 -I worker.py --keep RUN --root R` detached (setsid, stdin /dev/null, output to runs/RUN/keeper.log, SIGHUP ignored) and answers `started` with the pid and its start time, or `refused no keeper`. The keeper forks the run: own process group, `pgid` file written before exec, setrlimit RLIMIT_AS/RLIMIT_NPROC (and RLIMIT_CPU at cpus x wall), on Linux PR_SET_PDEATHSIG=SIGKILL by ctypes and a raised oom_score_adj; it execs `/bin/sh -c COMMAND` with the given env, stdout/stderr to runs/RUN/out and runs/RUN/err. It holds the wall deadline (start + limits.wall, never moved) and the lease deadline read from `runs/RUN/deadline` every quarter second (an unreadable or unparsable file keeps the last value), both on CLOCK_BOOTTIME (Linux) or the platform's suspend-counting monotonic clock elsewhere; at the earlier one, or when `runs/RUN/stop` appears (with its grace), SIGTERM to the group, SIGKILL K seconds later (K from the stop file or grace(ttl)/4), and writes `exit` with the code and how (`exit`, `TERM`, `KILL`, `wall`, `lease`). After the end it waits for `runs/RUN/done` or a day (a hidden `--day SECONDS` for tests), removes its run folder by name after resolving it under the root, and exits. `kill` from the engine writes the stop file. `ended` is sent when the exit file appears (resources and output come in later gaps).

Definition of done.
1. A run started over the pipe executes, writes out/err/exit, and the worker answers `started` then `ended` with its exit code.
2. Closing the worker's stdin mid-run leaves the run going; its keeper kills it at its wall time and removes its folder after the (shortened) day.
3. SIGKILL of the keeper on Linux kills the run's first process (death signal); the test is skipped elsewhere.
4. A garbage deadline file never moves the kill later.
5. `kill` with a grace ends the run with SIGTERM, and with SIGKILL if it ignores TERM.
6. A bad run id, a full node and limits over the node are refused, and nothing is made for them.

Files: ergostat/compute/worker.py, tests/test_compute_keeper.py (new), docs/SPEC.md.

Acceptance tests (at most 8 processes per test, all killed in teardown).
- tests/test_compute_keeper.py::test_run_exits_and_reports, ::test_stdin_closed_run_goes_on_then_wall_kill, ::test_folder_removed_after_day, ::test_keeper_killed_death_signal (Linux), ::test_bad_deadline_file_keeps_last, ::test_kill_term_then_kill, ::test_refusals_make_nothing.

Size budget: 300 net lines.

### compute-worker-output (incremental)

A node run's output sent by offset, resumed by attach, capped

depends-on: ['compute-worker-keeper']

Problem. The engine records a run's lines as it reads them from a file it follows (ergostat/spec/stream.py:27-62); over a session that can be cut, lines must be addressable so a resend is recorded once (docs/proposals/compute-systems.md section 2.3; ordering by offset, never time, the review lessons' lesson-2).

Change. In ergostat/compute/worker.py: a follower over each running run's `out` and `err` sends `out {run, stream, offset, text}` (offset of the first byte; at most 64 KiB a line, split at a line end where possible, else at the limit; whole lines only until the run ends). `attach {run, out, err}` resends from those offsets; `beat` carries each run's offsets taken (from the engine's last attach/ack). Flow control: at most 4 MiB sent ahead of the engine's acknowledged offsets, across runs, so a slow engine slows sending, never the worker's memory. A file past `limits.log` (default 64 MiB, at most 1 GiB) stops its run through the stop file with how `log over its cap`. `ended` comes after the last `out` of that run. `done {run}` writes runs/RUN/done. On the engine side (test helper only in this gap) the rule a line below the taken offset is dropped is shown in tests/compute_pipe.py; the engine's own use comes with compute-remote-backend.

Definition of done.
1. A run printing 10,000 lines yields offsets that cover out and err exactly once each, in order.
2. An attach from a middle offset resends from there; lines below it are not resent.
3. A line longer than 64 KiB arrives split, rejoined exactly by offset.
4. With the reader stalled, the worker holds at most 4 MiB unacknowledged and its RSS stays bounded (measured).
5. A run over its log cap is stopped and ended with that how.

Files: ergostat/compute/worker.py, tests/compute_pipe.py, tests/test_compute_output.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_output.py::test_lines_by_offset_once, ::test_attach_resumes_from_offset, ::test_long_line_split, ::test_backpressure_window, ::test_log_cap_stops_run, ::test_ended_after_last_out.

Size budget: 220 net lines.

### compute-worker-readings (quick)

Per-run CPU and memory on the node, in beats and at the end

depends-on: ['compute-worker-keeper']

Problem. A local run's CPU and memory come from the shared sampler and the wait status (ergostat/costs/sampler.py:1-24, engine.py:1082-1089) and are written on agent.ran/agent.failed as `resources`. A node run has neither (docs/proposals/compute-systems.md section 2.8).

Change. In ergostat/compute/worker.py (standard library only; the sampler module cannot be imported, so a small tree sampler is written for the worker): each process-backend run's tree (its process group and descendants by parent), from /proc on Linux, one `ps -A -o pid=,ppid=,pgid=,rss=,utime=,stime=` elsewhere, sampled once a second for the first ten seconds then every ten; per run the CPU seconds, peak resident memory and peak process count. The latest per run is in each `beat`; the whole is in `ended.resources` with the same keys a local run's `resources` carries (cpu, memory_peak, processes_peak as named in sampler.Sampler.finish, sampler.py:235). One sampling thread for all runs. Readings are measurements: nothing here becomes an event.

Definition of done.
1. A run that burns CPU for 2 s reports at least 1.5 CPU seconds in `ended.resources`.
2. A run that allocates 100 MB reports a peak at least that.
3. The keys of `ended.resources` equal those of a local run's resources.
4. One thread samples every run (a test counts threads with 4 runs going).

Files: ergostat/compute/worker.py, tests/test_compute_readings.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_readings.py::test_cpu_seconds_reported, ::test_memory_peak_reported, ::test_resource_keys_match_local, ::test_one_sampling_thread.

Size budget: 150 net lines.

### compute-worker-restart-states (incremental)

A starting worker lists its runs as running, gone or unknown, and sweeps by name

depends-on: ['compute-worker-keeper']

Problem. A worker started again on a node must say which runs it still holds and what became of them, and must never call a run gone on a reading it did not make (docs/proposals/compute-systems.md sections 2.4 and 2.9; lesson-3 and lesson-6 on failed readings; lesson-11 deletes by allowlist). Today's local record decides `alive` by pid and start time only (ergostat/spec/runrecord.py:75-80) and reads an unread start time as gone.

Change. In ergostat/compute/worker.py: at start, read every `runs/RUN/` folder whose name matches `^[0-9a-f]{32}$`; each run is `running` (its pid alive with the recorded start time, or its container running with the id recorded, once docker exists), `gone` only on an allowlisted reading (the exit file written; or the pid absent or with another start time and its process group read as empty), else `unknown` (record unreadable, start time not read, `ps` failed or timed out, group not read, run alive but keeper gone). `hello.runs` lists them with their state; `beat` carries each state. For `unknown`, the worker at once stops the run by name itself (SIGTERM then SIGKILL to the group in runs/RUN/pgid) and keeps listing it unknown until a reading moves it. A keeper gone with its run ended: the worker writes the exit's want and does the keeper's cleanup. A sweep at start and hourly removes only run folders of that name form under its root, each resolved and checked to be inside the root before deletion, and only when `done` exists or a day has passed since the run's end; it never deletes all-but-a-list.

Definition of done.
1. A run left running by a killed worker is listed `running` by the next.
2. A run whose exit file exists is `gone` with its exit.
3. A `ps` that fails (patched) gives `unknown`, never `gone`; the worker then signals the recorded group.
4. A reused pid (another start time) with the group empty gives `gone`; with the group not empty gives `unknown` and the group stopped.
5. The sweep leaves a folder named otherwise, a symlink pointing out of the root, and a folder of an un-done run younger than a day.

Files: ergostat/compute/worker.py, tests/test_compute_restart_states.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_restart_states.py::test_running_after_worker_restart, ::test_gone_on_exit_file, ::test_ps_failure_is_unknown_and_stopped, ::test_reused_pid_group_empty_gone, ::test_reused_pid_group_alive_unknown, ::test_sweep_deletes_only_its_own_names.

Size budget: 200 net lines.

### compute-worker-lease-clock (quick)

The worker turns the engine's lease renewals into its keeper's deadline, on its own clock

depends-on: ['compute-worker-keeper']

Problem. A keeper must kill a run whose lease the engine stopped renewing, by the engine's expiry, without ever comparing a time of the engine's with one of its own (docs/proposals/compute-systems.md section 2.7, *How the worker times it*; lesson-2). compute-worker-keeper reads `runs/RUN/deadline` but only its first value is written.

Change. In ergostat/compute/worker.py: each message from the engine that carries `sent` (start's lease, `renew {run, fence, left, sent}`, ping) gives `heard - sent` (heard on the worker's suspend-counting clock); `base` is the least of those over the last ten minutes. A run's lease deadline is `sent + base + left` of the latest renewal heard for its fence, converted to the keeper's clock and written to runs/RUN/deadline by temporary file and os.replace. A renewal of an older fence is ignored; a later renewal of the same fence may move the deadline either way, since the engine's `left` is authoritative. Only a renewal heard writes the file; a cut session writes nothing. K = grace(ttl)/4 with grace(ttl) = max(1, min(0.1 x ttl, 30)) (ergostat/leases/terms.py:38-41) is written beside the deadline for the keeper's SIGKILL.

Definition of done.
1. With renewals arriving at random delays (0-500 ms, patched clock), the deadline written is never later than the engine's expiry plus the least delay seen.
2. A worker whose clock of day is set an hour off (time.time patched) writes the same deadline.
3. A renewal delayed in the pipe does not move the deadline later than a prompt one would.
4. A renewal for an older fence is ignored.
5. No renewal after a cut session: the keeper kills by the last deadline plus K.

Files: ergostat/compute/worker.py, tests/test_compute_lease_clock.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_lease_clock.py::test_deadline_never_later_than_expiry_plus_dmin, ::test_clock_of_day_offset_irrelevant, ::test_delayed_renewal_does_not_extend, ::test_old_fence_ignored, ::test_cut_session_keeper_kills_by_deadline.

Size budget: 120 net lines.

### compute-node-connection (incremental)

The engine's connection to each node of a pool: session, hello, beats, loss, round trips

depends-on: ['compute-pools-config', 'compute-worker-protocol']

Problem. The engine has no way to reach a worker (docs/proposals/compute-systems.md sections 2.1, 3, milestone gap 4). Remote systems use HTTP (ergostat/remote/); compute uses JSON lines over `ssh -T -o BatchMode=yes HOST ergostat worker --stdio`, or a pool's `connect:` argv.

Change. `ergostat/compute/connection.py`: one `Node` per entry of each pool the model declares (named `POOL/N`, by its place in the list, never by host), started by the engine when it starts and closed on close/swap: a subprocess with stdin/stdout pipes, one reader thread per node, the stderr kept in the pool's log under the state folder. It parses `hello` (version 1 only, else `error` said in the pool's status and nothing started there; labels must include the pool's `labels:`, else the node is not used), counts beats, and marks the node **lost** after three beats missed (30 s) or EOF, whichever first; reconnects with backoff from 1 s doubling to ten minutes. It sends `ping` every 2 s and keeps round trips on its own monotonic clock; `least_rtt(window=60)` is exposed. `request(msg) -> reply` with ids and a timeout; `on(type, fn)` for unsolicited lines (out, beat, ended). Per pool a `status()` dict (nodes in service, lost, slots, free, last error) is put in the engine's heartbeat and in `/api/status` under `compute` (ergostat/web/server.py:447-455), only when the model has pools. At most 64 nodes over all pools (compute-pools-config refuses more).

Definition of done.
1. A pool with `connect: [python3, -I, .../worker.py, --stdio, --root, R]` comes up: its node is in service with the worker's slots.
2. Killing the worker marks the node lost at EOF; a worker that stops beating (SIGSTOP) is lost after three missed beats.
3. A lost node is retried with backoff and comes back in service when the worker returns.
4. A worker answering another `v` leaves the pool's status with the error and no node in service.
5. `/api/status` shows `compute` only for a model with pools; a model without is unchanged.
6. No host name, address or user appears in status, logs or events (a node is POOL/N).

Files: ergostat/compute/connection.py (new), ergostat/spec/engine.py (start/close the pools), ergostat/web/server.py, tests/test_compute_connection.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_connection.py::test_node_in_service, ::test_lost_on_eof, ::test_lost_after_three_missed_beats (beat interval shortened), ::test_backoff_and_return, ::test_unknown_version_in_status, ::test_status_only_with_pools, ::test_round_trips_measured.

Size budget: 280 net lines.

### compute-capacity-measures (incremental)

A pool's slots as built-in measures, and the dispatcher's room capped by them

depends-on: ['compute-node-connection']

Problem. A pool's capacity must read like any stock so a controller can hold a queue against it, and the dispatcher must stop sending to a pool whose slots are gone (docs/proposals/compute-systems.md section 4, *Compute capacity as a stock*; section 3's engine-wide 256). The workspace pools are the pattern: `WORKSPACES`/`WORKSPACES_MEASURES` (ergostat/spec/ir.py:205-212), read in ergostat/numbers/measures.py:180, listed at measures.py:190 and :201, recognised at ir.py:308. A block's room is its pool less its runs (ergostat/leases/dispatch.py:193-203), a daemon's capped by its free room (dispatch.py:197-198).

Change. `COMPUTE = ^ergostat\.compute\.(slots|free|busy|nodes|lost)(?:@POOL)?$` and `COMPUTE_MEASURES` in ir.py, read from the connections' status in measures.py, recognised as built-in names (so `pool: {now: stock.S}` and goals may read them). In `tick_block`, a block with `runs_on` gets `room = min(room, free slots of its pool - starts in flight to it)`, and globally at most 256 node runs held or draining (killed, not yet ended) before any start. A lost node's slots leave `slots`/`free` at once. No diagram changes: a model may declare a stock on these measures and it is drawn as any stock (invariant 12).

Definition of done.
1. Each measure reads the connections' numbers, per pool with `@POOL` and summed without.
2. A block on a pool with 2 free slots and pool 8 takes at most 2 items in a pass.
3. A node lost drops `slots@POOL` by its slots at the next reading, and no item is taken for it.
4. The 256 cap holds across two pools (patched counts).
5. A model without pools has no new measures and identical dispatch.

Files: ergostat/spec/ir.py, ergostat/numbers/measures.py, ergostat/leases/dispatch.py, ergostat/compute/connection.py, tests/test_compute_capacity.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_capacity.py::test_measures_per_pool_and_sum, ::test_room_capped_by_free_slots, ::test_lost_node_leaves_capacity, ::test_engine_wide_256_cap, ::test_no_pools_unchanged.

Size budget: 160 net lines.

### compute-remote-backend (incremental)

A block with runs-on runs on a pool's node through the runner interface

depends-on: ['compute-runner-interface', 'compute-run-spec', 'compute-node-connection', 'compute-worker-output']

Problem. With the interface, the spec, the connection and the worker's output in place, nothing yet joins them: `runner(spec, block)` returns `local` always (compute-runner-interface), and a `runs-on` block still runs here (docs/proposals/compute-systems.md milestone gap 4, acceptance).

Change. `ergostat/compute/remote.py`: a `remote` backend of the Runner protocol over a pool's connection. `start(spec)` picks a node in service with a free slot (fewest runs first), sends `start` with the RunSpec as JSON (the allowlisted environment, never the engine's), and returns a handle holding the node and run; `refused` raises a `Refused` the engine turns into `outcome["nack"] = {why, after: POOL_FULL_AFTER, count: False}` as a full workspace pool does (ergostat/spec/engine.py:1170-1171), so a misconfigured node costs no attempt, and the refusal is said in the pool's status. `follow` takes `out` lines for the run in offset order, drops any below the offset taken, hands complete lines to `take` exactly as stream.follow does, keeps the offset taken in the run's record under the state folder after each batch is recorded, sends acks, and returns at `ended` (exit code and how; how `wall` gives the note `stopped after its timeout of Ns`). `kill` sends `kill {run, why, grace}`; `alive` is the node's last beat for the run; `resources` is `ended.resources`; `cleanup` sends `done`. `runner()` returns it for a block whose `runs_on` names a pool. The run's note and exit are recorded by `_ran` unchanged.

Definition of done.
1. A program block with `runs-on: farm` over a same-machine worker (`connect:`) runs, and its agent.started/agent.ran records and its item's moves equal those of the same block run locally (ids and times aside).
2. Its lines are recorded once each even when the test forces a resend from an earlier offset.
3. A `start` refused (`full`, `no such image`) gives the item back uncounted and put off; the attempt count is unchanged.
4. A lease kill reaches the node run and records ergostat.run.killed with the signal the worker reports.
5. A block without `runs-on` is unchanged (the existing suites pass).

Files: ergostat/compute/remote.py (new), ergostat/compute/runner.py, ergostat/spec/engine.py (the Refused case only), tests/test_compute_remote_backend.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_remote_backend.py::test_runs_on_records_like_local, ::test_resent_lines_recorded_once, ::test_refused_start_uncounted, ::test_lease_kill_reaches_node_run, ::test_timeout_on_node_noted.

Size budget: 260 net lines.

### compute-lease-renew-on-node (incremental)

A node run's lease renewed by the same activity as a local run's, and killed on the node when it is not

depends-on: ['compute-remote-backend', 'compute-worker-lease-clock']

Problem. The watchdog renews a local run's lease by activity only at its look, after the expiry (ergostat/leases/dispatch.py:458, 470-476, activity at 506-525). A node's keeper kills at the expiry (compute-worker-lease-clock), so a node run kept alive only by activity the fold does not count would be killed before the watchdog renews it (docs/proposals/compute-systems.md section 2.7, *What renews a node run's lease, and when*, *What the engine checks*; milestone gap 5).

Change. In ergostat/compute/remote.py and ergostat/leases/dispatch.py: for each run on a node, the engine sends `renew {run, fence, left, sent}` at once after any move of the lease's expiry in the fold and every 2 s besides (`left` = expiry less now, `sent` = its monotonic clock, read together). On each 2 s tick while the lease has less than half its TTL left, it calls `activity()` for the lease as the watchdog does; activity later than the lease's `renewed` records the same `renewed` event the watchdog would (`seen: activity`, at the activity's time, dispatch.py:474-475), at most one a tick per run, and the renew carries the new expiry. Before sending `start`, the node's least round trip over the last minute must be at most grace(ttl)/4 for the block's TTL (ergostat/leases/terms.py:38-41), else the item goes back uncounted as `full`; a running node run whose node's round trips grow past it is killed by `kill`. The fence and the watchdog are unchanged.

Definition of done.
1. A session cut and its worker ended: the run's keeper has SIGKILLed it by the expiry plus grace(ttl)/2, before the watchdog expires the lease; the item goes back once; a line the run's node sends after reconnecting is refused by the fence.
2. A node run whose only activity is events it causes about another item (one every third of its TTL; no line, no event about its own item) outlives its TTL several times, is never killed by its keeper, and ends agent.ran with renewed events `seen: activity`, as the same block run locally does.
3. The same run falling silent is killed by its keeper and its lease expires, counted.
4. A node whose round trip is past the bound is sent no start; the item goes back uncounted.
5. Renewals recorded: at most one per run per tick, none without new activity.

Files: ergostat/compute/remote.py, ergostat/leases/dispatch.py, ergostat/compute/connection.py, tests/test_compute_lease_on_node.py (new), docs/SPEC.md.

Acceptance tests (TTL shortened to seconds).
- tests/test_compute_lease_on_node.py::test_cut_session_keeper_kills_before_watchdog, ::test_activity_on_other_item_keeps_node_run, ::test_silent_node_run_killed_and_expired, ::test_slow_node_sent_no_start, ::test_renewals_bounded, ::test_line_after_reconnect_refused_by_fence.

Size budget: 230 net lines.

### compute-reattach (incremental)

A cut session to a node is resumed: held runs attached from their offsets, others killed

depends-on: ['compute-remote-backend', 'compute-worker-restart-states']

Problem. When the SSH session to a node ends and comes back within one engine process, the runs on it keep going (compute-worker-keeper) but the engine's `follow` for each has lost its stream, and a run the engine no longer holds a lease for must never be left running on a node (docs/proposals/compute-systems.md section 2.4, last paragraph; milestone gap 6, the node half; the engine-restart half is compute-adopt-node-runs).

Change. In ergostat/compute/remote.py: on a node's `hello` after a reconnect, for each run listed: held by a lease of this engine (in `dispatch.mine`, fence matching) and `running` or `gone`, send `attach {run, out, err}` from the offsets in the run's record, and the waiting `follow` resumes, recording each line once and the end as usual; not held, send `kill` then `done` once ended; `unknown`, keep the lease, record no end, send no renewal, so the lease expires through the watchdog (ergostat/leases/dispatch.py:468-504) and the run ends agent.failed with the note `unknown on its node`. A run the engine follows that the hello does not list is ended with the note `lost on its node` only when its lease has expired (never released early on a reading not made, lesson-6).

Definition of done.
1. A session cut (connect process killed) mid-run and reconnected: every line is recorded exactly once and the run ends agent.ran with its exit.
2. A run listed by the node with no lease of ours is killed and its folder removed.
3. A run listed unknown keeps its lease until the watchdog expires it; it ends agent.failed `unknown on its node`; no renew is sent for it meanwhile.
4. A run missing from the hello is not ended before its lease's expiry.

Files: ergostat/compute/remote.py, ergostat/compute/connection.py, tests/test_compute_reattach.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_reattach.py::test_cut_and_reconnect_lines_once, ::test_unheld_run_killed, ::test_unknown_keeps_lease_until_expiry, ::test_missing_run_not_ended_early.

Size budget: 180 net lines.

### compute-adopt-node-runs (incremental)

An engine started again takes up the runs on nodes its record says it started

depends-on: ['compute-reattach', 'rs-adopt-continued']

Problem. After an engine restart no `_ran` thread waits for a run it had started, so nothing records that run's end; SPEC says taking up a run left behind by a stopped engine is not built (docs/SPEC.md:2379-2380; the proposal cites the old line 2201). `gap/rs-adopt-continued` (parked) builds that for local runs; node runs need the same, through the same mechanism (docs/proposals/compute-systems.md section 2.4 last paragraph, milestone gap 6).

Change. Extend whatever rs-adopt-continued lands (its adoption of a run found in the record with its lease held) to node runs: a node run's record (pool, node index, run id, fence, offsets taken; written by compute-remote-backend) is read at engine start; once the node's hello lists the run, the engine starts a follow thread for it through the remote backend's handle exactly as compute-reattach does, recording its lines from the offset taken and its end, its lease kept and renewed (compute-lease-renew-on-node). A run in the record whose node never comes back keeps its lease until the watchdog expires it. The record's end is written before the run's record file is released (the parked rs-adopt review's finding).

Definition of done.
1. An engine killed while a node run goes, and started again: the run's remaining lines are recorded once, its end is agent.ran, its item moves as a run that was never interrupted.
2. A node run whose node is gone at restart ends only when its lease expires, counted.
3. Local and node runs are adopted by one code path (one function the two backends' handles share).
4. SPEC 2379-2380's sentence is replaced by what is built.

Files: ergostat/compute/remote.py, the adoption module rs-adopt-continued adds (or ergostat/spec/engine.py), tests/test_compute_adopt.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_adopt.py::test_engine_restart_takes_up_node_run, ::test_node_gone_at_restart_lease_expires, ::test_one_adoption_path.

Size budget: 150 net lines.

### compute-secrets (quick)

A pool's secrets read from files, sent at start, never written by ergostat

depends-on: ['compute-remote-backend']

Problem. A local run inherits the engine's whole environment (ergostat/spec/engine.py:995), so every secret the engine was started with reaches every run, and nothing says a run needs one. A node run gets only the allowlisted environment (compute-run-spec), so it has no way to receive a secret (docs/proposals/compute-systems.md section 2.6; milestone gap 8).

Change. The pool's `secrets: {NAME: file}` (compiled by compute-pools-config) are read at each start by the remote backend (`~` expanded; an unreadable file refuses the start, said by name, item given back uncounted) and sent in `start.secrets`. The worker keeps them in memory only: the process backend adds them to the run's environment in the keeper's exec (passed to the keeper through an inherited pipe, never a file or argv); the docker backend (later) passes `-e NAME` with the value in the docker client's environment. The worker replaces each secret's exact value in forwarded lines with `[secret NAME]` (a second layer only). Records, events, run.json, beats and errors carry names only; agent.started gets `secrets: [names]`.

Definition of done.
1. After a run that prints nothing secret, the secret's value is in no file under the worker's root, the engine's state folder, the event record or any log (a test walks them all and greps for the value).
2. The run sees the secret in its environment; agent.started names it.
3. A run that prints the secret has the line recorded with `[secret NAME]`.
4. An unreadable secret file refuses the start, uncounted, with the name and not the path's contents.

Files: ergostat/compute/remote.py, ergostat/compute/worker.py, tests/test_compute_secrets.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_secrets.py::test_secret_never_written, ::test_secret_reaches_run_and_name_recorded, ::test_printed_secret_masked, ::test_unreadable_secret_refuses_start.

Size budget: 140 net lines.

### compute-work-in (incremental)

A node run starts in a worktree at an exact commit sent as a git bundle

depends-on: ['compute-remote-backend']

Problem. A node run has an empty folder: it cannot work on the model's repository (docs/proposals/compute-systems.md section 2.5, *In: an exact commit*; milestone gap 7, first half). Locally, workspace pools make worktrees (ergostat/workspaces/git.py:50-58).

Change. RunSpec.work = {repo, commit} (a name in the pool's `repos:`, and a commit id, never a branch), set when the block's item names a commit field or the block says `work: {repo, commit: FIELD}` (one key added in compute-pools-config's block keys here). The worker keeps one bare repository per name under its root (`repos/NAME.git`), answers `need {repo, commit, have: [newest commits]}` when it lacks the commit; the engine makes `git bundle create` of what is missing (`--not` the haves), sends it as `bundle` chunks of at most 1 MiB, at most 2 GiB in all, with size and SHA-256; the worker verifies, fetches it and makes the run's folder a detached worktree at that commit. Bare repositories are pruned by age and a disk cap (`--keep`).

Definition of done.
1. A run with work at commit C sees the tree at C (a test checks a file's content and `git rev-parse HEAD`).
2. A second run at a later commit sends only the missing commits (the bundle is smaller; checked).
3. A bundle with a wrong hash or over the cap is refused; the start is refused uncounted.
4. A branch name in place of a commit is refused at check or start.
5. Pruning removes only repositories under repos/ of the name form.

Files: ergostat/compute/worker.py, ergostat/compute/remote.py, ergostat/compute/spec.py, ergostat/compute/compile.py, tests/test_compute_work_in.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_work_in.py::test_run_at_exact_commit, ::test_incremental_bundle, ::test_bad_hash_refused, ::test_branch_refused, ::test_prune_by_name.

Size budget: 260 net lines.

### compute-work-out (incremental)

A node run's commits, artifacts and transcripts brought back, hashed, capped and fenced

depends-on: ['compute-work-in']

Problem. What a node run makes stays on the node and is removed with its folder (docs/proposals/compute-systems.md section 2.5, *Out*; milestone gap 7, second half). The factory's containers bring work out as a git bundle made with no network (dev/bin/agents.py:309-335), unreachable from a model.

Change. RunSpec.out = {bundle, artifacts: [globs], transcripts: [globs]} from the block's `out:` (key added here). When the run ends the worker makes a git bundle of the commits on top of the given commit, collects files matching the globs inside the run folder only (symlinks resolving outside refused, said), and sends each as `result` chunks with size and SHA-256, capped (bundle 256 MiB, artifacts 1 GiB, transcripts 64 MiB by default). The engine verifies each, fetches the bundle into a side ref `refs/ergostat/runs/RUN-FENCE` of the named repository (never a branch), and keeps the rest under `runs/RUN/` in the state folder; agent.ran carries their names, sizes and hashes. A result arriving after the run's lease ended is refused by the fence and said. `done` is sent only after the results are kept.

Definition of done.
1. A run that commits twice has its commits at the side ref, and no branch moved.
2. An artifact glob brings back the matching files byte-exact; a symlink out of the folder is refused and named.
3. Over a cap: refused, the run's end notes it.
4. A result after the lease ended is refused and recorded as refused.

Files: ergostat/compute/worker.py, ergostat/compute/remote.py, ergostat/compute/spec.py, ergostat/compute/compile.py, tests/test_compute_work_out.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_work_out.py::test_commits_at_side_ref, ::test_artifacts_byte_exact, ::test_symlink_out_refused, ::test_cap_refused, ::test_result_after_lease_refused.

Size budget: 260 net lines.

### compute-docker-backend (incremental)

The worker's Docker backend: a run in a named container under its limits

depends-on: ['compute-worker-keeper', 'compute-worker-readings']

Problem. The process backend cannot limit network or isolate files (docs/proposals/compute-systems.md section 2.2, *docker*; milestone gap 9). The factory already runs its sessions in containers with hard limits and `--init` (dev/bin/agents.py:53-54), secrets by name (agents.py:12-14, 145-155) and kill by name (agents.py:161-164), but only for itself.

Change. In ergostat/compute/worker.py: backend `docker` when `docker` is on PATH (`hello.backends` and `hello.images` from `docker image ls --format {{.Repository}}:{{.Tag}}@{{.Digest}}`). The keeper runs `docker run -d --init --name ergostat-run-RUN --cpus --memory --memory-swap(=memory) --pids-limit --network none(default) --cap-drop ALL --security-opt no-new-privileges -v RUNFOLDER:/work -w /work IMAGE /bin/sh -c COMMAND`, output to the run folder's out/err files (a wrapper in the container redirects; never `docker logs` alone), records the container id in run.json, waits with `docker wait`, writes the exit; at its deadlines `docker stop -t K` then `docker rm -f`. Readings from the container's cgroup (cpu.stat, memory.current, memory.peak) through `docker inspect`/the cgroup path, in the same keys as the process backend. `no such image` is refused at start. restart-states reads a container as running or exited by its recorded id (the docker reading is added to its allowlist). The sweep removes only containers named `ergostat-run-` plus 32 hex. Docker is a resource limit, not a security boundary (CLAUDE.md): the SPEC says so.

Definition of done.
1. A docker run's output, exit and readings arrive as a process run's do.
2. With `network: none`, a run that opens a socket fails.
3. After a session is cut, the keeper has asked `docker rm -f` by the lease's expiry plus grace(ttl)/2.
4. `no such image` is refused before anything is made.
5. Tests skip when docker is absent.

Files: ergostat/compute/worker.py, tests/test_compute_docker.py (new), docs/SPEC.md.

Acceptance tests (skipped without docker).
- tests/test_compute_docker.py::test_docker_run_reports_like_process, ::test_network_none, ::test_cut_session_container_removed_by_deadline, ::test_no_such_image_refused, ::test_sweep_only_its_containers.

Size budget: 250 net lines.

### compute-calls-from-node (incremental)

A node run calls the engine back through a socket its worker forwards

depends-on: ['compute-remote-backend']

Problem. A local run calls `ergostat act`, `event --add`, `lease` and `item` through `ERGOSTAT_SOCKET` (ergostat/spec/engine.py:1005-1008, 1817-1819; ergostat/calls/). On a node there is no such socket, so compute-pools-config refuses every `runs-on` block whose command uses calls (docs/proposals/compute-systems.md section 4, milestone gap 10).

Change. The worker serves a Unix socket in each run's folder (`runs/RUN/calls.sock`, mounted for docker), puts its path in the run's `ERGOSTAT_SOCKET`, and forwards each call as `call {run, id, body}` to the engine, at most 20 calls a second a run (beyond: answered `busy`). The engine answers it as its own socket does (ergostat/calls/server.py's handler, with the run's identity from the handle, never from the call), and the worker relays `answer`. `ERGOSTAT_CMD` on a node names `python3 -I worker.py --call` (a client mode of the worker that speaks the same socket protocol as ergostat/calls/client.py). compute-pools-config's refusal is lifted for program blocks.

Definition of done.
1. A node run that calls `$ERGOSTAT_CMD event --add` gets its event recorded, caused by its run, as a local run's is.
2. A call naming another run's identity is answered as the caller's run, never the claimed one.
3. The 21st call in a second is answered `busy`.
4. A call arriving after the run's lease ended is refused by the fence as a local one is.
5. check no longer refuses `runs-on` blocks that call.

Files: ergostat/compute/worker.py, ergostat/compute/remote.py, ergostat/calls/server.py (an entry point for forwarded calls), ergostat/compute/compile.py, tests/test_compute_calls.py (new), docs/SPEC.md.

Acceptance tests.
- tests/test_compute_calls.py::test_event_add_from_node, ::test_identity_from_handle, ::test_rate_limit, ::test_call_after_lease_refused, ::test_check_allows_calling_block.

Size budget: 250 net lines.

### compute-demo (incremental)

examples/compute-pair: items worked on two same-machine nodes, one lost mid-run

depends-on: ['compute-capacity-measures', 'compute-lease-renew-on-node', 'compute-reattach']

Problem. Nothing shows a compute pool working end to end, and demo_check (scripts/demo_check.py) covers no compute model (docs/proposals/compute-systems.md milestone gap 11). examples/remote-pair/ with tests/test_remote_pair.py is the pattern for a two-process demo.

Change. `examples/compute-pair/`: a model with one item kind, a program block with `runs-on: pair`, and a pool of two nodes each `connect: [python3, -I, ../../ergostat/compute/worker.py, --stdio, --root, ...]` (roots under the demo's state folder), plus a stock and goal on `ergostat.compute.free@pair` so the capacity is drawn as any stock in the Dynamics diagram and as a plant input in Blocks (only what the model declares). `run.sh` starts it; a script kills one worker and its keepers mid-run. README says what to watch. tests/test_compute_pair.py: the killed node goes lost, its slots leave the stock, its item's lease expires (counted), and the item is worked again on the other node and ends; no host names anywhere. demo_check covers the model.

Definition of done.
1. `examples/compute-pair/run.sh` runs the demo to completion on macOS and Linux.
2. The test sees: node lost, `slots@pair` drops, lease expired, item re-run on the other node, item done.
3. `scripts/demo_check.py` passes with the demo included.
4. The demo draws no part it does not declare.

Files: examples/compute-pair/ (new: model, README.md, run.sh), tests/test_compute_pair.py (new), scripts/demo_check.py, docs/SPEC.md (one line pointing at it).

Acceptance tests.
- tests/test_compute_pair.py::test_node_lost_item_reworked.
- tests/test_demo_check.py passes with compute-pair.

Size budget: 150 net lines outside tests/ and docs/ (the model YAML counts).
