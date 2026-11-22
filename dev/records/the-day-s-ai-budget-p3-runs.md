## Entry

section: Runtime, scale and latency

- **The day's AI budget, P3: runs reserve before they start** (in progress, `factory/run-budget-reserve`; SPEC §9.9,
  `docs/roadmap/overnight/run-budget-reserve.md`): `budget: {daily, max-cost}`; every run started through
  `Engine.run_block` or `Dispatcher.take` asks a permit under a file lock, and a charged run is refused unless what
  is left of the day covers `max-cost`; spend is folded by run id, an unknown cost charged as the reserve;
  `ergostat.budget.left`. It covers those start paths only.
