# compute-node-status: Each node's round trips measured, and a pool's status in the heartbeat and /api/status

depends-on: [compute-node-connection]

Problem: the lease rule for node runs needs each node's least round trip, and nothing shows whether a pool's nodes are in service. Change in ergostat/compute/connection.py: a ping every 2 s per node, least_rtt(window=60) from the pongs; a per-pool status() (nodes in service, lost, slots, free, last error, least round trip) that goes in the heartbeat and in /api/status under `compute` (ergostat/web/server.py:447-455) only when the model has pools. No page changes: the status is data in an existing answer. Done: least_rtt is the least of the window and has no value before the first pong; a lost node's slots leave the pool's status at the next reading; a model without pools has no `compute` key; another v's error is in status; no host name, address or user appears in status. Files: ergostat/compute/connection.py, ergostat/web/server.py, tests/test_compute_connection.py (four tests), docs/SPEC.md. Full text: wave2-compute.md (compute-node-connection, the status half). Budget: 90 net lines.

Area: compute. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1 (996cc9c5). Net lines outside tests and docs: 89 (budget 90).

- `ergostat/compute/connection.py`: a ping thread per node (`Node.pinger`) sends `ping` through `request` every 2 s
  while the node is in service, one at a time, so a stopped worker with a full pipe blocks only that thread and never
  the reader's loss detection; it ends with `close` and is joined by `Pools.close` and counted in draining
  (`Node.alive`). `least_rtt(window=60)` is taken from the current session's pongs only: they are cleared when the
  session ends, and a pong that lands after a new session began is not kept (lesson 5). `Pools.status()` per pool:
  `in_service`, `lost`, `slots`, `free`, `error`, `least_rtt`.
- Choices made with nobody to ask, the most reversible taken: `lost` counts every node not in service (lost,
  refused or still connecting: the worst case); `free` is the last beat's `free`, counted 0 before the first beat or
  when it is not a whole number from 0 to the slots; `error` is of the nodes still out of service, the one set last
  by a sequence number (`ERRS`), never by time (lesson 2), as `{node, why}`.
- The heartbeat is written in `ergostat/spec/watchdog.py`, which the Files list does not name: the definition asks for
  the status in the heartbeat, and that file writes it. A status that raises is said and left out; the heartbeat is
  still written (lesson 3).
- `/api/status` (`ergostat/web/server.py`, in the `status` answer; the 447-455 lines named are now about 662-685)
  reads `compute` from the heartbeat files through `watcher.beats` (so the lead shard's too), only when the model
  declares pools; a pool's value is None when no engine runs or the heartbeat gives none for it.
- Tests (tests/test_compute_connection.py): `test_round_trips_measured`, `test_lost_node_slots_leave_the_status`,
  `test_unknown_version_in_status`, `test_status_only_with_pools`. Each was seen to fail under a mutation: the window
  ignored, the error ordered without its sequence, the heartbeat without `compute`, a lost node's slots counted.
- Run: tests/test_compute_connection.py (10 passed), tests/test_upkeep_watched.py, tests/test_resilience.py,
  tests/test_engine_shard.py (106 passed), ruff clean. Not run here: the whole unit suite, the four browser files
  (no page changes), demo_check (no example touched). `main` had no commits past the branch, so there was nothing to
  merge.
