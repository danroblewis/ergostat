# ui-from-items-to-the-process-map-and-the-map-says-h: From Items to the process map, and the map says how many are there now

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q57 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /items; /diagram?view=process (States)

**The problem:** Where work queues is shown only on the Process map, which Items does not link to; the map's node counts are visits ('18× · 16 items'), not how many items are in the state now; node text is about 8 px at Fit.

**The change:** Each kind's name on Items has a 'process map' link to /diagram?view=process&kind=<kind>&mode=states. In States mode each node shows 'now 3' before the visit count. The map fits at no less than 11 px text and says which way more lies.

**User stories it serves:** F3

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796/items the ticket kind has a link whose href contains 'view=process'; on that map every node contains 'now ' and a number equal to the Items legend's count for that state; no node label is below 11 px.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1, built (e776f836, docs ffedbdcf). Net 15 lines outside tests and docs (server.py +7, diagram.js +5,
pages.js +2, process.js 0, style.css +1).

What changed:
- Items (`pages.js`, `style.css`): each kind's card has a "process map" link after its name, to
  `/diagram?view=process&kind=KIND&mode=states`.
- The Diagram page (`diagram.js`) reads `kind` and `mode` as the Process view's `kinds` and `by`, so the link
  works as the definition writes it. This is the most reversible choice: the existing names are not renamed, and
  the address is rewritten to `kinds=`/`by=` on the next move.
- `GET /api/graph?view=process` (`server.py` `_process`), in States: each state node carries `now`, read from the same
  `spec.items.listing` counts the Items page shows. In the map (`process.js`), a node's second line reads
  `now 3 · 6× · 4 items`.
- Fit (`diagram.js`), for the process map only: scale at least 1, both first fit and the Fit button, so the 11px node
  text is never drawn smaller. The pan hint now says which way more lies ("More to the right and below"). The hint is
  shared by the three views, so the Dynamics and Blocks views say the direction too. I judged that part of "says
  which way more lies", not a new panel.
- SPEC §5b and DESIGN updated.

Narrower than the acceptance, on purpose: "every node contains 'now '" is held for every **state** node. The start
and end pills, and in States a kind with no states drawn by its events, are not states, have no count on Items, and
show no `now`. The test checks every state node, not the pills.

Test: `tests/test_diagram_rendering.py::test_items_links_each_kind_to_its_process_map_whose_states_say_how_many_are_there_now`
(the-job, 3 new / 2 explained / 1 answered). It reads the ticket card's legend on /items, follows the link, and
checks that each state node's sub-line starts `now N · ` with N the legend's count, that no node text is under 11px
on screen, and that at 760 px Fit keeps 11px and the hint says "to the right". Breaks made and seen to fail: fit floor
removed (7.9px), `now` text dropped, the server's `now` set to visits, hint text without a direction, `kind` alias
removed (the test now asserts the map asked for ticket alone). Not seen to fail: the `mode` alias removed. States
is already the default for ticket, so the test cannot tell; the link's href is asserted to carry `mode=states`.

Runs (each under suite_watch with Playwright):
- the new test: passed.
- tests/test_items_page.py: 21 passed, rc 0.
- ruff: clean.
- tests/test_diagram_rendering.py, run twice in full. First: 4 failed / 197 passed. Second: 8 failed / 193 passed.
  Of the second run's 8, I ran 6 alone on this branch:
  - 4 passed alone: test_every_lines_panel_links_to_the_parts_it_joins[image-squeeze] and [ticket-factory],
    test_a_valve_says_its_rate_inputs_and_equation_and_its_pipe_what_moves, and
    test_pages_are_ordinary_links_opened_in_new_tabs_reloaded_and_walked_back.
  - 2 failed alone: test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page (the Model page
    lacks "Nothing waiting." after an accept, which this branch does not touch) and
    test_a_big_tangled_model_lays_out_in_time_and_cleanly (Dynamics open=* drawn in 2892ms against a 2500ms
    bound; this branch adds only a hint text write per applyView and a Math.max(0, …) to that path).
  - Not run alone: the other 2, the routing-time failures of test_every_view_draws_cleanly_and_in_time[coordinator]
    and [image-squeeze] (open=* routed in about 40s).
  I could not run any of them on main: `git archive main | tar -x -C /tmp/mainsrc` and
  `git checkout main -- <the five web files>` were both refused in this session. So they are not shown to fail on
  main too; the factory's rerun on clean main should settle that.
- Not run here: the unit suite, test_page_polling.py, test_page_refresh.py. No main merge was needed: the branch was
  made from main and main has not moved in the clone.

### Round 1, after the factory's build step

The build step failed with rc 5: it ran `tests/test_diagram_rendering.py` (via affected_tests) without Playwright
installed, so the file was skipped at import (`could not import 'playwright.sync_api'`) and pytest collected no tests.
No test failed and no code is at fault, so I changed no code. Run again with Playwright under suite_watch, the gap's
test `test_items_links_each_kind_to_its_process_map_whose_states_say_how_many_are_there_now` passed (rc 0), and ruff
is clean. To check this page change, the build needs Playwright (`build_browser = true` or `--with playwright`).

### Round 1, after the factory's build step, again

The build step failed the same way: rc 5, `tests/test_diagram_rendering.py` skipped at import because Playwright
is not installed there, so no tests were collected and none failed. I changed no code: changing a test's bounds or
the build's configuration is outside this gap. Run again here with Playwright under suite_watch, the gap's test
passed (1 passed, rc 0) and ruff is clean. The build step can only check this page change if it has Playwright
(`[suites] build_browser = true`, or `--with playwright`).

### Round 2

No review findings to answer. I took the step main took for the same rc 5 (ab17bb6e): I added a unit test the build
can run without Playwright, so the build step now has a test to collect. No source changed this round.
`tests/test_graph_cli_web.py::test_the_process_maps_states_say_how_many_are_there_now_as_items_counts_them` copies
the-job, records 3 new / 2 explained / 1 answered tickets, and checks that `/api/graph?view=process&kinds=ticket&by=states`
gives each state node a `now` equal to the count `/api/items` gives that state, and that `by=events` gives no node a
`now`. It covers the server half only; the browser test still covers the page. It was seen to fail when I set the
server's `now` to the node's visit count (`x["count"]`); with the code put back, it passes.

Runs: tests/test_graph_cli_web.py 33 passed; the gap's browser test, under suite_watch with Playwright, 1 passed
(rc 0); ruff clean. Not run: the build command itself (`suite_watch -- affected_tests -- pytest -n 8`) was refused
in this session, so I ran the files it would pick one at a time. tests/test_graph_cli_web.py is new to that
selection, because the branch now changes it. Also not run: the unit suite, the four browser files in full, and
test_items_page.py again. Main has not moved since the merge at 2a565036.

### Round 3

The only finding was the merge conflict with main (tests/test_graph_cli_web.py, and also pages.js). I resolved it in
107a2f0b and kept both sides. In pages.js, the Items card keeps main's new chart arguments (`k.finished`, `k.paused`,
`k.finished_from`, `kind: k`) and the branch's `pm` process-map link after the name. In tests/test_graph_cli_web.py,
both tests are kept: main's side-panel ellipsis test and the branch's `now` test. No source changed beyond the merge.

Runs after the merge:
- ruff: clean.
- tests/test_graph_cli_web.py: 41 passed.
- The gap's browser test, under suite_watch with Playwright: 1 passed, rc 0.
- tests/test_items_page.py, under suite_watch with Playwright: 6 failed / 25 passed, rc 1.
  I reran three of the six alone and all three failed again:
  - test_a_stocks_and_a_flows_side_panel_list_their_items_and_link_to_exactly_that_set: no
    `#detail .item-set table.item-list` in a Dynamics side panel.
  - test_the_model_changes_are_found_by_heading_search_and_panel.
  - test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart: no `#project` option for the second
    project.
  The other three are not named: the output was truncated, and a piped rerun to list them was refused.

  I judge these unrelated to this gap. The branch's diff against main is server.py (`now` on process-map state
  nodes), diagram.js (the pan hint's words, the process-only fit floor, the `kind`/`mode` aliases), pages.js (one
  link), process.js (one label) and style.css (one rule). None of it touches the Dynamics side panel's item sets
  or the header's project picker. That is not shown on main, though: `git worktree add --detach /tmp/mainwt main` was
  refused in this session. The factory's rerun on clean main should settle it.
