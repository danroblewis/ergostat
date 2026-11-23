## Entry

section: Done recently

- **A renewing run killed because the engine was busy recording its renewal** (done on `leaserenew`, merged as
  1f013ba, its last commit 372533d; SPEC §9.5, `docs/roadmap/overnight/leaserenew.md`): the watchdog expires a lease
  only on a second look at the same expiry, `grace(ttl)` after the first (a tenth of the TTL, 1-30 s), and re-reads
  the lease just before it writes, writing nothing when it was renewed or ended; the fold refuses an expiry judged
  before a renewal, and the readers of raw expiries leave a refused one out (measures `counts`/`attention`, the
  estimates, the block models, the workspace sweep), reading what each item refused from the item index, transcripts
  never folded. Measured there on 2026-11-20: with a GIL-holding thread in the engine, 16 of 32 runs killed on main
  before the fix, 0 of 48 after; at 1,000 items × 300 lines, counts / estimate / identify took 0.15 / 0.13 / 0.10 s
  before refused expiries were left out and 0.17 / 0.14 / 0.12 s now. The cost test
  (`tests/test_lease_refused_cost.py`) bounds each read at 2× + 50 ms of the cost without the refusal.
