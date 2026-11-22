# modeller-calls-ask-the-budget: every call through `numbers/modeller.call` (the redesigner, the reviewer, the ai tier) asks the day's budget too, and no AI command in `ergostat/` starts outside the listed places
depends-on: [ai-calls-ask-the-budget]

## Definition of done

1. **The modeller's calls ask.** With `budget:` declared, each `numbers/modeller.call` reserves before it starts, the same way `ai-calls-ask-the-budget` does. Its reserve is the call's `unsaid` estimate, which SPEC states is an estimate and not a bound. This covers the redesigner, the reviewer and the `modelling ai` tier. Each call is closed with its reported `usd`; a failed call is closed with null cost and charged its reserve. It is counted once inside its run: these calls print their cost as the run's Claude Code result lines, so the run's end already includes them.
2. **Refused, and said.** A refused call starts no process. The redesigner stops its rounds, and its log says `budget: …`. Its own daily cap and its `redesign.held` hold stay as they are; the refusal is checked as well as them, not in place of them. The reviewer and the ai tier stop the same way, each with a `budget:` note. A refused redesign is not submitted as a change set and is not reported as "nothing proposed".
3. **Only the listed starts.** A structural scan of `ergostat/` finds AI commands (`$ERGOSTAT_AI` or `claude`) started only in `decisions/ai.py` and `numbers/modeller.py`, plus a named allowlist: `bench/` (developer benchmarks), `session.py` (inside a run, which the run's permit covers) and `supervisor.chat` (the owner's own chat). SPEC states that allowlist as the limit of the claim.
4. SPEC §9.9, the agent guide and GAPS are updated, and the house rules are met.

## Relation to other work

- `ai-calls-ask-the-budget`: builds on its call reservation and its counted-once fold.
- `redesign-ghosts-a-removed-system-resumed`: its files are the web and changeset code, not the redesigner's call path, so there is no shared file.

## Files to touch

- `dev/records/modeller-calls-ask-the-budget.md` (new)
- `ergostat/numbers/modeller.py`
- `ergostat/numbers/redesigner.py`
- `ergostat/numbers/reviewer.py`
- `ergostat/library/run/modelling.py`
- `docs/SPEC.md`, `docs/AGENT-GUIDE.md`, `docs/GAPS.md`
- `tests/test_modeller_budget.py` (new)

## Risks

- lesson-3: a refused call read as an empty answer would be reported as "nothing proposed", or would let the next round try again.
- lesson-8: "every AI call asks" is only as wide as the structural scan's allowlist; a new spawn site must fail the scan.

## Acceptance tests

- `tests/test_modeller_budget.py::test_redesigner_stops_when_day_budget_gone`: run inside a reserving run under an exhausted budget, the stand-in AI is never started, the log says `budget:`, and nothing is submitted. (lesson-3)
- `tests/test_modeller_budget.py::test_reviewer_and_ai_tier_refused`: under an exhausted budget, both make no call and each says `budget:`.
- `tests/test_modeller_budget.py::test_modeller_calls_counted_once_in_run`: two 0.1 calls printed to a run whose `agent.ran` says 0.2 are charged 0.2. A failed call is charged its `unsaid` reserve.
- `tests/test_modeller_budget.py::test_only_listed_ai_starts`: the AST scan. It fails if a new module spawns `claude` or `$ERGOSTAT_AI` outside the allowlist. (lesson-8)

## Size budget

70 net lines
size: M (confidence: medium)
