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

## Where it stopped

Round 1, 2026-11-22. **Nothing built**: only this note. No code, docs or tests changed.

**Why: its dependency is not in this branch's base.** `depends-on: [ai-calls-ask-the-budget]`, and that gap's work is
missing from the clone (made from main at ae7bdc89). Checked like this:
- `ergostat/decisions/ai.py` has no reservation: `call` runs its command with only its own `--max-budget-usd`, and
  nothing in it imports `costs.budget`.
- `ergostat/costs/budget.py` has only the run permit (`permit`, `fold`, `recover`) and T1. It has no call
  reservation, and its fold has no counted-once rule for calls made inside a run.
- SPEC §9.9 "Limits, stated" still says the decisions extract, intent verdicts and redesigner calls are not covered.
  GAPS still lists "ergostat's own AI calls under the budget" as open.
- `tests/test_ai_calls_budget.py` does not exist.
- `git for-each-ref` lists two refs (this branch and its HEAD). Searching `git log --all -S` for the gap's name finds
  only the definitions, no code.

Point 1 of this definition ("the same way `ai-calls-ask-the-budget` does", "its counted-once fold") rests on that
work. So does `test_modeller_calls_counted_once_in_run`. Building the reservation and the fold here would build the
dependency inside this branch (lesson-13), and it would conflict once the dependency lands. Stopping is the more
reversible option. Resume once `ai-calls-ask-the-budget` is on main.

**Found for the resumption (the definition is unchanged; these are notes):**
- **Point 3's allowlist would fail on main as it stands.** These sites outside the listed places also start an AI
  command:
  - `ergostat/repair/fix.py:124` runs `decisions.ai.command(...)` through its own `subprocess.run`, under its own
    `repair/spend.jsonl` ledger.
  - `ergostat/spec/engine.py:66` (`AI_COMMAND`) starts an `ai` block's `claude`. The run permit covers it.
  - Check `ergostat/intent/ai.py` and `ergostat/bench/improvers.py` too.

  The scan needs those sites named (or routed through `decisions/ai.py`), or the definition needs a new round, before
  `test_only_listed_ai_starts` can pass honestly.
- `modeller.call`'s callers: `numbers/redesigner.py:294` (once per round), `numbers/reviewer.py:228`, and
  `modeller.answer` (the `modelling ai` tier, through `within`, which already stops on `modeller_spend.Capped`). A
  budget refusal can raise `Capped` with a `budget: …` message, so the tier stops rather than reading the refusal as
  an empty answer (lesson-3).
- `modeller.call` uses `subprocess.run` with no process group. A refused call must return before that line, so that
  no process starts.
