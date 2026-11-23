# what-is-holding-everything-up: the system's current constraints, ranked

The owner, 2026-11-22: "figure out what is holding up processes, figure out why certain things have not been done yet." Today's status lists 18 goals off with no sign of which one is holding the rest up.

Change: `ergostat held-up`, `GET /api/held-up`, MCP, and one line at the top of the page. It groups every unfinished item by its root cause (`why-is-it-not-done`) and ranks the roots by what they hold: how many items, how many hours of waiting, and the items that matter most by rank. The first line is the single biggest constraint, in words, with its next step: "The merge queue is held by a dead lease: 60 approved gaps are waiting. Release it with ...". Goals that are off only as a consequence of a root are folded under it. It distinguishes **normal queueing** from a **stall** (something that should be moving and is not), and says "nothing is stuck" only when that is true.

Definition of done:
1. On the fixtures of `why-is-it-not-done`, the true constraint ranks first.
2. The budget-guard stall and the dead-lease stall are each named as the first line, and a healthy busy system reports no stall.
3. A snapshot of 18 off goals with one root shows one root with the rest folded under it.
4. It answers in under 200 ms on a factory-size record.

## Where it stopped

Built in round 1: `ergostat/why/held.py` (every unfinished item's roots, worked out once each, grouped, classed and
ranked; the goals folded; the first line), `ergostat held-up [--json]`, `GET /api/held-up`, MCP `held_up`, the line in
the page's header (`#heldup`, from `/api/status`'s `held_up`), SPEC §5a *What holds the work up* and the agent guide.
`why` itself is unchanged in what it answers: its context can now read every item and link up front and work out a
block's answer once for all its items (used only by held-up), and two roots carry one more field each (`backoff` on a
give-back's wait, `dead` on a parked root). About 360 net lines of code outside tests, docs and dev.

Tests: `tests/test_held_up.py` (25): item 1 is
`test_on_the_fixtures_of_why_the_true_constraint_ranks_first` (13 of why's fixtures, each compared with what `why`
says for the item asked) and `test_a_stall_outranks_a_bigger_queue_and_each_item_counts_once_under_its_root`; item 2
is `test_the_dead_lease_stall_is_the_first_line`, `test_the_budget_guard_stall_is_the_first_line` and
`test_a_healthy_busy_system_reports_no_stall`; item 3 is
`test_eighteen_goals_off_with_one_root_show_one_root_with_the_rest_folded_under_it`; item 4 is
`test_factory_size_answer_under_200_ms` (87 ms here, best of 5). The page's line:
`tests/test_items_page.py::test_the_header_says_what_holds_the_work_up_in_one_line`.

The choices made with nobody to ask (each the most reversible):

- **Stall, held, queue, unknown.** A stall: a dead or stale lease, the budget refusing runs, a block failing or no
  engine, a cycle, a missing item, a dead letter, a state nothing takes, a parked item others wait on. Held on
  purpose: a gate reading 0 (a limit reached), a closed goal or intake, a person to answer, a parked item nothing
  waits on. Queue: work going on, a full pool of live runs, a give-back's wait. The table is `klass` in held.py, one
  place to change.
- **Ranking:** stalls first (then unknown, held, queue), then by the items waiting on the root, the items it holds and
  their hours of waiting. The definition lists what to rank by but not how to weigh it; a stall holding a few items is
  put above normal queueing of many, because the queueing is moving.
- **"The items that matter most by rank":** the model declares no rank of an item beyond its block's `takes: order:`,
  so each root names its first 5 items in the order its block would take them, then the longest waiting. They do not
  weigh the ranking.
- **A goal is off** by its last recorded crossing (`loop.off`), not by the status snapshot, so the CLI and MCP need no
  snapshot. A goal is folded under the root holding most of the unfinished items its stock's `items:` sensor counts. A
  goal whose part counts no items (a flow, a stock read some other way) is listed as not traced, never guessed onto a
  root.
- **The page's line** is in the header (no new panel), carried by `/api/status`, so no page makes a new request. It
  is worked out again when the record moves or after 30 s, and a failure is said in the line rather than failing the
  status.
- **The module's name** `held` hid the `held` function `why/__init__.py` imported from precedence (a submodule's import
  sets the package attribute), so that import is now `held as _held`. (Renaming the file was refused here: `mv`.)
- The `ergostat.*` kinds (ergostat's own upkeep: actions, claims, workspaces) are left out of "every unfinished item".

Tests run here: `tests/test_held_up.py` (25 pass), `tests/test_why.py` (33 pass), `tests/test_cli_fallback.py::
test_every_flag_of_a_read_topic_is_called_acting_or_read_only`, `tests/test_export.py` and
`tests/test_graph_cli_web.py` (49 pass; test_export's 2 page tests skipped there because plain `uv run` has no
Playwright, so they were not run here); ruff clean. Browser, under the watchdog: `tests/test_items_page.py` whole: 51
pass, 1 fails; `tests/test_page_refresh.py` and `tests/test_page_polling.py`: 28 pass, 1 fails. The two failures,
both unrelated:

- `tests/test_items_page.py::test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`, named in
  why-is-it-not-done's record as failing here too: it times out at line 1667, waiting 30 s for the project switcher to
  list the other project (`/api/projects`). Every header check before that line passes.
- `tests/test_page_refresh.py::test_other_pages_left_open_change_nothing[diagram?view=process&by=events-graph]`: the
  process map's `DIV` class and `H1` title change over three idle refreshes. It fails the same way with the header
  line switched off in util.js, and again with `held_up` taken out of `/api/status` as well (both put back after).
  The loops and agents cases pass.

`main` has not moved since the clone, so there was nothing to merge in.

Lesson 9, each broken by hand and seen to fail: the budget refusal no longer a stall (2 tests fail); stalls not ranked
first (2 fail); no goal folded (1 fails); the page reading no `held_up` (the browser test fails).
