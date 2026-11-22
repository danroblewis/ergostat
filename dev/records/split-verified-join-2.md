# split-verified-join-2: `splits-covered` (renaming `split-quality`) and `split-budgets-held` measured; a covered parent merged without `merged_at`; a missing sub-gap judged short with no session; the second short parks; a taken join name never fatal
depends-on: []

## Definition of done
- **`splits-covered`.** `split-quality` is renamed `splits-covered` everywhere: `measure.py`, `dev/model/knowledge.yaml`, `dev/README.md`, `docs/roadmap/overnight/knowledge.md`, `docs/proposals/knowledge-graph.md` and `tests/test_factory_join.py`. After the change `git grep split-quality` finds nothing. It counts the parents whose first verdict (the first entry of `join_verdicts`, in list order and never chosen by `at`) falls in the 14-day window. It gives the share of them whose first verdict was `covered`. With none it gives no value (exit 1), never 0.
- **`split-budgets-held`.** Of the sub-gaps (gaps with a `parent`) merged in the window (`merged_at`), this is the share whose `net_lines` are at or under the net lines in the `## Size budget` of their own definition. The definition is read from where intake/brief find it. Each of these counts as not held: a missing or unreadable definition, no `## Size budget` section, a budget with no number, or a missing or non-integer `net_lines`. The `budget_of` default (600) is never used as a budget. With nothing to count there is no value (exit 1).
- Both are auxiliaries in `dev/model/knowledge.yaml` (system intake), each with a `measure.py` sensor like the other split measures.
- **Covered, not a merge of work.** When `plan.py join` judges a parent covered, the parent becomes `merged` with its verdict, `join_verdicts` and `judged_at`, but no `merged_at`. So cycle-hours, cost-per-merged and fix-rounds read the same before and after the judgment. `split-overhead` finds parents in the window by `judged_at` instead of `merged_at`. The existing split-overhead tests pass once their fixtures use `judged_at`.
- **Missing sub-gap, no session.** `join_brief` may show a sub-gap's definition or last review as `(missing: …)`, and this includes a child that is not in the record. In that case `plan.py join` makes no clone and no `fac.attempt` call. It records a `short` verdict at `ai_cost_usd` 0, with one point for each missing sub-gap that names it and what could not be read. It then takes the normal short path: a new sub-gap is requested, or the parent is parked.
- **The second short parks.** The first short verdict requests a new sub-gap and splits again. The second parks the parent. Its "Where it stopped" lists the points not built, one `- ` line each. The constant, the docstrings and `dev/prompts/join_judge.md`'s `most_short` text say so.
- **A taken name is not fatal.** The new sub-gap's name is `<parent-branch>-join-<n>`. If that is taken or not safe, the join uses the next unused safe name (`-join-<n+1>`, …, then `<parent-branch>-rest`, `-rest-2`, …) instead of raising. It stops with an error only after a bounded number of tries.
- `dev/README.md` and `docs/roadmap/overnight/knowledge.md` say that "covered" means the planner's coverage mapping plus an AI judgment at the join, not a proof. Both name `splits-covered` and `split-budgets-held`.

## Relation to other work
- gap/one-bad-link-never-stops-dispatch: avoids its files (`dev/bin/deps.py`, the dispatch code). This plan touches only `plan.py join`, `measure.py`, the model and the docs.
- gap/dod-measured-runs: may touch `measure.py`. This plan's changes are local to the split measures, so on a conflict, merge main and run the suites again.

## Files to touch
- `dev/bin/measure.py`
- `dev/bin/plan.py`
- `dev/prompts/join_judge.md`
- `dev/model/knowledge.yaml`
- `dev/README.md`
- `docs/roadmap/overnight/knowledge.md`
- `docs/proposals/knowledge-graph.md`
- `docs/GAPS.md`
- `tests/test_factory_join.py`
- `tests/test_factory_knowledge.py`

## Risks
- lesson-3: a missing definition, budget or `net_lines` could be read as held (for example through `budget_of`'s 600 default). A missing sub-gap could also still reach the AI judge, which might call it covered.
- lesson-2: the "first" verdict could be picked by the smallest `at` instead of by list order.
- lesson-8: the docs could call "covered" verified or proven. It is only an AI judgment against the coverage mapping.

## Acceptance tests
- `tests/test_factory_knowledge.py::test_split_measures`:
  - `splits-covered` does not count a parent covered only on its second judgment, even when its first `join_verdicts` entry has the later `at`.
  - With nothing in the window, `splits-covered` and `split-budgets-held` both exit 1 with no value.
  - `split-budgets-held` counts a sub-gap at exactly its budget as held. It counts each of these as not held: over budget, no definition, no budget section, a budget with no number, no `net_lines`.
  - Both measures are sensed in `dev/model/knowledge.yaml`.
- `tests/test_factory_join.py::test_join_moves_parent_to_joined_then_judge_merges`: the parent waits in `joined`, then the covered verdict makes it `merged` with `judged_at` and `join_verdicts` but no `merged_at`. Cycle-hours, cost-per-merged and fix-rounds read the same before and after the judgment, and `split-overhead` finds the parent by `judged_at`.
- `tests/test_factory_join.py::test_join_with_missing_sub_gap_definition_is_not_covered`: `fac.attempt` and `agents.clone` are patched to fail if called. One child has no definition and another is not in the record. The result is a `short` verdict at cost 0 with one point naming each, and a new sub-gap is requested.
- `tests/test_factory_join.py::test_join_not_covered_requests_new_gap_then_second_parks`:
  - The first short requests `<branch>-join-1`, even though a gap already holds that name, so the next unused safe name is taken.
  - The second short parks the parent in `joined`, with one `- ` line per point not built in "Where it stopped".
  - No third sub-gap is requested.

## Size budget
120 net lines
size: M (confidence: medium)

## Where it stopped
Built. Most of this definition was already on main from gap/split-verified-join-1: the rename to `splits-covered`, `split-budgets-held`, the two auxiliaries and their sensors, a covered parent with no `merged_at`, `split-overhead` by `judged_at`, a missing sub-gap judged short with no session, the second short parking, `most_short` in the prompt, and the docs' "not a proof" text. This branch adds what was still open:
- **A taken name is not fatal.** `plan.join_name` tries `-join-<n>` … `-join-<n+49>`, then `-rest`, `-rest-2` … `-rest-50`. It skips any name that is taken (as an id or a branch) or not safe, and raises only after those 100 tries. It runs only on the short path, so a covered parent or a park never fails on a name. Before, an unsafe name raised even when the verdict was covered. `dev/README.md` says so.
- **Tests.** `test_join_moves_parent_to_joined_then_judge_merges` now checks that `split-overhead` finds the covered parent, which has only `judged_at`. `test_join_with_missing_sub_gap_definition_is_not_covered` adds the combined case: one child with no definition and another not in the record give two points and a new sub-gap. `test_split_measures` adds a budget with no number, a non-integer `net_lines`, and `splits-covered` with only an out-of-window judgment, which gives no value. A new test, `test_a_taken_or_unsafe_join_name_takes_the_next`, covers the next name, the `-rest` fallback and the bounded error.
- **`git grep split-quality`.** It still finds the old name, but only in definition records (`docs/roadmap/overnight/split-verified-3.md`, `dev/records/split-verified-join-1.md` and this file). Those files may only be appended to, so they were left as they are; this was the reversible choice. The last test line that held the old name (in `test_split_measures`) was removed. No code, model or doc file names it.
- `docs/GAPS.md` has no entry for this gap or its parent, so it was not changed.
- **Round 2: the queue's browser failure.** The queue's run of the four browser files had 2 failures, each a Playwright `TimeoutError` in `_sync_base.py`. It named no test, and the run was under heavy load (550 threads, 4.1 GB RSS, 43 processes). This branch changes no page, no server code and nothing the browser files import. It changes only `dev/bin/plan.py`, its tests, `dev/README.md` and this record. None of `tests/test_*page*.py` or `tests/test_guide.py` mentions `plan.py`, `measure.py`, `join_name` or the split measures. So this branch did not change any code; it was the reversible choice. The browser files were not rerun here: the attempt to check for a local Playwright install was refused, and the instructions keep the four browser files for the queue. The failure is unrelated to this gap (lesson 13). Because no test was named, it could not be reproduced or traced to a race or a fixed sleep (lesson 10). It should be triaged in the queue on clean main. The branch already contains main at 5617e225 (no newer main in this clone). `test_factory_join.py` (13 passed), `test_factory_knowledge.py` (76 passed) and ruff are clean.
- **Round 3: `tests/test_agents.py::test_each_queue_suite_runs_in_a_container_on_the_queue_cpuset_with_no_network`.** The cause is the queue's environment, not this branch. Run alone here, the test passes (1 passed in 63 s). Read from the code: `fac.suite` (`dev/bin/fac.py:479`, from main's 8212a01f) adds `-o faulthandler_timeout=…` to whatever `PYTEST_ADDOPTS` it inherits. It then passes the result into the queue's container as `-e PYTEST_ADDOPTS=…` (line 482). The unit suite, and this test with it, runs in that container. The test's `Factory` copies `os.environ` (`tests/test_factory.py:184`), so the inner `fac.suite` inherits `-o faulthandler_timeout=300` and gives `-o faulthandler_timeout=300 -o faulthandler_timeout=300`. The exact check at `tests/test_agents.py:325` then fails. The failure is the same every time, not a load effect, and it would happen in the queue for any branch, main included. This branch changes none of `fac.py`, `agents.py` or `queue.py`, and `queue.py` does not import `plan.py`. So nothing was changed for it (lesson 13). The fix belongs in its own gap: either the test drops `PYTEST_ADDOPTS` from the `Factory` env, or `fac.suite` stops adding the option a second time. Not verified: the command that would show the failure here was refused, `PYTEST_ADDOPTS="-o faulthandler_timeout=300" timeout 600 uv run python scripts/named_tests.py tests/test_agents.py::test_each_queue_suite_runs_in_a_container_on_the_queue_cpuset_with_no_network`, and so was the shell heredoc used to append this text.
