# finished-rule-in-series-and-routing: The process map, the state counts over time and message routing take their finished states from the one function, with their outputs proved unchanged or the change said

depends-on: [items-kinds-say-which-states-finish]

Problem: items-kinds-say-which-states-finish moves the finished rule into finish_of for the Items page, the dependency graph and the estimates, and leaves three other callers on their own rules: ergostat/process.py:75-83 (done_states, also stripping 'leased'), ergostat/series.py:338 and 371-398 (state counts over time) and a separate done_states in ergostat/messages/route.py:39. Until they agree, the Items page can call a state finished that the process map draws as a middle state, or that a message's done route does not treat as done.
Change: each of the three is read and compared with finish_of on every demo spec and the factory-shaped fixture. Where its set equals finish_of's (after its own stated extras, such as stripping 'leased'), it calls finish_of and keeps the extra as one named line. Where it differs on purpose (message routing's done may be a different idea: where a message's answer goes), it keeps its rule, is renamed so it no longer reads as the same thing (e.g. route_done_states), and one SPEC sentence says how it differs. Any change in output is listed in the PR per demo and kind.
Definition of done:
1. No function named done_states remains outside ergostat/spec/finished.py and spec/itemindex.py's inference that finish_of wraps.
2. A parity test: the process map's answer, /api/series state counts and message routing's targets are byte-identical before and after on the six demos' specs with seeded records, except for the differences listed in the PR.
3. SPEC says in one place which uses share the rule and which does not, and why.
Files: ergostat/process.py, ergostat/series.py, ergostat/messages/route.py, ergostat/spec/finished.py, docs/SPEC.md, tests/test_finished_states.py.
Acceptance tests: the parity test; a unit test per caller on a kind with declared done, inferred done and one state.
Budget: 70 net lines.

Milestone: items-page-readable. Owner items: 4 (one answer to 'which states are done', everywhere). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. Net +10 lines in ergostat/ (budget 70).

What each caller does now:
- **Process map** (`process._done`): `finished.ends_of`, i.e. `finish_of`'s finished states plus `dead` for a taken
  kind, none for a kind that lives on. These are the states the Items list hides (`items.hidden_states`). The old
  rule's stated extra (stripping `leased`) is already inside `finish_of`. The added `dead` is the one named line,
  kept because the old map ended a dead letter's item too and the Items list hides it.
- **State counts over time** (`series.finished_states`, `_flow_indexed`): `finish_of`'s finished states, with no
  `dead` (a dead letter is not finished work, so no cycle time ends there; the Items overview's "out" rate counts the
  same way).
- **Message routing**: keeps its rule on purpose, renamed `route_done_states` (the unused `p` argument is dropped).
  `finish_of` infers a state no item has left as finished. Routing calls such a state waiting while no item has gone
  past it, so a message about a review briefed and waiting for its reviewer still goes to the work.
  `tests/test_messages.py::test_work_that_finished_before_the_message_reached_it_is_missed_and_redone` failed when
  routing was switched to `ends_of`, which is how this came out. Keeping the rule was the more reversible choice:
  no routing target moves. SPEC §5a, *Which states are finished*, says which uses share the rule and why routing
  does not.

Differences in output, per demo and kind (all in `/api/items-flow`; the parity test's `CHANGED` lists them and
checks each new value): the process map and routing targets are byte-identical on all six demos.
- image-squeeze/hypothesis: finished `[leased, dropped, dead]` -> `[kept, dropped]` (declared `done` was not read).
- roadmap/epic `[underway, shipped]` -> `[shipped]`; roadmap/ticket `[leased, done, dead]` -> `[done]` (declared).
- the-job/ramp `[leased, proved-fine, dead]` -> `[approved, rejected, broke, proved-fine]`; the-job/review
  `[leased, answered, dead]` -> `[answered]` (declared).
- the-job action, alert, ci, doc, mention, pr, secret, team-pr, ticket, update: `[leased, X, dead]` -> `[X]`
  (inferred; X the kind's end state, as `_TAKEN` in the test names it).
- ticket-factory/report `[written]` -> `[]` (one state: lives on); ticket-factory/ticket `[leased, stopped, dead]`
  -> `[done]` (declared).
With the finished states, an items-flow answer's `finished` items and `median` follow from them.

Readings of the definition:
- "/api/series state counts" is read as `/api/items-flow` (series.py's state counts over time; `/api/series` reads
  no states).
- "The six demos": nothing defines six. The test uses `READERS_DEMOS` from test_diagram_rendering.py: first-loop,
  image-squeeze, roadmap, software-factory, the-job, ticket-factory.
- The parity fixture (`tests/fixtures/finished_parity.json`) holds a sha256 of each output, not the 428 KB of the
  outputs themselves. It was taken and committed with main's code (commit "finished parity: …") before the callers
  changed.
- On the seeded demos no kind with one state has an item, so the process map's change for such a kind (it no longer
  ends: a pool lives on) shows only in the unit test (`pool`), not in the parity list.

Findings left for other gaps (not fixed here):
- Routing's rule counts `leased` as finished for the-job's taken kinds and does not count their end state. Main's own
  snapshot of the old rule (`[dead, leased]`) shows this. So a message about an item a run holds goes to the
  `finished:` policy. That is a routing defect inside its own rule. It needs its own gap.
- `spec/about.py` (open items about a part) and the item index's in-memory set (`itemindex._open`) still call
  `itemindex.done_states`. SPEC says so. They are outside this gap's Files.

Tests: tests/test_finished_states.py (8, all pass). Each new test was seen to fail with the old rule put back in
process.py, series.py and route.py. Also passed: test_series, test_process, test_messages, test_item_index,
test_dashboards, test_remote_lines, test_intent, test_module_sparklines, test_conformance_lists_ergostat,
test_reload_in_place, test_items_overview. test_repair2: 18 passed, 31 skipped (bwrap cannot make namespaces in this
container). Browser, tests/test_items_page.py: 86 passed, 4 failed, none on this change:
- `test_a_lease_taken_or_ended_comes_and_goes_in_the_valves_panel` and
  `test_the_graph_and_the_timeline_left_open_change_nothing[timeline]` pass when run alone: load in the full file.
- `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` (the project switcher never lists the other
  project) and `test_every_surface_prints_the_servers_one_count_of_goals_off` (wants the heading "Loops ·", and
  pages.js on main says "Goals") fail alone too. They test the header and the switcher, which this branch does not
  touch. Running them on main itself was not possible: `git checkout main -- ergostat` was refused.
The other three browser files and demo_check were not run (no example touched).
