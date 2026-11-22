# toml-models-budget: `ergostat.toml` takes a `[budget]` table, and `runner.run_agent` runs reserve from it before they start
depends-on: [ai-calls-ask-the-budget]

## Definition of done

1. **Config.** `ergostat.toml` accepts `[budget]` with `daily` and `max-cost`. Both are required, and they have the same bounds as the YAML key: 0 < daily ≤ 10000 and 0 < max-cost ≤ daily. An unknown key, a missing key, a non-number or an out-of-bounds value is each a model error with its own message. Without `[budget]`, nothing changes.
2. **Runs reserve.** `runner.run_agent` asks the P3 permit before it starts a run, using the same free-kind allowlist by the agent's declared kind; an agent with no kind is charged. The `agent.started` is written inside the permit with `reserve` and `pid`. When the permit refuses, no `agent.started` is written, no process starts, `budget.refused` is written, and the caller gets a refused result. `ergostat agents run` (by hand) prints `refused: budget: …` and exits 1.
3. **Ends and orphans.** A run that raises before its end bookkeeping gets a `budget.closed` with null cost (charged its reserve). The toml runner runs `budget.recover` at its start and on its loop, at most once a minute.
4. **ergostat's own calls.** In a toml project, the calls from `ai-calls-ask-the-budget` and `modeller-calls-ask-the-budget` read this `[budget]`.
5. The GAPS entry moves to *Done recently*. SPEC §9.9 and the agent guide drop `ergostat.toml` from P3's "not covered" list. The house rules are met.

## Relation to other work

- `ai-calls-ask-the-budget`: builds on it. In a toml project, its calls read this budget.
- `modeller-calls-ask-the-budget`: in a toml project, its calls read this budget too. It shares no files with this plan.
- `run-budget-trip`: it edits `costs/budget.py`. This plan does not touch `costs/budget.py` beyond reading the budget from a toml model, so merge main and rerun.
- `shard-supervisor`: it edits `ergostat/runner.py`. This plan changes only `run_agent`'s start and end.

## Files to touch

- `dev/records/toml-models-budget.md` (new)
- `ergostat/model.py`
- `ergostat/runner.py`
- `ergostat/cli/agents.py`
- `ergostat/costs/budget.py`
- `docs/SPEC.md`, `docs/AGENT-GUIDE.md`, `docs/GAPS.md`
- `tests/test_toml_budget.py` (new)

## Risks

- lesson-4: `daily` and `max-cost` move money. They need ceilings at load time and again when a run asks.
- lesson-3: an exception between `agent.started` and its end must still close the reserve. An agent with no kind is charged, never free.
- lesson-1: the toml runner and the CLI start runs in separate processes, so the permit's flock must span the read, the decision and the write in both.

## Acceptance tests

- `tests/test_toml_budget.py::test_toml_budget_keys`: each bad `[budget]` (daily 0 or over 10000, max-cost over daily, a missing key, an unknown key, a non-number) is its own model error. A valid table loads. (lesson-4)
- `tests/test_toml_budget.py::test_run_agent_refused`: under an exhausted budget, no `agent.started` is written and no process starts. `agents run` prints `refused: budget` and exits 1.
- `tests/test_toml_budget.py::test_run_agent_crash_closes_reserve`: a monkeypatched raise after the start gives a `budget.closed` with null cost, charged its reserve. (lesson-3)
- `tests/test_toml_budget.py::test_run_agent_lock_across_processes`: a subprocess permit competes from `budget._between`. Exactly one start gets in. (lesson-1)
- `tests/test_toml_budget.py::test_toml_calls_read_budget`: a `decisions extract` call in a toml project with an exhausted `[budget]` is refused.

## Size budget

110 net lines
size: M (confidence: low)
