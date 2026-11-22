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

## Where it stopped

Parked by the factory (review/ai-calls-ask-the-budget-1, 2026-11-22 00:02).

Done: only the definition of done and a 'Where it stopped' note (dev/records/ai-calls-ask-the-budget.md). Left: all of it, points 1-5 and the eight acceptance tests in tests/test_ai_calls_budget.py. It stops because it depends on run-budget-reserve's P3 permit (costs/budget.py: flock, fold, refused, recover), and the plan review says to build on its merged form. That gap's branch exists (origin/factory/run-budget-reserve 8e4f2923), but this branch's base does not contain it. The record's claim that the ref is absent from the clone is wrong and should be corrected when work resumes.

## Where it stopped

Continued (gap/ai-calls-ask-the-budget-continued, round 1). Built: points 1–5 and the eight acceptance tests, plus one more.

- **Correcting the earlier record.** The first note above said `origin/factory/run-budget-reserve` was absent from the
  clone. That was stated from `git for-each-ref` in that clone alone, which lists no remote-tracking refs, so it said
  nothing about the ref existing elsewhere. The factory's parking note says the ref exists (8e4f2923). In this round's
  clone, `git for-each-ref` again lists only `refs/heads/main` (5617e225) and this branch. But `main` now holds the
  merged P3 (`ergostat/costs/budget.py`, SPEC §9.9), and `git merge-base --is-ancestor main HEAD` holds (e7d14d64
  merged it). So this round builds on P3's merged form, as the plan review asked.
- **The per-call permit** is `costs/budget.ask(p, spec, name, reserve)` and `budget.done(permit, cost)`, written so
  `modeller-calls-ask-the-budget` and `toml-models-budget` can reuse them. Both already declare
  `depends-on: [ai-calls-ask-the-budget]`, so no dependency was added. `ask` holds P3's flock across the fold, the
  decision and the write of a new `budget.call` reserving event (`reserve`, `pid`, `within`, `included`). It refuses
  on a non-finite, non-positive or over-`daily` reserve, or an unreadable record, and the P3 refusal is written per
  call name. `read` takes `budget.call` as a reserving event, so `recover` closes orphaned calls unchanged.
- **The counted-once rule** (plan review note 2) is in `fold`. A call's charge goes with its enclosing run only when
  `included`, and the run is charged max(its end, the sum of its included calls) plus the calls it does not include.
  `Engine.judge` sets `budget.WITHIN` (a context variable) to (its pass, included), and its `agent.started` carries
  `reserve: 0` and `pid` only when `budget:` is declared. Otherwise `$ERGOSTAT_RUN` names the run, if it is a
  reserving start, with `included: false`.
- **Note 1** (refusal before `record.asked`): `judge_one` asks before `record.asked` and returns `{"refused": …}`, and
  `run` stops its loop and reports `refused`. `ergostat/intent/ai.py` takes the permit. **Note 5** (reserve equals
  the extractor's cap): `ai.extract` reserves `left`, or `max-cost` when there is no cap. `ai.call(permit=…)` always
  forces `capped=True` at the reserve, and closes the permit in a `finally`. **Note 3**: built against the merged
  form. **Note 4**: 104 net lines, within 140.
- **Choices taken as the most reversible, with nobody to ask.** The calls are named `decisions-extract`, the judge's
  block name, and `architecture-review`. A refused review lists that system and the rest of the run as not reviewed,
  and writes no `ergostat.architecture.unreviewed` event, so a refusal is not counted as a failed call. A file outside
  the list was touched: `ergostat/cli/intent.py` (4 lines). It prints `refused: budget: …` and exits 1, so a refused
  pass does not say "nothing waiting to be judged".
- **Tests.** `tests/test_ai_calls_budget.py` has the eight named tests (13 cases with the parametrisations) and
  `test_architecture_review_refused_lists_not_reviewed`, which covers point 2's third clause. Each named one was seen
  to fail with its guard broken, then pass with it restored:
  - flock removed from `held`: both lock orders failed;
  - the included-calls rule disabled: counted-once failed (0.4 for 0.2);
  - `done` charging 0 for an unknown cost: all 5 cost modes failed;
  - `record.asked` moved before the ask: stays-due failed;
  - extract's refusal skipped: refused-when-gone failed;
  - `capped` not forced: uncapped failed;
  - recovery skipping calls: orphan failed;
  - review refusal skipped: architecture failed.
- **Run here:** the new file, test_run_budget, test_decisions, test_intent, test_vsm_review and
  test_architecture_review, all passing, and ruff clean. Not run here, as the house rules say: the full unit suite, the
  four browser files (no page is changed) and `demo_check` (no example is touched). No remote ref of main is in this
  clone to merge again beyond the local `main`, which is already in HEAD.

## Where it stopped

Continued (gap/ai-calls-ask-the-budget-continued, round 2). The finding to answer is the queue's: this branch was
the first failing merge of a batch of 5 (found by bisecting), and it failed again alone on
`tests/test_agents.py::test_each_queue_suite_runs_in_a_container_on_the_queue_cpuset_with_no_network`. No code was
changed this round. This branch did not cause that failure, and fixing it here would go outside the gap (lesson-13).

- **Nothing on that test's path is changed by this branch.** `git diff --stat main HEAD -- dev/bin tests/test_agents.py
  tests/test_factory.py ergostat.yaml schema` is empty. The test drives `dev/bin/queue.py` and `fac.suite` against a
  stand-in ergostat (`ERGOSTAT_CMD`) and a stand-in Docker. Of `ergostat/`, it only imports `ergostat.spec.read` on
  the unchanged `ergostat.yaml`. In this clone it passes alone (1 passed, 62 s).
- **Likely cause (read from the code, not reproduced).** `fac.suite` (`dev/bin/fac.py`, the `if box:` line) builds the
  container's `PYTEST_ADDOPTS` by *appending* `-o faulthandler_timeout=300` to the value it inherits. The queue runs
  the unit suite in its own container with exactly that variable set. So inside the queue, the test's child
  `queue.py` inherits it and passes `PYTEST_ADDOPTS=-o faulthandler_timeout=300 -o faulthandler_timeout=300`. The
  test's exact-element check (`"PYTEST_ADDOPTS=-o faulthandler_timeout=300" in flag(a, "-e")`) then fails. That would
  fail for any branch in the queue's container, `main` included. A bisect blames the first merge it tries, which
  fits. I tried to reproduce it by running the test with `PYTEST_ADDOPTS="-o faulthandler_timeout=300"` set, but the
  command was refused in this session, so the cause is not confirmed. The fix belongs in its own gap: either the test
  clears `PYTEST_ADDOPTS` from `f.env`, or `fac.suite` drops an inherited `faulthandler_timeout` before adding its own.
- **Run this round:** tests/test_ai_calls_budget.py (14 passed), tests/test_run_budget.py (36 passed), the named
  test_agents test alone (passed), and ruff (clean). Not run: the full unit suite and the browser files (house rules),
  and `demo_check` (no example is touched). The local `main` (5617e225) is already in HEAD, and there is no newer
  remote ref in the clone to merge.

## Where it stopped

Continued (gap/ai-calls-ask-the-budget-continued, round 3). The finding is still the queue's
`tests/test_agents.py::test_each_queue_suite_runs_in_a_container_on_the_queue_cpuset_with_no_network`. No code was
changed this round. The test is outside this gap (lesson-13), so it is reported here and not fixed.

- **Still nothing of this branch is on that test's path.** `git diff --stat main HEAD -- dev tests/test_agents.py
  tests/test_factory.py` shows only this record.
- **The cause, traced in the code this round (still not reproduced).** The option and its assertion came in together
  in `8212a01f` (2026-11-22, "A hung test is named from pytest's faulthandler stack…"). That commit reached `main`
  through `4a1bcd10` (Merge branch 'factory/a-queue-suite-that-stops-making') and is in HEAD. The steps:
  1. The queue runs the unit suite in a container with `-e PYTEST_ADDOPTS=-o faulthandler_timeout=300`
     (`dev/bin/fac.py:479-482`).
  2. The test's stand-in factory copies `os.environ` whole into its env (`tests/test_factory.py:184`), and the child
     `queue.py` is run with that env (`:242`).
  3. `fac.py:479` *appends* to the value it inherits, so the child's container gets
     `PYTEST_ADDOPTS=-o faulthandler_timeout=300 -o faulthandler_timeout=300`.
  4. The exact-element check at `tests/test_agents.py:325` then fails.

  With the variable unset, the test passes (round 2: 1 passed). It fails only inside the queue's own container, for
  any branch, `main` included. A bisect blames whichever merge it tries first.
- **The fix belongs in its own gap.** Either `fac.suite` drops an inherited `faulthandler_timeout` before it adds its
  own, or the test removes `PYTEST_ADDOPTS` from `f.env`. Until one of them lands, every branch fails this test in the
  queue.
- **Refused commands this round.** The reproduction,
  `PYTEST_ADDOPTS="-o faulthandler_timeout=300" timeout 300 uv run python -m pytest -q -p no:cacheprovider
  "tests/test_agents.py::test_each_queue_suite_runs_in_a_container_on_the_queue_cpuset_with_no_network"`, was refused
  (don't-ask mode). A shell `cat >> … <<EOF` append to this file, followed by `git commit`, was also refused, so this
  note was written with the editor instead.
- **Run this round:** tests/test_ai_calls_budget.py (14 passed), tests/test_run_budget.py (36 passed), and ruff (clean).
  Not run: the full unit suite and the browser files (house rules), and `demo_check` (no example is touched). The
  local `main` (5617e225) is the only ref of main in the clone, and it is already in HEAD.
