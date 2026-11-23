## Entry

section: Runtime, scale and latency

- **T1: a run stopped at its spend cap** (done; `run-budget-trip`, SPEC §9.9, `dev/records/run-budget-trip.md`):
  each run gets its reserve as its cap (`ERGOSTAT_MAX_COST`; `--max-budget-usd` on an `ai` block's own `claude`),
  `ergostat session` takes all that is left from a per-run ledger under `flock`, and the engine kills the run's
  process group once its reported cost (an unknown part counted as the whole reserve) reaches the reserve. Left: a
  program running `claude` itself is stopped only after its result line, and an `ai` block's own `claude` is not in
  the ledger, so a run can go up to about twice its reserve before T1 sees it.
