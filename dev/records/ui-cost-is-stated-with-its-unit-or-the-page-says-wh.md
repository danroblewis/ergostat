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

Round 2: built. 40 net lines outside `tests/`, `docs/` and `dev/` (budget 60).

Merge of main (277a9c6c): conflicts in `pages.js` and `tests/test_agents_page.py`. Kept main's group heading (kind ·
count, rung as small text). Its colspan is the branch's `6 + nums.length`, since a hidden column must not widen it.
Both tests are kept. Main's test said the "ai" group has 2 rows, but the branch's fixture adds the stand-in `drafter`,
so it now expects 3.

The review's finding (lesson 3 / 8): an AI run with no `ai` data that failed or was killed showed a definite $0.
- `costs/record.py` `totals()` now also gives `unknown`: the runs with no cost that failed, were stopped (an
  `agent.ran` with a note: a stopped run is not written as `agent.failed`) or exited other than 0.
- `costText` (util.js): for an AI-rung agent with any such run, a cost of none reads "not known: N failed or stopped",
  and dollars known read "$X + not known: N failed or stopped". The per-run cell in the panel (details.js) uses the
  run's own `failed`, `note` and `exit`. The /agents total row says the same over the AI agents. The item header goes
  through the same `totals()` and `costText`, so it says "not known" too.
- A program or rule block's failed run still reads "no AI, $0". That kind has no session to spend.
- SPEC §9.1 and the agent guide say this.

Tests: `tests/test_run_costs.py::test_a_run_with_no_cost_that_failed_or_was_stopped_is_counted_as_not_known` (unit:
failed, stopped, exit None, a failed run with a known cost). The items acceptance test now also ends hypothesis/2's
second run as `agent.failed` ("killed (a timeout?)", no `ai`) and checks that the header reads "not known: 1 failed or
stopped" and has no "$0". Broken and seen to fail: the "not known" branch in costText never taken (the items test
timed out waiting for "not known"), and `unknown` counting only `agent.failed` (the unit test failed).

Run: tests/test_items_page.py (22 passed) and tests/test_agents_page.py (5 passed), with Playwright under the
watchdog, rc 0, and tests/test_page_polling.py (17 passed, rc 0). tests/test_run_costs.py (16 passed). Ruff is
clean. Not run here: test_diagram_rendering.py, test_page_refresh.py and the whole unit suite (the factory and the merge queue run them).

Round 3: built. 41 net lines outside `tests/`, `docs/` and `dev/` (budget 60).

The review's blocking finding (lesson 3 / 9): the panel's per-run cost cell (details.js `costOf`) left out the run's
exit, note and failed, so `costText`'s fallback read `undefined !== 0` as a failure and every good stand-in run read
"not known: 1 failed or stopped". `costOf` now takes the event and passes `exit`, `note` and
`failed: e.type === "agent.failed"`. A run event with no `exit` at all still counts as not known. That is the worst
case (lesson 3), and the engine writes `exit` on every end.

New browser test: `tests/test_agents_page.py::test_a_stand_in_agents_panel_reads_free_for_a_good_run_and_not_known_for_a_killed_one`.
It opens drafter's panel and checks that its 10 recent good runs all read "free stand-in, $0". It then adds a run ended
as `agent.failed` (exit -9, "killed (a timeout?)", no `ai`) and checks that the newest row reads "not known: 1 failed or
stopped" while the others still read "free stand-in, $0". It is last in the file because it adds that run to the
shared fixture's record. Broken and seen to fail: with `costOf` again leaving out exit, note and failed, the test failed
on its first assertion with all 10 rows "not known: 1 failed or stopped". That is the bug the review found.

The non-blocking finding (round 2): the `_item_cost` unit test used the string rung 'stand-in'. It now uses int rungs as
the model has them (worker 1, tidy 4). It also checks that leases by agents of two different rungs give no one rung.

Run: tests/test_agents_page.py (6 passed, rc 0) and tests/test_items_page.py (22 passed, rc 0), with Playwright under
the watchdog. tests/test_run_costs.py (16 passed). Ruff is clean. Main has not moved since the clone (the merge-base is
main, 277a9c6c), so there was nothing to merge. Not run here: test_diagram_rendering.py, test_page_refresh.py,
test_page_polling.py and the whole unit suite (the factory and the merge queue run them).

Round 4: built. The branch's code is as in round 3 (41 net lines outside `tests/`, `docs/` and `dev/`, budget 60).
This round is the merge of main (bf6dbebf).

The queue's finding, conflicts with main, resolved (commit a94b2210):
- `server.py`: an item's answer keeps main's `kind_of.final` and adds the branch's `cost`.
- `details.js`: main's new runs table (when, item, outcome, outward actions asked, cost; resources behind a
  disclosure) is kept. Its cost cell is the branch's `costText` over `costOf(e)`, which carries the run's exit,
  note and failed. Both tables call `costOf(e)`.
- `pages.js`: main's table is built first, then `holdStill` or `patch` (main's hold while the pointer is on a row).
  The branch's `nums` columns and the `total` tbody are inside it.
- `tests/test_agents_page.py`: both sides' tests are kept. `panel_costs` and the stand-in test now read
  `#detail .runs-table > table`, since main moved the cost there (still the fifth cell).

The stand-in panel test then failed after the merge: the killed run never showed. The cause was the test, not the
page: the server keeps a snapshot 1.5 s (`Live.snapshot`), and the panel opened right after the write read one made
before it (`/api/status` `at` was a second before the event). The test now waits until `/api/agents/drafter` counts
the failed run, then opens the panel (no fixed sleep). Broken again and seen to fail: with `costOf` leaving out exit,
note and failed, the test failed on its first assertion (all 10 rows "not known: 1 failed or stopped").

Run, with Playwright under the watchdog: tests/test_agents_page.py (9 passed, rc 0). An earlier run of that file
once failed `test_each_row_says_how_it_is_engaged_and_which_goal_it_serves` (main's, untouched). It read `#detail`
while it still said "Loading…", because it waits only for the panel's h2, which the loading panel shows already. It
passed on the next run. It is a race in that test and not part of this gap (lesson 13).
tests/test_items_page.py: 26 passed, 6 failed, the same six on two runs. The acceptance test
`test_cost_is_stated_or_says_why_it_is_none_with_the_windows_total_and_on_an_item` passes, alone and in the file.
The six failures are named here as unrelated, not fixed:
`test_a_stocks_and_a_flows_side_panel_list_their_items_and_link_to_exactly_that_set`,
`test_the_model_changes_are_found_by_heading_search_and_panel`, `test_a_valves_leased_items_are_listed_live`,
`test_a_snapshot_lists_a_parts_items_and_opens_its_set`, `test_a_set_left_out_of_a_snapshot_says_so`, and
`test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`. The panels of the first five stay at
"Loading…" with no page error. Two of them run in a file:// snapshot with no server, so the branch's server change
cannot reach them. The branch's JS differs from main only in the agent panel, the agents table and the new
`costText`. The sixth waits for the project switcher to list a second project. It was not confirmed that they fail on
clean main too: running main's copy (`git archive bf6dbebf | tar -x -C /tmp/mainwt`, then the test there) and
putting main's six ergostat files in place for one run (`git checkout bf6dbebf -- ...`) were both refused.
The factory reruns failing tests on clean main.
tests/test_run_costs.py and tests/test_snapshot_sets.py (20 passed). Ruff is clean. Not run here:
test_diagram_rendering.py, test_page_refresh.py, test_page_polling.py and the whole unit suite.

Round 5: built. The branch's code is unchanged since round 3 (41 net lines outside `tests/`, `docs/` and `dev/`,
budget 60).

The queue's finding (conflicts with main in `server.py`, `details.js`, `tests/test_agents_page.py`) was resolved in
round 4's merge (a94b2210). Main has since moved to ead497d1, and the factory merged it cleanly (fdea6b40), with no
conflict markers. The merge-base is now main. This round reran the tests on that merge.

Run, with Playwright under the watchdog:
- tests/test_agents_page.py: 8 passed, 1 failed, the same one on two runs:
  `test_each_row_says_how_it_is_engaged_and_which_goal_it_serves` (main's, which the branch does not change). It
  passes alone (rc 0, and its page-error check is empty). In the file it reads `#detail` while the panel still says
  "Loading…", because it waits only for the panel's h2, which the loading panel shows already. This is a race in that
  test (lessons 10 and 13), not a fault of the page, so it is not fixed here. All of this gap's tests in the file pass.
- tests/test_items_page.py: 33 passed, 1 failed: `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`
  (it waits for the project switcher to list a second project. The branch does not touch the switcher, and the test
  failed in round 4 too). Round 4's five other failures ("Loading…" panels) pass now that main is merged. The
  acceptance test `test_cost_is_stated_or_says_why_it_is_none_with_the_windows_total_and_on_an_item` passes.
- tests/test_run_costs.py (16 passed), tests/test_snapshot_sets.py (4 passed). Ruff is clean.

Refused commands, not worked around: the first watchdog run, given as `uv run python scripts/suite_watch.py -- uv run
--with playwright==1.63.0 python scripts/named_tests.py tests/test_agents_page.py 2>&1 | tail -8; echo rc=$?` (it ran
when given without the pipe). A scratch Playwright probe in /tmp (`timeout 120 uv run --with playwright==1.63.0 python
-I /tmp/probe/probe.py`) that would have timed the panel's load was also refused, and so was appending this section
with a shell heredoc. The run of the single test stood in for the probe. It was not confirmed that the two failures
happen on clean main too; the factory reruns failing tests there. Not run here: test_diagram_rendering.py,
test_page_refresh.py, test_page_polling.py and the whole unit suite.

Round 6: built. About 50 net lines in `ergostat/` against main (72 added, 22 removed), budget 60.

The review's blocking finding (lesson 3 / 8 / 9): a run given back unrun because its workspace pool was full
(`agent.ran`, the engine's PoolFull note, no session) counted as "not known: failed or stopped". So the leased `work`
agent would have read "not known: 19 failed or stopped" while its panel said "0 failed".
- `costs/record.py`: new `given_back(r)`, true for a run that is not `agent.failed` and whose note is the engine's
  pool-full note ("workspace pool … has none free for …", the same test as `segments._full`). `totals()` leaves those
  runs out of `unknown`, whatever their exit. A real give-back has `exit: None`, because the engine sets its note
  before any process starts (spec/engine.py: `refused` is raised as OSError before `Measured`).
- `util.js` `costText`: the per-run fallback (the panel's rows) applies the same rule.
- Only the pool-full give-back is left out. Any other note, a missing exit or a failure still counts as not known. Of
  the two choices this is the narrower and more reversible one, and it keeps the worst case for every other run
  (lesson 3). The engine's `failed` rule also leaves out the two stop notes, but a stopped run may have had a session
  that spent, so it stays "not known", as SPEC said before.
- SPEC §9.1, the agent guide and the `costText` comment now say a pool-full give-back is not one of them.

Tests: `tests/test_agents_page.py::test_an_ai_agents_runs_given_back_for_a_full_pool_read_free_not_unknown` (new, on
the `leased` fixture): `work`'s /agents cost cell reads "free stand-in, $0", the total row has no "not known", and
its 10 newest panel rows (all give-backs) read "free stand-in, $0" next to "19 refused (workspace pool full), 0
failed". The fixture's give-backs now carry `exit: None`, as the engine writes them (before, they had exit 0, which
the old rule's exit check alone would not have caught). `tests/test_run_costs.py::test_a_run_with_no_cost_that_failed_or_was_stopped_is_counted_as_not_known`
now also checks that two give-backs (exit None and 0) count 0, and that an `agent.failed` with that note still counts 1.
Broken and seen to fail: `given_back` always False (the browser test failed: the cell read "not known: 19 failed or
stopped", and the unit test failed `assert 2 == 0`). Then the JS `back` always false, with the server's fix in place:
the browser test failed with all 10 panel rows reading "not known: 1 failed or stopped".

Run, with Playwright under the watchdog: tests/test_agents_page.py: 9 passed, 1 failed, on two runs of the file:
`test_each_row_says_how_it_is_engaged_and_which_goal_it_serves` (main's). This round it fails alone too: it reads
`#detail` as "Agent × work Loading…", because it waits only for the h2 that the loading panel already shows. It
fails the same way with the fixture's give-backs put back to `exit: 0` (one run alone), so this round's fixture
change is not the cause. This round's code changes only the text of the cost cell, not when the panel loads. It is the
race named in rounds 4 and 5 (lessons 10 and 13) and is not fixed here.
tests/test_items_page.py: 33 passed, 1 failed (`test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`,
the project switcher, as in rounds 4 and 5). The acceptance test passes. tests/test_run_costs.py: 16 passed. Ruff is
clean. Main has not moved since the clone (the merge-base is main), so there was nothing to merge.
Refused, not worked around: a shell `for` loop running that one test twice (it ran once without the loop), and an
in-place edit of record.py and util.js by a Python heredoc (it was done with the editor instead). Not run here:
test_diagram_rendering.py, test_page_refresh.py, test_page_polling.py, test_snapshot_sets.py and the whole unit suite.

Round 7: built. The branch's code is as in round 6 (72 added, 22 removed in `ergostat/` against main, budget 60).
This round is the merge of main (7a905955), commit 4cfcd6a6.

The queue's finding, conflicts with main, resolved:
- `details.js`: main's `tableCaption` and `headRow` (a `thead`) on both runs tables are kept. Both rows still call
  the branch's `costOf(e)`, which carries the run's exit, note and failed (main's side had `costOf(e.data)`).
- `pages.js`: main's `sr-only` caption and `headRow` on the agents table are kept, with the branch's `nums` columns
  inside it. The group heading keeps main's `scope: "colgroup"` and the branch's `colspan: 6 + nums.length`, since a
  hidden column must not widen it. The `total` tbody stays last.
- `tests/test_agents_page.py`: both sides' tests are kept (the branch's total-row test, then main's `requests_site`
  fixture and its evidence test).
- After the merge, the branch's two panel tests waited for `table tr:nth-child(2)`. Main's `thead` makes that miss,
  since the head row is now in the thead and the run rows come after the caption. They now wait for
  `.runs-table > table > tr`, a run's row. Only the tests changed, not the page.

Run, with Playwright under the watchdog: tests/test_agents_page.py: 11 passed, 1 failed, main's
`test_each_row_says_how_it_is_engaged_and_which_goal_it_serves` ("Agent × work Loading…"). This is the race named in
rounds 4 to 6 (it waits for the h2 that the loading panel already shows), and it is not fixed here (lesson 13).
tests/test_items_page.py: 57 passed, 2 failed. One is `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`
(the project switcher, as in rounds 4 to 6). The other is new with this merge:
`test_actions_say_per_class_asked_approved_denied_and_whether_held`. It also fails alone: the Items page's
`.action-classes li[data-class="jira-transition"]` never shows within 20 s. The branch does not touch that path. Its
diff in `pages.js` is in pageAgents and pageItem only, and in `server.py` it is the item answer's `cost` and
`_item_cost`, not the items list or `actionClasses`. So it is named as unrelated, not fixed. It was not confirmed
on clean main here; the factory reruns failing tests there. The acceptance test passes. tests/test_run_costs.py: 16
passed. Ruff is clean.
Refused, not worked around: an in-place merge resolution by a Python heredoc (it was done with the editor), and a
rerun of the single items test piped through `grep | head` (it ran without the pipe). Not run here:
test_diagram_rendering.py, test_page_refresh.py, test_page_polling.py, test_snapshot_sets.py and the whole unit suite.
