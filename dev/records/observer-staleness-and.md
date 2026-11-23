## Entry

section: Modelling

- **Observer staleness and estimated stocks** (done, `observer`; SPEC §9.6, `coordinator/06-observer.md`): a reading's
  age, `stale` goals, `on-stale: act | hold | off` per goal or block; a scalar Kalman estimate per stock with an adaptive
  gain (`stock.X.estimate`, `.uncertainty`), its innovations as `observer/X/innovation`, and `model-disagrees`. All
  opt-in (`observe: true`, `on-stale:`, or reading the estimate). Not yet: a
  covariance between stocks, item-level states (06's x̂1 to x̂10), sampling that rises after a surprise (06 §3.3).
