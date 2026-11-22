# engine-runs-its-shard-join-1: each shard engine gets its own calls socket, heartbeat and start/stop events, its close stops only its own processes, and a shard name not in the plan raises `ShardError`
depends-on: [engine-runs-its-shard-1, engine-runs-its-shard-2]

## Definition of done
- Already on main and not built again: owner asks are followed by the owning shard. `ergostat.action.approved` runs once. `start` refuses another shard's block. Only the lead does `history.note`, `_prune`, the `Ingester` and `ergostat.started` (`tests/test_engine_shard_asks.py`).
- With `shard=None` nothing changes: same socket path, `heartbeat.json`, events with no `shard` field, and `close()` as today. The existing unit suite passes, and no test outside `tests/test_engine_shard*.py` is edited.
- **Files per shard.** In `calls/server.py`, the socket path depends on the state directory and the shard. `path_for(state)` and `path_for(state, None)` give today's path. Shards get different paths, including the short fallback for long paths (its hash includes the shard). `calls/client.py` still finds the state directory from any of these paths.
  - Each shard engine starts its own calls server. Two shard engines in one state directory both answer calls, and each run's `ERGOSTAT_SOCKET` names the socket of its own engine's shard.
  - The watchdog and `cli/running.py` write `heartbeat.<shard>.json` (`heartbeat.json` when the shard is `None`).
- **Watcher.** `watcher.look` treats the engine as stale when `heartbeat.json`, or any `heartbeat.<shard>.json` whose pid is the running engine's, is older than `STALE`. A shard heartbeat left by another pid is ignored. A file that cannot be read counts as no beat, as today.
- **Events.** `ergostat.started` and `ergostat.stopped` carry `data.shard` (the name, or `null` for `None`). A shard engine that is not the lead records its own `ergostat.stopped`. `ergostat.started` stays the lead's alone.
- **Close.** `close()` on a shard engine kills only what this engine started: its machine-block runs (process groups), agent and sensor runs, daemons and pools. It does not call `old.kill_all()`, and it does not set the process-wide `STOPPING`. Its own runs are still recorded as stopped by ergostat, not as the agent's failure. Another shard's runs and daemons keep going. A shard engine's start does not clear `STOPPING` for the whole process.
- **ShardError.** `ShardError(ValueError)` is raised for a shard name the plan does not have, at construction and on a `swap` to such a plan. The message names the shard and the plan's shards.
- **Not done here, said in SPEC §9.8 and GAPS:**
  - Refusing on wires is left to `shard-wires`, which carries them. The existing shard tests read an estimate across shards on purpose.
  - "Reshard" on swap is superseded by what is on main: a swap clears what moved out (`test_swap_moves_part_out`).
- SPEC §9.8 and the GAPS entry describe the above, and the entry's "Left" is updated.

## Relation to other work
- shard-supervisor: builds on this (one process per shard uses these sockets and heartbeats). It also touches `watcher.py`, so it lands after this. It must refuse shard processes while `Plan.wires` is not empty, until shard-wires lands.
- shard-wires: carries the wires. The wire refusal is left to it, and this plan avoids `shards.py`.
- upkeep-watched-loops: touches `spec/watchdog.py` and `watcher.py`. The heartbeat filename is the only shared change, and the files merge as they are.

## Files to touch
- `ergostat/spec/engine.py`
- `ergostat/calls/server.py`
- `ergostat/calls/client.py`
- `ergostat/spec/watchdog.py`
- `ergostat/cli/running.py`
- `ergostat/watcher.py`
- `ergostat/runner.py`
- `tests/test_engine_shard.py`
- `tests/test_resilience.py`
- `docs/SPEC.md`
- `docs/GAPS.md`

## Risks
- lesson-6: a shard's `close` kills too little (a run started outside `self.procs`, such as an agent or sensor run, keeps going) or too much (`kill_all` or `STOPPING`, which reach the other shard). Guarded by `test_close_one_shard_leaves_other`.
- lesson-3: the watcher reads a missing or other-pid shard heartbeat as fine, or a stale file from a past run as a stall. Guarded by `test_watcher_stale_shard_heartbeat`.
- lesson-8: the SPEC says "per shard" for something still shared, such as the socket fallback or the stopped event. Each claim has a test below.

## Acceptance tests
- `tests/test_engine_shard.py::test_shard_socket_paths`: `path_for(state, None)` equals today's path. Two shards give two different paths, including when the state path is too long. The client maps each path back to the state directory.
- `tests/test_engine_shard.py::test_two_shard_engines_answer_calls`: engines `a` and `b` started in one state directory both answer a call. A run of `a`'s block sees `ERGOSTAT_SOCKET` equal to `a`'s socket.
- `tests/test_engine_shard.py::test_shard_heartbeat_and_events`: a shard engine writes `heartbeat.a.json` and not `heartbeat.json`. `ergostat.started` (lead) and `ergostat.stopped` (each shard) carry `data.shard`. With `None`, the file is `heartbeat.json` and `shard` is null.
- `tests/test_resilience.py::test_watcher_stale_shard_heartbeat`: a stale `heartbeat.b.json` with the running pid gives `stale`. The same file with another pid gives nothing.
- `tests/test_engine_shard.py::test_close_one_shard_leaves_other`: `a` and `b` each have a live run and a daemon. `a.close()` kills `a`'s process group and daemon, records `a`'s run as stopped by ergostat, and leaves `b`'s run, daemon and `STOPPING` untouched.
- `tests/test_engine_shard.py::test_stop_asked_reaches_owning_shard`: `block.stop.requested` for `b`'s running block kills that run in `b`. `a`'s run keeps going.
- `tests/test_engine_shard.py::test_unknown_shard_is_shard_error`: an unknown shard at construction, and a swap to a plan without the shard, raise `ShardError` (a `ValueError`) naming the shard.

## Size budget
110 net lines
size: M (confidence: medium)

## Where it stopped
Built, round 1: every acceptance test above exists and passes. About 67 net lines of code, inside the 110 budget.
These are the choices made with no one to ask. Each is the most reversible one:
- `client.owner` takes a socket in the run's state directory, or in the short folder (`server.short()`), as that state
  directory's. The short name is a hash of the state directory and the shard, so it cannot be mapped back exactly.
  When the socket is in the short folder but is another project's, the call waits its bound, as it did before.
- A shard's pointer file is `engine.SHARD.sock.path`. `client.find` (a shell's command) still finds only the whole
  engine's socket. Finding shard sockets is left to `shard-supervisor`.
- `cli/running.py` and `runner.py` are not edited. `running.py` runs only the `shard=None` engine, so it already
  writes `heartbeat.json`. `kill_all` and `STOPPING` stay as they are, and a shard engine no longer calls either.
- A shard engine's `close` kills every run in its `self.live` (machine-block runs, item runs included), plus its daemons
  and pools. The engine starts no agent runs (the older `Runner` does). A sensor command runs under its timeout and is
  not killed at close by either engine, the same as with `shard=None`.
- Race closed: a run now checks `self.stop` under `self.lock` after it registers in `self.live`, so a run started while
  a shard engine closes either is in close's list or kills itself.
- Still shared and named in SPEC §9.8: `daemons.json` is one file per state directory.
