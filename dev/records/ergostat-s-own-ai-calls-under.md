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

## Where it stopped

Built, round 1. Net code lines outside `tests/`, `docs/`, `dev/`: 72 (`runner.py` +43, `model.py` +26,
`cli/agents.py` +3), within the 90 budget. `main` merged (already up to date: the clone's base).

How it is built: `Model.budget` (a `spec.ir.RunBudget`, or None) is read from `[budget]` in `model.parse`.
`run_agent` passes `costs/budget.permit` a spec of `{budget, agents: {its agent}}` and a block standing in for the
agent (`type` = the agent's kind), so the permit, its flock, `budget.FREE` and `reserve_of` are the engine's own,
unchanged. The old body is now `runner._ran`, at the same indent. `Runner._recover` runs on each schedule tick and
calls `budget.recover` at its default once a minute.

Choices made alone (the most reversible):
- A refused run returns `{"budget_refused": why, "note": "refused: budget: …"}`. It is a separate key because
  `refused` already counts refused output lines. `ergostat agent NAME --now` prints the note on stdout, as
  `block --now` does, and exits 1 (with `--json`, the run and its events).
- The free check uses the agent object `run_agent` was given, not a lookup in `project.model`, so a run carried
  across a reload is typed as the agent it began as.
- `tests/test_run_budget.py::test_only_known_start_paths` names `runner.py:run_agent.write` instead of
  `runner.py:run_agent`. The `agent.started` write now sits in the nested `write` that `permit` calls. A lambda
  would keep the old name but ruff refuses it (E731). It is still one named site.
- `ERGOSTAT_MAX_COST` and the T1 kill on a reported cost are not given to toml runs. The definition asks only for
  `--max-budget-usd`, and SPEC, the guide and GAPS say so.

Each acceptance test, and the break that made it fail (each break applied by hand to the committed code, the file
then restored, and the suite seen green again):
- the permit call removed (the start written with its reserve and no decision): `test_toml_run_refused_when_day_spent`,
  `test_toml_permit_holds_the_lock`, `test_toml_free_kinds_only[ai]`, `test_toml_free_kinds_only[narrow-ai]`,
  `test_toml_run_raised_is_closed_at_reserve` (the id was never in `OPEN`, so it was not closed) and
  `test_toml_orphan_recovered` failed. 6 failed, 5 passed.
- the free-kinds allowlist widened (`"narrow-ai"` added to `budget.FREE`): `test_toml_free_kinds_only[narrow-ai]`
  failed.
- the close-on-raise removed (`budget.close` replaced by `pass`): `test_toml_run_raised_is_closed_at_reserve` failed.
- the `--max-budget-usd` rewrite removed (`if False and …`): `test_toml_claude_command_capped` failed.
- the competing write put in the gap (the permit replaced by the fold read, `budget._between()`, then the write, with
  no flock): `test_toml_permit_holds_the_lock` failed on its own assertion, because the second run was admitted.
- in addition, `Runner._recover`'s `budget.recover` call removed: `test_toml_orphan_recovered` failed.
- `test_toml_budget_parsed_and_bounded` is not guarded by a break of the run path. It checks each refused value
  directly (missing key, bool, NaN, inf, a 400-digit integer, a string, an unknown key, `daily` above the ceiling,
  `max-cost` of 0 or above `daily`, a `[budget]` that is not a table). The error must name the key each time.

How "the Runner's next pass is admitted again" is tested: recovery turns the orphan's reserve into a charge for a
day from the close, so it frees nothing at once. The test runs at once (refused), recovers, then moves the clock 1.5
days on, and the next run is admitted. Without the recover it is still refused, because the orphan stays reserved
for 7 days.

Tests run (`scripts/named_tests.py`, serially): `tests/test_toml_models_budget.py` (11 passed),
`tests/test_runner_and_state.py` (43 passed, unchanged), `tests/test_run_budget.py`, `tests/test_ai_calls_budget.py`,
`tests/test_run_budget_trip.py` (65 passed after the start-path name above), `tests/test_model.py`,
`tests/test_agents.py`, `tests/test_reload_in_place.py` (51 passed). ruff clean. Not run here: the whole unit suite
and the four browser files (left to the factory). No page changed.

Seen, not changed (outside the gap): the AGENT-GUIDE §3b lead-in still says "The modeller's calls … are outside
it", which its own later bullet contradicts (those calls ask since `modeller-calls-ask-the-budget`).

### Round 2: the merge of main (f086f76e), and the review's finding

Main now carries `toml-models-budget` (`dev/records/toml-models-budget.md`, `tests/test_toml_budget.py`), which
landed the same design in parallel: `model._budget`, `budget.of`, `run_agent` asking `budget.permit` under its flock,
the close on a raise, `Runner._recover`, and `ergostat agent NAME --now` printing `refused: budget: …` (to stderr,
exit 1). I resolved the conflicts by keeping main's code for all of that. That is the most reversible choice: main
already ships it, and its own file tests it. From this branch I kept only what main lacks:

- `--max-budget-usd` at the run's reserve on a `claude` command, replacing any value already in it (`runner.py`).
  That is now this branch's whole code change against main: `ergostat/runner.py` +9 −6, net +3 lines.
- `tests/test_toml_models_budget.py`, changed only to use main's names. A refusal is the key `budget` (not
  `budget_refused`), and the test reads the CLI's refusal from stdout and stderr together.

Taken from main, and so changed from round 1: an `[[agent]]` with no `kind` written is charged. This is main's
stricter rule (`budget.of` passes its kind as None). Round 1 read such an agent as `program` and let it run free.
Round 1's `budget_refused` key and its extra CLI branch are gone, as they were dead next to main's. The error
messages are main's, and each still names its key (`[budget].daily: out of bounds`, `[budget]: missing max-cost`,
`[budget]: unknown key 'weekly'`).

The review's finding (this gap listed twice in GAPS): main's `toml-models-budget` has landed, so the toml part is
now done. I kept the entry under *Done recently* (main's, which says done) and added this gap's record and the cap to
it. I removed the Runtime entry, which said "in part" and had a "Left: models in `ergostat.toml`" clause. I also
removed a one-line fragment of it that an earlier merge left dangling above the P3 entry (`… (done;
factory/ai-calls-ask-the-budget, SPEC §9.9,`). One entry is left, with no "Left" clause. This goes against the
finding's literal instruction (remove the Done recently entry), because its premise, that the gap is not done, no
longer holds on main. SPEC §9.9 keeps main's "In `ergostat.toml`" bullet, with one sentence added for the cap. The
branch's duplicate "Models in `ergostat.toml`" bullet and its second "Limits, stated" are dropped. The agent guide
keeps main's bullet, with the cap sentence added.

Breaks re-run on the merged code (each applied by hand, then restored, and the file seen green again, 11 passed):
- the permit call removed (the start written with its reserve and no decision): 6 failed,
  `test_toml_run_refused_when_day_spent`, `test_toml_permit_holds_the_lock`, `test_toml_free_kinds_only[ai]`,
  `test_toml_free_kinds_only[narrow-ai]`, `test_toml_run_raised_is_closed_at_reserve`, `test_toml_orphan_recovered`.
- the free-kinds allowlist widened (`"narrow-ai"` added to `budget.FREE`): `test_toml_free_kinds_only[narrow-ai]`.
- the close-on-raise removed (`budget.close` replaced by `pass`): `test_toml_run_raised_is_closed_at_reserve`.
- the `--max-budget-usd` rewrite removed (`if False and …`): `test_toml_claude_command_capped`.
- the competing write put in the gap (fold read, `budget._between()`, then the write, no flock):
  `test_toml_permit_holds_the_lock` failed on its own assertion (the second run was admitted).
  `test_toml_run_refused_when_day_spent` failed too, but only on the reason's text.

Tests run after the merge (`scripts/named_tests.py`, serially): `tests/test_toml_models_budget.py` (11 passed);
`tests/test_toml_budget.py`, `tests/test_runner_and_state.py`, `tests/test_run_budget.py` (104 passed);
`tests/test_ai_calls_budget.py`, `tests/test_run_budget_trip.py`, `tests/test_agents.py` (48 passed);
`tests/test_model.py`, `tests/test_reload_in_place.py`, `tests/test_modeller_budget.py` (38 passed). ruff clean.
Not run here: the whole unit suite and the four browser files (left to the factory). No page changed.
