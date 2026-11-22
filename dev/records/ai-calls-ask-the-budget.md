# ai-calls-ask-the-budget: every AI call made through `decisions/ai` (decisions extract, intent verdicts, the architecture review) reserves from the day's budget first, is refused when it is gone, and is counted once
depends-on: [run-budget-reserve]

## Definition of done

Builds on the P3 permit (`ergostat/costs/budget.py` from `run-budget-reserve`). With `budget:` declared in `ergostat.yaml`:

1. **A call asks first.** Every call that `ergostat/decisions/ai.py` makes, for `decisions extract`, the intent judge's verdicts (from `Engine.judge` and `ergostat intent judge`) and `improve --architecture` (`vsm_review`), reserves under the same flock as P3: a read, a decision and a write. The reservation is the call's own per-call cap. A call with no cap reserves `max-cost` and is run with `--max-budget-usd` at that amount. When `spent + reserved + reserve > daily`, or the reserve is not finite and positive, or the reserve is over `daily`, or the record cannot be read, the call is refused. No AI process is started, and a `budget.refused` is written (the P3 rate limit applies).
2. **Refusals are said, and nothing is lost.**
   - `decisions extract` stops before the call, and its `stopped` note starts `budget:`.
   - An intent verdict that is refused writes no verdict. The work stays due, the pass stops, and the next pass with room judges it.
   - The architecture review lists the system as not reviewed, with why `budget: …`.
3. **The end is recorded.** Every reservation that started a call gets a `budget.closed` with the call's reported cost. That includes a call that raised, timed out or got a malformed cost: its cost is null and it is charged its reserve. A call whose process died with it is closed by P3's `recover`, like a run.
4. **Counted once.** A call made inside a reserving run belongs to that run. That covers a run whose `ERGOSTAT_RUN` names a reserving start, and `Engine.judge`'s own pass, whose `agent.started` now carries `reserve: 0` and its `pid`. The run is charged once: its own charge, plus the calls whose cost its end does not already include. A call with no enclosing reserving run is charged on its own. The intent judge's `agent.ran` `cost_usd` and its verdicts' calls are therefore not both counted.
5. Without `budget:`, nothing changes. SPEC §9.9 and the agent guide narrow P3's "not covered" list to what is left. The GAPS entry says what is left (the modeller's calls and `ergostat.toml`). The house rules are met.

## Relation to other work

- `run-budget-reserve`: waits for it. This plan reuses its flock, fold, `refused` and `recover`.
- `run-budget-trip`: it also edits `costs/budget.py` and `spec/engine.py`. This plan adds to the fold and changes only `Engine.judge`, so merge main and rerun.
- `engine-runs-its-shard-join-1`: it edits `spec/engine.py`. This plan changes only `Engine.judge`'s start event.

## Files to touch

- `dev/records/ai-calls-ask-the-budget.md` (new)
- `ergostat/costs/budget.py`
- `ergostat/decisions/ai.py`
- `ergostat/decisions/extract.py`
- `ergostat/intent/judge.py`
- `ergostat/numbers/vsm_review.py`
- `ergostat/spec/engine.py`
- `docs/SPEC.md`, `docs/AGENT-GUIDE.md`, `docs/GAPS.md`
- `tests/test_ai_calls_budget.py` (new)

## Risks

- lesson-1: two calls, or a call and a block run, each read room for one before the other writes. The flock must span the read, the decision and the reservation.
- lesson-3: a call that raises, times out or reports a NaN or negative cost must be charged its reserve, never 0. An unreadable record refuses.
- lesson-5: a refused verdict stored as `unjudged` would mark the work as judged, so it would never be judged again.

## Acceptance tests

- `tests/test_ai_calls_budget.py::test_extract_refused_when_budget_gone`: spent is at `daily`. A stand-in `$ERGOSTAT_AI` that counts its starts is never started. `budget.refused` is written, and the note says `budget:`.
- `tests/test_ai_calls_budget.py::test_refused_verdict_stays_due`: an `Engine.judge` intent pass under an exhausted budget makes no call and stores no verdict, and the work is still in `due()`. With room, the next pass judges it. (lesson-5)
- `tests/test_ai_calls_budget.py::test_call_lock_spans_write`: room for one call. A competing block-run permit is started from the monkeypatched `budget._between`. The result is exactly one reservation and one refusal, and the test fails with the flock removed. (lesson-1)
- `tests/test_ai_calls_budget.py::test_call_unknown_cost_charges_reserve`: the stand-in raises, times out, or prints NaN, -1 or no cost. Each time `budget.closed` has null cost and the call is charged its reserve. (lesson-3)
- `tests/test_ai_calls_budget.py::test_call_counted_once_in_run`: an intent pass whose `agent.ran` says 0.2, made of two 0.1 calls, is charged 0.2. A 0.1 call inside a reserving run whose end says 0.3 and does not include it is charged 0.4 in total.
- `tests/test_ai_calls_budget.py::test_uncapped_call_reserves_max_cost`: a call with no cap reserves `max-cost` and is run with `--max-budget-usd` at that amount. A cap over `daily`, or a non-finite cap, is refused.
- `tests/test_ai_calls_budget.py::test_orphan_call_closed_by_recovery`: a call reservation whose pid is dead is closed by `recover` and charged its reserve.
- `tests/test_ai_calls_budget.py::test_no_budget_calls_unchanged`: without `budget:`, calls write no reservation and run as before.

## Size budget

140 net lines
size: M (confidence: medium)

## Notes from the plan review (answer each)

- ergostat/intent/judge.py:33-36 writes record.asked before ai.judge calls, and due() (judge.py:50,62) skips any work with a stored verdict, including state 'asked'. A reservation refused inside decisions/ai.py's call therefore leaves the work out of due() for good, and test_refused_verdict_stays_due fails. Take the permit in judge_one/run before record.asked, return the refusal as a distinct result that stops run's loop (judge.py:95), and add ergostat/intent/ai.py to the files to touch: ai.judge (line 116) calls call() with no state dir, spec or run id.
- Point 4 gives the outcome (0.2, not 0.4; 0.3+0.1) but no fold rule. P3's fold charges each run's ends and each reservation independently, and nothing marks whether an end already includes a call (Engine.judge's agent.ran sums its verdicts in process; a subprocess run's end does not). Taking the judge's agent.ran total also fails open: a call that raised or timed out adds 0 to Spent.cost_usd (decisions/ai.py:144-148), so the run's total is below its calls' charges. State the rule: the call reservation records its enclosing run and whether that end includes it; the run is charged max(its end's charge, the sum of its included calls' charges) plus its calls that are not included. Extend test_call_counted_once_in_run with a judge pass where one call raised.
- run-budget-reserve is not on main (origin/factory/run-budget-reserve, stopped after round 3). Its permit() takes a block and block-level max_cost, and refused() rate-limits per block name, so a per-call reserve and a refusal name for each call (extract, intent judge, architecture review) are new code. Build against its merged form, not the branch.
- 140 net lines is tight: the state dir, spec and enclosing run must be passed through extract.py, decisions/ai.extract, intent/ai.judge, judge.run/judge_one and vsm_review.review, plus fold, recover and the Engine.judge start event.
- ai.extract caps each call at max(0.05, min(2.0, cap - spent)) (decisions/ai.py:221). The reservation must be that same number, and the call must pass --max-budget-usd even when $ERGOSTAT_AI is not claude (the capped=True path), or the stand-in's cost can pass its reserve.
- modeller-calls-ask-the-budget and toml-models-budget will need the same per-call permit. Put it in costs/budget.py as a function they can reuse, and check whether either should depend on this gap.

## Where it stopped

Round 1 stopped before any code: the gap this one depends on is not in the clone.

- `depends-on: [run-budget-reserve]` is not met. On `main` (c1d10970) and on this branch there is no
  `ergostat/costs/budget.py`, and `ergostat/costs/` holds only `__init__.py`, `ai.py`, `prices.py`, `record.py` and
  `sampler.py`. Nothing in `ergostat/` reads a `budget:` key or has `permit`, `held`, `refused` or `recover`. SPEC has no
  §9.9 P3 section and no "not covered" list to narrow. Checked with `git for-each-ref`: the only refs are
  `refs/heads/main` and `refs/heads/factory/ai-calls-ask-the-budget`, so there is no `origin/factory/run-budget-reserve`
  here either. `git diff --stat main HEAD` shows only this file.
- The plan review says to build against P3's merged form, not its branch, and the house rule says a missing dependency is
  reported, not built here. Writing P3's flock, fold, refusal and recovery in this branch would build
  `run-budget-reserve` inside this gap and blow the 140-line budget. That is the least reversible choice, so I did not
  take it.
- What is left: all of it (points 1–5 and the eight acceptance tests). Resume once `run-budget-reserve` is on main. The
  plan review's notes still stand for that round: take the permit before `record.asked` in `intent/judge.py` and add
  `ergostat/intent/ai.py` to the files; write the counted-once fold rule (each call reservation records its enclosing run
  and whether that run's end includes it; the run is charged max(its end, the sum of its included calls) plus its
  calls that are not included); make the reserve equal to `ai.extract`'s per-call cap and always pass `--max-budget-usd`;
  put the per-call permit in `costs/budget.py` where `modeller-calls-ask-the-budget` and `toml-models-budget` (which
  already depends on this gap) can reuse it.
- No code was changed, so no tests were run.
