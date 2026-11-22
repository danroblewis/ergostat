## Entry

section: Runtime, scale and latency

- **ergostat's upkeep as a modelled system** (idea; owner, 2026-11-19): a built-in `use: upkeep` template, like
  `use: modelling`, drawing ergostat's own housekeeping as control loops: item-index files (created on each change to
  the kinds, tidied, healed), event-log compaction, measurement retention, the worktree pool, expired leases, the
  engine's stall watchdog. Stocks, goals (e.g. index files <= 6) and rule-tier controllers instead of constants in
  the code; whether a delete is safe stays an interlock in the code (`coordinator/08-modes-and-protection.md`), and
  no controller reads what it manages. If the engine stops, its loops stop: so correctness never depends on them, each fails
  safe (tidying stopped means files pile up, nothing breaks), and they are watched in layers (the engine's own
  watchdog, then the runner or launchd for a dead process, with a heartbeat goal an outside watcher reads).
  - **The item-index files** (done on `factory/upkeep-index-files`, `docs/roadmap/overnight/upkeep-index-files.md`):
    `use: upkeep` with the loop `index-files` / `index-files-few` / `index-tidier` (`upkeep tidy --keep N`); the
    engine stands down from tidying under it; the interlock (lock without waiting, age checked again under the lock,
    an allowlist of index names under the resolved folder) stays in `spec/itemindex.py`. Under `use: upkeep` nothing
    else limits the count if the tidier stops.
  - **The record's loops** (done on `factory/upkeep-record-loops`, `dev/records/upkeep-record-loops.md`): the stocks
    `rollup-due`, `events-past-keep` and `measurements-due`, held at 0 by `record-compactor` and `record-pruner` (both
    `upkeep rollup`) and `measurement-retainer` (`upkeep retain`), each every 1m to 1d; the engine stops rolling up
    under `use: upkeep`. Every compactor (the engine, `ergostat compact`, the programs) holds `<state>/compact.lock`,
    an `flock` taken without waiting, and says `busy` when it is held. A store that cannot count gives no reading.
  - **The watched loops** (done on `factory/upkeep-watched-loops`, `dev/records/upkeep-watched-loops.md`): the
    stocks `heartbeat-age`, `stalls` and `restarts` (`ergostat.upkeep.*`), the goals `heartbeat-fresh` (`<= stale`,
    180, 60 to 3600) and `no-stalls`, and the engine's watchdog and the outer watcher as `type: external` blocks;
    with `leases: true` lease expiry, with `pool: NAME` that pool's quarantined slots held at 0 by the owner. The
    engine writes `stale` into `heartbeat.json`; the watcher uses it within 60 to 3600 s, else 180. Left: the loops
    are drawn, not closed by ergostat (their controllers are its code); the heartbeat the run writes as it starts has
    no `stale`, so the watcher uses 180 until the watchdog's first beat (5 s); `restarts` has no goal.
