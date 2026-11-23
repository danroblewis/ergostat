## Entry

section: Done recently

- **Warm processes for blocks** (done on `factory/warm3`, finishing `warm2` and `warm3`, each parked after two failed
  gates; SPEC §9.7, `docs/roadmap/overnight/warm2.md`): `warm: true` on a daemon, a declared promise that the program
  keeps no state between runs: `concurrency` processes, one run each at a time, each run charged its process group's
  CPU (its reaped children's included); a process that misbehaves is restarted, one cancelled or past `recycle:`
  replaced; `ergostat block NAME --check-warm FILE` tests the promise on one input. `main` (f158e00) was merged in on
  2026-11-20 (2ca24c7), and the factory's gates ran the four suites on the merged tree (f2f1891) and passed them, as
  review/warm3-3 reports. Measured: 100 items through five steps at `pool: 10`, end to end p50 0.57-0.81 s warm
  against 1.31-1.34 s a process per item (89-116 against 49-56 items a second).
