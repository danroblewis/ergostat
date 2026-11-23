# compute-worker-lease-clock: The worker turns the engine's lease renewals into its keeper's deadline, on its own clock

depends-on: [compute-worker-keeper-deadlines]

Problem: a keeper must kill a run whose lease the engine stopped renewing, by the engine's expiry, without comparing a time of the engine's with its own (compute-systems.md section 2.7); the keeper reads runs/RUN/deadline but only its first value is written. Change: new module ergostat/compute/worker/leaseclock.py: each engine message carrying `sent` (start's lease, `renew {run, fence, left, sent}`, ping) gives heard - sent on the worker's suspend-counting clock; `base` is the least over the last ten minutes. A run's lease deadline is sent + base + left of the latest renewal heard for its fence, written by temporary file and os.replace; an older fence is ignored; a later renewal of the same fence may move it either way. Only a renewal heard writes the file. K = grace(ttl)/4 (ergostat/leases/terms.py:38-41) is written beside it for the keeper's SIGKILL. Done: with random delays the deadline is never later than the engine's expiry plus the least delay seen; a clock of day an hour off changes nothing; a delayed renewal does not extend; an old fence is ignored; after a cut session the keeper kills by the last deadline plus K. Files: ergostat/compute/worker/leaseclock.py, ergostat/compute/worker/serve.py (one registration), tests/test_compute_lease_clock.py (five tests), docs/SPEC.md. Budget: 120 net lines.

Area: compute. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1: `ergostat/compute/worker/leaseclock.py` (86 lines), two lines in `serve.py` (its import and one
registration, wrapping `start` and `ping` and adding `renew`), the five tests in `tests/test_compute_lease_clock.py`,
SPEC §12s.3 and §12s.5. 88 net lines of code, within the 120 budget. Each test was seen to fail against a break of the
code it guards: the deadline taken as heard + left (random delays, delayed renewal), the fence check removed (old
fence), the time of day mixed into the clock (time of day), no `renew` registered (cut session).

Choices nobody could be asked about, each the most reversible:
- `renew` answers nothing when taken or ignored (as `ack` does); `refused` with `no such run` or `no lease`.
- K is kept from the file, where `start` already wrote grace(ttl)/4 (`deadline.kill_after`): `renew` carries no ttl,
  and the worker may have restarted since `start`. A run started without a lease is refused (`no lease`), never given
  one with the wall's 2 s K.
- The fence written is kept in the deadline file itself (`"fence"`, which the keeper ignores), so a new worker on the
  same root still ignores an older fence; `start`'s `lease.fence` is held in memory for the session.
- `start`'s first deadline is still the keeper module's now + left (not rewritten: "only a renewal heard writes").
- A `sent` that is finite but absurd lowers `base` and so moves deadlines earlier: the run is killed, never kept.

Left for other gaps: the engine's side (sending `renew`, `sent` on `ping` and in `start`'s lease) is not built.
