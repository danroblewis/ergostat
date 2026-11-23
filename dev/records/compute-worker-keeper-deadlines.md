# compute-worker-keeper-deadlines: The keeper holds a run's wall and lease deadlines on a clock that counts suspend

depends-on: [compute-worker-keeper]

Problem: a run on a node must not outlive its timeout or its lease when the session, or the engine, is gone; locally the timeout lives in the engine's follower (ergostat/spec/stream.py:36-38), which a node does not have. Change: new module ergostat/compute/worker/deadline.py used by the keeper. `start` writes the first deadline file (runs/RUN/deadline) from the spec's wall limit and lease. The keeper holds the wall deadline and the lease deadline, read from the file every quarter second, on a suspend-counting clock (CLOCK_BOOTTIME on Linux, the equivalent continuous clock on macOS; the module names the one it uses); an unreadable or garbage file keeps the last value and can never move a deadline later; at the earlier deadline it sends SIGTERM then SIGKILL after K and writes exit with how `wall` or `lease`. Done: a run past its wall is killed with how wall; a run whose lease deadline passes is killed with how lease; garbage written to the deadline file never extends; a deadline moved earlier takes effect within half a second; with the worker gone (stdin closed) both deadlines still hold; a simulated clock jump of an hour in the time of day changes nothing. At most 8 processes a test. Files: ergostat/compute/worker/deadline.py, ergostat/compute/worker/keeper.py, tests/test_compute_keeper_deadlines.py (six tests), docs/SPEC.md. Full text: wave2-compute.md (compute-worker-keeper, the deadline half). Budget: 130 net lines.

Area: compute. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1: ergostat/compute/worker/deadline.py (the clock, the file, `Held`), keeper.py (`start` writes the
first deadline file; `keep` holds it), the six tests in tests/test_compute_keeper_deadlines.py, SPEC §12s.3 and §12s.5.
104 net lines outside tests and docs.

Choices made alone (the most reversible; nobody to ask):
- The deadline file is `{"wall": T, "lease": T|null, "kill": K}`, times on the keeper's clock (CLOCK_BOOTTIME on
  Linux, CLOCK_MONOTONIC elsewhere: on macOS the continuous clock). `start` takes an optional `lease` `{"left", "ttl"}`
  (seconds); converting the engine's `sent` to this clock is compute-worker-lease-clock's.
- "Can never move a deadline later" is read as: garbage or an unreadable file never moves either one; the wall never
  moves later from any file; a well-formed file's lease is taken either way (renewals must extend it, as
  wave2-compute.md's lease-clock text says), but a `null` lease never drops one held. A time over a day from now, or
  non-finite, is garbage.
- No `limits.wall`: the wall is a day (the most `over` allows), so no node run is unbounded.
- A deadline file unreadable at the keeper's start: the run is not started (`how` `not started`), never run with none.
- keeper.py imports `deadline` only when loaded by bare name (`__package__` empty: the worker's and the keeper's own
  process), since the worker's modules may import only the standard library and each other by bare name
  (tests/test_compute_worker_protocol.py); the engine imports keeper as a package and never calls `start`/`keep`.
- Engine runs kept with `runs: outlive_engine` keep their `timeout` how; their wall is now timed on the same clock.
