## Entry

section: Runtime, scale and latency

- **The day's AI budget, P3: runs reserve before they start** (done; `run-budget-reserve`, merged in c8c94527; SPEC
  §9.9, `docs/roadmap/overnight/run-budget-reserve.md`, `dev/records/the-day-s-ai-budget-p3-runs.md`):
  `budget: {daily, max-cost}`; every run started through `Engine.run_block` or `Dispatcher.take` asks a permit under
  a file lock, and a charged run is refused unless what is left of the day covers `max-cost`; spend is folded by run
  id, an unknown cost charged as the reserve; `ergostat.budget.left`. P3 itself covers those two start paths only:
  ergostat's own AI calls are the next entry's (`ai-calls-ask-the-budget`), and models in `ergostat.toml` are left to
  `toml-models-budget`.
