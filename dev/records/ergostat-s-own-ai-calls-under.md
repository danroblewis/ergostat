# ergostat-s-own-ai-calls-under: models in ergostat.toml declare a [budget], and every charged run_agent asks the permit
depends-on: []

## Definition of done
Every call through `decisions/ai.call` and `numbers/modeller` already asks the budget; that part is on main and is not planned again. This gap covers only what GAPS lists under "Left": runs started by `runner.run_agent` for a model in `ergostat.toml`.
- `ergostat.toml` accepts a `[budget]` table with `daily` and `max-cost`. It follows the same rules and bounds as `budget:` in `ergostat.yaml`: both keys required, finite numbers only (a bool, NaN, inf or an overflowing integer is refused), and only within the bounds `RunBudget.problem()` sets. Anything else fails to load with a `ModelError` that names the key. An unknown key in `[budget]` is refused too.
- When a toml model declares `[budget]`, every `run_agent` asks `costs/budget.permit` under its flock before it writes `agent.started` and before it starts the command. A run is free (reserve 0) only when its agent's kind is on the same allowlist as `budget.FREE` (person, decision, program, rule). Every other kind (`ai`, `narrow-ai`) reserves `max-cost`.
- A refused run writes `budget.refused` and no `agent.started`, and its command is never started. `run_agent` returns a result that says it was refused and why, and `ergostat agent run` by hand prints that reason. A refused run is not retried at once: the Runner's next run comes on the agent's next trigger.
- If anything raises after the reserving `agent.started` and before its end is written, the run is closed with `budget.closed` at unknown cost, so it is charged its reserve. Its id leaves `budget.OPEN` in a `finally` block.
- A Claude command started by `run_agent` under a budget is given `--max-budget-usd` equal to its reserve, replacing any value already in the command. This matches the engine's T1.
- For toml models the Runner also calls `budget.recover`, at most once a minute, so a reserved run whose process is gone gets closed.
- Without `[budget]`, `run_agent` behaves exactly as it does on main, and the existing tests in `tests/test_runner_and_state.py` pass unchanged.
- SPEC §9.9 (which now says toml models are not covered), the agent guide and the GAPS entry are updated to say what is now covered. The "Left" clause goes, with no second "Left" clause left behind.
- The record `dev/records/ergostat-s-own-ai-calls-under.md` says, for each acceptance test, which break of the code made it fail: the permit call removed, the free-kinds allowlist widened, the close-on-raise removed, the `--max-budget-usd` rewrite removed, and the competing write put in the gap.

## Relation to other work
- the-day-s-ai-budget-p3-runs (building): edits the same GAPS §9.9 area and budget records. This gap does not touch its files; the GAPS entry is edited only where it is, after merging main.
- ergostat-s-upkeep-as-a-modelled (building): also edits `docs/GAPS.md`. This gap avoids its code files.

## Files to touch
- `ergostat/model.py`
- `ergostat/runner.py`
- `ergostat/cli/agents.py`
- `docs/SPEC.md`
- `docs/GAPS.md`
- `dev/records/ergostat-s-own-ai-calls-under.md` (new)
- `tests/test_toml_models_budget.py` (new)

## Risks
- lesson-1: the read of what is spent, the decision and the `agent.started` write happen outside the flock, so two runs both fit under `daily`.
- lesson-3: a run that raises, or a cost that is missing or malformed, counts as 0; or a malformed `[budget]` loads as "no budget".
- lesson-9: a refusal test that only checks the event, not that the command never started.

## Acceptance tests
- `tests/test_toml_models_budget.py::test_toml_budget_parsed_and_bounded`: a valid `[budget]` loads. A missing key, a bool, NaN, a 400-digit integer, an unknown key and an out-of-bound value each raise a `ModelError` that names the key.
- `tests/test_toml_models_budget.py::test_toml_run_refused_when_day_spent`: with spent plus reserved plus `max-cost` above `daily`, an `ai` agent's run writes `budget.refused` and no `agent.started`, and the marker file its command would create is absent.
- `tests/test_toml_models_budget.py::test_toml_permit_holds_the_lock`: `budget._between` is monkeypatched to try writing a competing reservation from another thread. That write waits for the flock, and the second run asking is refused.
- `tests/test_toml_models_budget.py::test_toml_free_kinds_only`: a `program` agent reserves 0 and runs while the day is spent. `ai` and `narrow-ai` agents reserve `max-cost` and are refused.
- `tests/test_toml_models_budget.py::test_toml_run_raised_is_closed_at_reserve`: the Recorder is made to raise after start. `budget.closed` is written with null cost, the fold charges the reserve, and the id is not in `budget.OPEN`.
- `tests/test_toml_models_budget.py::test_toml_claude_command_capped`: a `claude` command that already carries `--max-budget-usd 99` is started with only `--max-budget-usd <max-cost>`.
- `tests/test_toml_models_budget.py::test_toml_orphan_recovered`: a reserving `agent.started` whose pid is dead is closed by the Runner's recover, and the Runner's next pass is admitted again.

## Size budget
90 net lines
size: M (confidence: medium)
