## Entry

section: Runtime, scale and latency

- **ergostat's own AI calls under the budget** (in part; `factory/ai-calls-ask-the-budget`, SPEC §9.9,
  `dev/records/ai-calls-ask-the-budget.md`). Done: every call through `decisions/ai.call` (decisions extract, the
  intent verdicts from `Engine.judge` and `ergostat intent judge`, `improve --architecture`) reserves its per-call cap
  under P3's lock (`costs/budget.ask`), is refused when the day's budget is gone, is closed with its reported cost
  (unknown: its reserve), and is counted once inside a reserving run. So does every call through
  `numbers/modeller` (the redesigner, the modelling reviewer, the ai tier, the architecture review:
  `modeller-calls-ask-the-budget`, `dev/records/modeller-calls-ask-the-budget.md`), at its `unsaid` estimate. A
  structural scan (`test_only_listed_ai_starts`) finds AI commands started only in `decisions/ai.py`,
  `numbers/modeller.py` and a named allowlist (`bench/`, `session.py`, `supervisor.chat`, `spec/engine.py`,
  `repair/fix.py`). Left: models in `ergostat.toml` (`runner.run_agent`), which have no `budget:`
  (`toml-models-budget`). Their ends count in spent when priced, but nothing refuses them when the day's budget is
  gone.
