# research-design-queues-research-sources-checked: A research answer is checked for evidence: its cited files and lines exist, its URLs were opened; an unsourced answer is asked again once

depends-on: []

Problem: the research queue promises "a written answer with evidence", but research.py takes any <report>. dev/bin/research.py:42-51 stores the ## Sources lines as they are and says research.answered even when there are none, or when they name a file that does not exist. The stand-in's answer is "Sources: none" (dev/bin/fac.py:670) and it passes. A planner (plan.py:312) and, later, the briefs then carry claims nobody can trace.

Change: research.py checks each source line before it says research.answered.
- A `path:line` or `path` source must exist in the session's clone at the sha it was cloned at, and the line must be within the file's length.
- A URL source must appear in the session's own tool calls: WebFetch urls, WebSearch result urls, or the walker's goto. These are read from the session item's tool_calls (dev/bin/sessions.py), which are folded when the session ends.
- An answer with at least one checked source is answered, with `sources_checked` (the checked ones) and `sources_unchecked` (the rest, with why).
- An answer with none says research.unsourced (a new state, unsourced), and the question is asked again once, with the reason in the brief. The second unsourced answer is research.dead (a new state, dead, which plan.py:304 and manage.py:295 already read).
- In the model: a flow research-unsourced, and research-answered counts only answered.

Definition of done:
1. A report citing an existing file and line is answered, with that source in sources_checked.
2. A report citing only a file that is missing, or a line past the end, is unsourced, and the item says which and why.
3. A URL the session never opened is unchecked. One it fetched is checked.
4. The second unsourced answer for one question makes it dead, and a planner waiting on it plans without it (plan.py's existing dead path).
5. The stand-in researcher's answer cites a real file, so the existing tests keep passing.
6. The researcher's prompt says sources are checked and how.

Files to touch: dev/bin/research.py, dev/bin/fac.py (STANDIN text), ergostat.yaml (the research kind's states and events), dev/model/knowledge.yaml (a flow, descriptions), dev/prompts/researcher.md, tests/test_factory_knowledge.py.

Acceptance tests (tests/test_factory_knowledge.py):
- test_research_source_file_and_line_checked
- test_research_missing_source_is_unsourced_and_asked_again
- test_research_url_checked_against_tool_calls
- test_research_second_unsourced_is_dead_and_planner_goes_on
- test_researcher_answers (existing, still passing)

Size budget: 120 net lines (code, YAML and prompt; tests excluded).

Area: research-design-queues. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1: all four acceptance tests and test_researcher_answers pass (named_tests.py, one file at a time), as
does test_the_knowledge_model_loads. Ruff is clean. Net 94 lines outside tests. Each guard was broken and its test
seen to fail: with the line bound loosened, test_research_source_file_and_line_checked failed; with a failed WebFetch
counted as opened, test_research_url_checked_against_tool_calls failed.

Choices made with nobody to ask (the most reversible one each time):
- The URLs are read from the session's own transcript (run/sessions/<item>-researcher-<n>.jsonl, the highest n),
  which holds the same lines the session item folds as tool_calls and tool_results. That file is complete once the
  session ends. The engine folds the item from it asynchronously (every 2 s), so the item could still be missing the
  last calls when research.py reads it (lesson-3). A WebFetch counts as opened only when its result came back with no
  error; a call that has no result counts as not opened.
- "The walker's goto": no walker exists in this repo. Any tool whose name ends in `goto` is read for its input `url`,
  the way WebFetch is.
- Dead: the engine never lets a run's own events leave an item `dead` (leases/dispatch.py moved_on). A lease's end
  puts the item back where it was taken from unless its attempts are spent. So each unsourced answer is given back
  *counted*, and the researcher's lease has `attempts: 2`: the first unsourced answer goes back to asked (its
  research.unsourced still counts in the flow research-unsourced), and the second, research.dead, is the lease's
  last attempt, a dead letter. The cost: a crashed attempt also counts, so a crash followed by one unsourced answer
  is dead too. Raising the lease's attempts would allow more re-asks than the one this gap promises. Fixing that in
  the engine is outside the gap's files. The fake ergostat in the tests folds the events and not the lease, so this
  engine path is reasoned from the code, not tested.
- An unsourced answer's report is kept as `unsourced_report`, not `report`, so a planner never reads an unchecked
  report (plan.py reads `report`). `unsourced` folds by sum. A dead letter that is redriven still has unsourced=2,
  so its next unsourced answer is dead at once.
- Not run: `uv run ergostat check` on the model (refused by the shell). The unit suite and the browser files were
  not run, per the brief.
