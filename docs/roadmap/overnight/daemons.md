# daemons: long-lived runners for blocks and sensors, supervised

Branch `daemons`, from main (c4472b6). Asked by the owner (2026-11-19): their work model has 170 sensors; each
command sensor every 3 minutes is about 57 process starts a minute. They want daemon-style runners: long-lived
processes that take work as JSON lines on standard input and write a stream of JSON lines to standard output, many
items and leases at once, interleaved, for blocks and for sensors. It supersedes the parked `warm` branch (warm
processes, one item at a time), and takes its review's findings (B1 env per item, B3 per-item CPU, B4 untagged
`done`) as lessons. It also adds `docs/RUNTIME.md`, a human explainer of how ergostat runs, with the bench numbers.

## Definition of done

**Part 1, the explainer.** `docs/RUNTIME.md`, plain prose for a human reader, with Mermaid diagrams: the event log
as the bus (its backends, the single writer under a file lock, notify-on-write); the scheduler loop; sensor kinds and
which start processes (items and changes: none; queries: batched on the pool of eight; `run:` commands: a process per
reading); blocks and runs; the dispatcher and leases; the socket; push intake; how a model reload swaps; the watchdog
and the outer watcher; and daemons. A bench (`scripts/daemon_bench.py`, watchdogged: killed past 1,500 threads or
6 GB, starting at N=20) runs a synthetic model of N command sensors every 3 minutes, as processes and then as one
shared sensor daemon, and the doc gives, for N=20 and N=170: process starts a minute, CPU (engine and children), memory
and the engine's pass latency.

**Part 2, daemon runners.** A program block may say `daemon:` instead of `run:`, and a sensor `daemon:` (one of the
sensor kinds); either is a map (`run`, `concurrency`, `heartbeat`, `restart: {max, within, backoff: [first, most]}`,
`stdin-timeout`) or the name of a top-level `daemons:` entry, so several sensors and blocks share one process. The
protocol is JSON lines: in, `{"op": "item", "run", "item", "lease", "input", "env"}`, `{"op": "read", "sensor",
"request"}`, `{"op": "cancel", "run"}`, `{"op": "stop"}`; out, every line tagged with its `run` or `request` (run
lines as today's; `{"done": EXIT, "run"}` strict: exactly those keys, an int, never a bool or float; `{"reading": V,
"request"}`), push readings `{"reading": V, "sensor"}` from a sensor with `push: true`, and `{"heartbeat": true}`.
Untagged or unknown-tagged lines are logged and dropped, never given to another run; the per-item env travels in the
line, never in the process's environment. Each item is still a run in the record (`agent.started`, `agent.ran` or
`agent.failed` with `daemon`, its lease, fencing), with wall time only: CPU and memory are the daemon's, sampled per
process, never claimed per item. A sensor read by a daemon starts no process per reading and holds no pool thread.

**Supervision** (`ergostat/daemons/supervise.py`, its own thread, never the engine loop's): a daemon that exits is
started again after a back-off (first, doubling, at most the most); one silent past `heartbeat` (no line of any kind)
is restarted; one that does not read its standard input for `stdin-timeout` (a write blocked, or its bounded queue
full) is restarted with an alarm; more than `max` restarts within `within` and it is given up: state `failed`, an
alarm, and `ergostat.daemon.failed` recorded (an intervention, class `alarm:daemon:NAME`, for `notify` to count).
Every write goes through a writer thread per daemon with a bounded queue: the engine never blocks on a daemon. A lease
expiring (or a run's timeout, or the owner's `block --stop`) sends `cancel`; a daemon still holding that run past the
kill grace is restarted, its other items given back uncounted. On a model swap a daemon whose definition changed is
sent `stop`, drained (its runs finish under the old model), killed after the grace once idle, and a new one started.
Daemons show on the Agents page (state, pid, restarts, last line, CPU, memory) and in the agent's panel; a failed or
alarmed daemon needs attention. No new page or panel. SPEC (§6, §9.3, a new §9.7), the agent guide (a minimal Python
and shell daemon; fail hard; heartbeat) and GAPS (warm workers superseded) say so.

## Acceptance tests (`tests/test_daemons.py`)

- `test_crash_restarts_the_daemon`
- `test_silence_past_heartbeat_restarts`
- `test_restart_storm_gives_up_with_alarm_and_intervention`
- `test_stdin_not_read_restarts_and_alarms_without_blocking_the_engine` (asserts the loop's latency)
- `test_interleaved_items_are_attributed_to_their_runs`
- `test_stray_and_unknown_tagged_lines_are_dropped`
- `test_strict_done`
- `test_cancel_on_lease_expiry_and_restart_when_ignored`
- `test_a_swap_restarts_a_changed_daemon_gracefully`
- `test_a_shared_sensor_daemon_serves_fifty_sensors`
- `test_push_readings`
- `test_daemons_are_checked`
- `test_daemons_on_the_agents_api`
- the bench numbers, in `docs/RUNTIME.md`;
- the four suites, rc 0, no skips; `demo_check` ticket-factory and image-squeeze.

## Size budget

**800 net non-test lines** (outside `tests/` and `docs/`), asked for this branch. Why larger than 600: it is a
runtime of its own (the protocol, its process with a writer and a reader thread, a supervisor with back-off, liveness,
backpressure, cancel and drain on swap), wired into blocks, item runs, leases, sensors and the swap, plus its config,
schema, the page's rows and the bench script.
