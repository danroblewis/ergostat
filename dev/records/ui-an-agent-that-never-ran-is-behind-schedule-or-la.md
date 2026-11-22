# ui-an-agent-that-never-ran-is-behind-schedule-or-la: An agent that never ran, is behind schedule or last failed stands out

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q41 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /agents

**The problem:** improver: '0 runs, never ran, every 3m' in the same grey as everything else, with no reason. judge: 'not run here' with a blank runs cell beside 'every 30s', while its panel says 10 runs (about 120 expected).

**The change:** Mark such rows with a word in the alarm colour ('never ran', 'behind: 10 of ~120', 'last run failed') and a one-line reason under the row. The top line counts them ('2 behind schedule'). The list and the panel take their run count from one source.

**User stories it serves:** D4

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8797/agents the improver and judge rows each contain an element with the exception class and one of the three phrases; the page's top line contains 'behind schedule' or 'never ran' with a count; judge's runs cell equals its panel's count.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built. About 23 net lines of code (server.py +2, pages.js +15, style.css +4), within the budget.

- **What changed.** `/api/agents` (the listing) adds `expected`, the runs an `every:` asks for over the window's record
  (`min(window, recorded) // every`), and `span`. On /agents, each row that stands out gets a `span.exception` in the
  alarm colour (`--bad`) beside the name: "last run failed", "never ran", or "behind: N of ~M". A `tr.exception-why`
  under the row gives the reason. The ladder line adds counts ("1 never ran", "2 behind schedule", "1 last run failed").
  The runs cell now shows the window's count (`runs`, from the same `snap["agents"]` entry the panel's "in window"
  reads) for every agent, and no longer only for those run here. This replaces the old " failing" span.
- **Choices made without asking (the most reversible ones).** "Exception class" is read as a CSS class named
  `exception`. An agent counts as behind when fewer than half the expected runs are recorded, and only when at least
  4 were expected. Cron-only agents are never judged behind: only `every:` gives an expected count. They still show
  "never ran" or "last run failed". "Never ran" applies to an agent that runs itself or has an `every:`/`cron:` and has
  no `agent.ran`/`agent.failed` on record. A person with no schedule is never marked.
- **Acceptance test.** `tests/test_agents_page.py::test_an_agent_that_never_ran_is_behind_or_last_failed_stands_out`,
  in the page's own test file. It does not run against the live :8797 demo. A fixture shaped like that demo stands in:
  improver is a program every 3m that never ran; judge is a `type: judge` every 30s, not run here, with 10 runs in an
  hour of record; tidy last failed. I broke three things and saw it fail each time: `expected` sent as null, the runs
  cell back to blank for agents not run here, and the alarm colour taken off `.exception`.
- **Tests run** (each under suite_watch with Playwright, rc 0, nothing skipped): tests/test_agents_page.py (4 passed),
  tests/test_page_refresh.py (8 passed), tests/test_page_polling.py (17 passed). `ruff check ergostat tests scripts`
  is clean. Not run: the unit suite, tests/test_diagram_rendering.py and tests/test_items_page.py (neither covers
  /agents). `main` has not moved since the clone, so there was nothing to merge.

Round 1, after the build step: the build step has no Playwright, so `tests/test_agents_page.py` (the only file it
picks) was skipped whole at import, and pytest returned rc 5. The Playwright skip now sits in the `browser` fixture.
A new check that needs no browser, `test_the_agents_listing_sends_each_agents_runs_and_the_runs_asked_for`, reads
`/api/agents` on the standout fixture (judge 10 of 120, improver 0 of 20, tidy 1 asked for). With `expected` sent as
null it failed, as it should. No code outside `tests/` changed. Run: the file without Playwright (1 passed, 4 skipped),
with Playwright under suite_watch (5 passed, rc 0), and ruff (clean).
