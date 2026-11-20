# leaserenew: a renewing run killed because the engine was busy recording its renewal

Branch `leaserenew`, from main at b24103e. Bug: `tests/test_lease_kill.py::test_a_renewing_run_is_not_killed` failed
intermittently under the merge queue's parallel suite (`ergostat.run.killed` recorded for a run that renewed).

## The bug

The test's numbers have slack: TTL 1 s, a renewal every 0.4 s plus the call (about 0.1 s through the engine's socket,
0.15 s loading the model), so a renewal is recorded about every 0.52 s. Under a CPU burner at the CPU count, other
agents' suites and load up to 65 (340 runs), the longest gap between recorded renewals was 0.67 s and nothing was
killed. Machine load alone does not do it.

The engine does. A run renews through the engine's socket, so the renewal is recorded only when the engine gets a
thread (the GIL) to record it. While something in the engine's process holds the GIL (a collection, a fit, a busy
thread; the suite's workers carry about 40 threads left from earlier tests, among them page servers'
`ergostat-fit-history`, a CPU-bound fit every 300 s), the watchdog can wake first, find the lease past its expiry with
the renewal still queued, and kill a run that asked in time. SPEC said a run is killed "only when that expiry took (not
renewed meanwhile)", but the fold applied any expiry to a held lease, so that check never caught a renewal.

**Evidence.** One thread in the engine's process holding the GIL about 0.9 s at a time, copies of the test at
`-n 8`: on main, **16 of 32** runs killed (recorded renewal gaps up to 1.57 s); on this branch, **0 of 48** (gaps up
to 2.7 s).

## What is done

- The watchdog expires a lease only on a second look at the same expiry, `grace(ttl)` after the first (a tenth of the
  TTL, at least 1 s, at most 30 s; a renewal starts it again; `leases/terms.py`).
- Just before writing the expiry it reads the lease again from the record and writes nothing when it was renewed past
  the expiry it judged, or ended.
- The expiry names the `expires` it judged; the fold refuses it when the lease was renewed since (the belt for the
  moment between the re-read and the write). Expiries without `expires` (old records) replay the same.
- Readers of raw expiries leave a refused one out (`fold.refused_expiries`): the workspace sweep and `on_event`,
  `leases/measures.py` (`counts`, `attention`), `numbers/blockmodels.py` (`identify`), `numbers/etamodel.py`
  (`_leases`). Workspaces are released, the run killed and the expiry said only when it took.
- One item's error in `watch()` stops no other lease's look; first looks are saved in a `finally`.
- `numbers/eta.py` models an expired attempt as TTL + grace. SPEC §9.5: the grace, `expires`, refused expiries, and
  that `ergostat.leases.overdue` is non-zero during the grace (a goal on stalls holds `expired`).
- Tests (`tests/test_lease_kill.py`, `tests/test_leased_workspaces.py`): the fold's refusal; the grace and its restart;
  a renewal before the re-read writes nothing; one between the re-read and the write releases no workspace, counts
  nowhere and leaves the estimates seeing the run going; one item's error stops no other's look. Unit suite rc 0.

## Where it stopped

Parked by the final re-review under the kill rule (everything else passed: the readers covered, the re-read fails
closed, old records replay the same). The one blocker is cost: `refused_expiries` (`leases/fold.py`) folds each item
with an expiry by an uncached `its.one`, transcripts included, on every call: from `leases/measures.py` `counts`
(every measure sample, ignoring `by_block`), `numbers/etamodel.py` `_leases` (up to 50k lease events per estimate
read), and `numbers/blockmodels.py` `identify` (called from impact and closedloop, twice, and the numbers API).

**The fix still needed:** read `refused` from the item index (`its.project(..., transcript=False)`, or the `ix`
etamodel already has: the index keeps each item's `refused`, `spec/items.py`); in `counts`, use the items its first
loop already projected; at the least skip `TRANSCRIPT_TYPES` and cache by (item, last seq). **The test needed:** a
performance test with many expired items and long transcripts, bounding the time of `measures.counts`,
`etamodel.read` and `blockmodels.identify` (against main's), besides the tests above.

**Done (2026-11-20).** Merged origin/main (clean). `refused_expiries` now reads what each item refused from folds
already in hand: the caller's (`items`, by id: `measures.counts` passes the items its first loop projected), else the
item index (`ix`, which `etamodel.read` passes on; else the record's, `transcript=False`, caught up: the index is the
cache by each item's last event), and folds only an item neither holds, its transcript left out. It answers only for
the expiries it was given. `counts` narrows the expiries to its kinds and, with `@BLOCK`, to the block before asking.
`tests/test_lease_refused_cost.py`: 300 items each taken and expired, each with a 200-line transcript; it asserts no
item's events are read again by `measures.counts` (plain and `@developer`), `etamodel.read` and
`blockmodels.identify`, and that each costs at most twice (+50 ms) what it costs with nothing left out (main's
behaviour); the parked code fails both (0.21 s against 0.003 s for `counts`). At 1,000 items × 300 lines:
main 0.15 / 0.13 / 0.10 s, the parked code 1.29 / 1.23 / 1.26 s, now 0.17 / 0.14 / 0.12 s (counts / estimate /
identify). The GIL-hog evidence, once more on this code (a thread sorting 7M floats, about 0.9 s a hold, 48 copies
at `-n 8`): 0 of 48 killed, all done, recorded renewal gaps up to 1.74 s.
Unit suite (`-n 8 --dist worksteal`, under `suite_watch.py`): 1906 passed, 14 skipped, 1 xfailed, rc 0. The four
browser files (`-n 4`, with playwright 1.63.0): 218 passed, rc 0.
