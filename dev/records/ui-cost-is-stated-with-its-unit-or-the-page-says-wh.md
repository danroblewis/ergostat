# ui-cost-is-stated-with-its-unit-or-the-page-says-wh: Cost is stated, with its unit, or the page says why it is zero

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q40 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /agents; agent panel; item header

**The problem:** Cost and tokens are '–' or '$0' for every agent with no reason; items show 'AI cost $0.0000'; there is no total; the words 'free stand-in' appear only on Check.

**The change:** A cost cell for an agent on a stand-in reads 'free stand-in, $0'. Add a total row for the window. The item header shows 'cost $0 (stand-in)' as the sum of its sessions. Hide a column that is empty for every row.

**User stories it serves:** D3

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8793/agents no cost cell is a bare '–' or '$0'; the table's last row starts with 'total'; /item/hypothesis%2F1 has 'cost' in its header line.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built. 34 net lines outside `tests/` and `docs/` (budget 60).

What changed:
- `/agents` (`ergostat/web/static/pages.js`, `util.js` `costText`): a cost cell with no dollars says why. It reads
  "free stand-in, $0" for an AI agent (ai, narrow-ai or decision rung) whose runs in the window had no AI session and no
  tokens, "no AI, $0" for another kind's runs, "no runs, $0", "not run here", or "a person, not priced". Tokens with
  no dollars read "not priced", never $0. The table ends in a `total` row: the runs column summed, dollars summed (or
  "$0: no AI cost recorded"), tokens and CPU summed, the largest peak memory. A tokens, CPU or peak-memory column that
  is empty for every agent is left out.
- Agent panel (`details.js`): the totals line and each run's cost cell use the same words.
- Item header (`server.py` `_item_cost`, `pages.js`): a "Cost" entry for any item that a run took. The runs are the
  ones named on its `ergostat.lease.taken` events, and their cost is the sum of their `agent.ran` and `agent.failed`
  ends (matched by `causedby`). While none has ended it says "not known yet", never $0 (lesson 3), and it says how many
  of the runs have ended.

Decisions taken alone, each the most reversible one:
- An item's "sessions" are read as the runs that leased it, because nothing else in the record ties a run to an item
  in general. In image-squeeze the `session/*` items do not name their hypothesis. The item header uses the agents'
  wording ("free stand-in, $0"), not the definition's "cost $0 (stand-in)", so one phrase means one thing everywhere.
- "Stand-in" is inferred: an AI-rung agent whose runs reported no session and no tokens. Ergostat cannot see that
  `bin/ai.sh` ran a stand-in program, so an AI block whose run failed before its session began also reads as one.
- Only the tokens, CPU and memory columns can be hidden. The cost column stays, since every row now says something.
- The item's leases are read from the latest 500 events in its detail. An item whose lease events were rolled up into
  a snapshot shows only the runs still in those events.
- The tokens cell stays '–' for an agent without AI when other agents have tokens. The cost cell beside it says why.
- SPEC §9.1 and the agent guide (§3b) now say this.

Tests: `tests/test_agents_page.py::test_the_agents_table_ends_in_the_windows_total_and_no_cost_is_bare` (new; checks
the total runs and dollars against the rows) and the updated `test_the_agents_page_shows_costs_...` (a program reads
"no AI, $0", a new AI stand-in block reads "free stand-in, $0").
`tests/test_items_page.py::test_cost_is_stated_or_says_why_it_is_none_with_the_windows_total_and_on_an_item` is the
acceptance, on image-squeeze: no bare cost cell on /agents, the last row "total", empty columns left out, and
/item/hypothesis%2F1's header has its cost. It then ends one of hypothesis/2's runs without a session and checks
that header reads "free stand-in, $0".

Each guarded piece was broken once and the tests were seen to fail: costText falling back to bare `usd()` (both new
tests), the total row renamed (both), column hiding turned off (the items test), the server's `cost` dropped (the
items test, timeout), and the stand-in branch never taken (the agents page test).

Run, with Playwright under the watchdog: tests/test_agents_page.py (4 passed), tests/test_items_page.py (22 passed),
tests/test_page_polling.py (17 passed). Unit: tests/test_graph_cli_web.py, tests/test_snapshot_sets.py,
tests/test_leases.py (all passed). Ruff is clean. Not run here: tests/test_diagram_rendering.py,
tests/test_page_refresh.py and the whole unit suite (the factory and the merge queue run them). Main has not moved
since the clone (merge-base is main), so there was nothing to merge. The unit run under `scripts/suite_watch.py` was
refused (`uv run python scripts/suite_watch.py -- uv run python scripts/named_tests.py tests/test_graph_cli_web.py
tests/test_snapshot_sets.py tests/test_web_access.py`), so those files ran without it, one at a time, and
tests/test_web_access.py was not run.
