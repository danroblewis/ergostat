# the-kind-page: The kind's page: its definition, where the model counts and moves it, its goals and loops, and its items

depends-on: [item-and-kind-footprint-proposal, kind-and-item-footprint-api, items-one-section-per-kind-closed]

Problem: owner item 15: 'no page representative of an item type ... its definition, the stocks and flows related to it, the feedback loops and control loops it takes part in, a well-designed filter, what all is this item?' Today the kind link goes to /items?kind=K (ergostat/web/static/pages.js:699), which only filters the list (shots/plan-ks-road-items-ticket.png): the description sits small on the system heading, the states are legend chips, and nothing names the kind's stocks, flows, taking blocks, goals or loops.
Change, as docs/proposals/item-and-kind-footprint.md decided (default: the Items page with exactly one kind chosen, at /items/<kind>, /items?kind=K redirecting with its other params, no new nav entry). Filled from /api/kinds/K, in order:
1. The kind's bar, drawn by the same kindBar function in static/kinds.js that the Items page uses, with the same markup (title, id pattern small, description, 'finishes: merged, closed' or 'lives on', state chips with counts, 'in <system>' with why on hover); here the title is the page's h1 and the list below is open. On the Items page the bar's title links here; the disclosure there still opens the list in place. Filtering by chip behaves identically on both.
2. Now: the state chart and cycle time under the bar; finished states folded per the page's one finished parameter.
3. In the model: a table of counted in (stock, which states), moved by (flow, which events), taken by (block: at, to, where, pool now and at most, attempts, TTL, taken and waiting now), goals (each with its word through goalWord), feedback loops (R/B and name); every name links to the diagram with that part selected or to the goal's evidence; links 'its states as a process map' (view=process&kinds=K, filed Q57's content) and 'draw what it touches' (kind=K) when that gap has landed.
4. Definition, a closed details: events -> states, fields shown, how each folds, relations both ways, joins, the lease rule.
5. Items: the list section, filter and pager built by the Items-list gaps, reused, not redesigned. Graph and Timeline stay views of the list.
Every link to a kind (item page header, Items bar titles, process map, stock panels' 'Show them on the Items page' when it names a whole kind) points to the kind's page.
Definition of done:
1. On the roadmap demo /items/ticket has h1 'ticket', its description, 'finishes', and an 'In the model' table naming todo, in-progress, in-review, developer, reviewer, nothing-ready-waits and its loops, each a link whose href starts with /diagram or opens evidence.
2. /items?kind=ticket ends at /items/ticket; the item page's kind link and the Items page's bar title go there.
3. The bar on /items/ticket and the ticket bar on /items have the same markup apart from the heading level and the open state (a test compares them); a chip click filters the list in place on both (window.__same survives) and lands in the address.
4. A kind nothing counts says so in section 3 and still shows its definition and items; built-in kinds render.
5. At 390 px every section stacks with no horizontal scroll.
6. SPEC §5a describes the kind's page; existing Items tests pass or are updated with the reason.
Files: ergostat/web/static/kinds.js, pages.js, main.js or util.js (route), ergostat/web/server.py (route), style.css, docs/SPEC.md, tests/test_items_page.py.
Acceptance tests: test_a_kinds_page_shows_its_definition_and_model_place, test_the_kind_bar_is_one_component, test_a_kinds_state_link_filters_without_reload, test_an_uncounted_kind_says_so, the redirect test. Each fails on main.
Budget: 300 net lines; if over, split definition and model place from the list wiring.

Milestone: kind-and-item-pages. Owner items: 15 (also 11). From the owner's list and the design review of 2026-11-22.


## Added 2026-11-22 (the owner)

The List, Graph and Timeline views live on this page only, for this one kind; `/items` no longer has them. This page loads only this kind's data. Its charts use the same right-side legend and state-group toggle as the overview (`items-one-section-per-kind-closed`). Opening a kind must not load any other kind's items.

## Where it stopped

Round 1, 2026-11-23. Built on `main` at 58471daf (the base; nothing newer to merge here).

**Built.** `/items/K`, the Items page with that one kind chosen (`pageItems(main, q, only)`); `/items?kind=K` ends
there through `replaceRoute` with its other params kept (util.js `route`); `"/items/"` in split.js's `OTHER_PAGES`.
The server already serves the address (`UI_PAGES`), so server.py is unchanged. `static/kinds.js` holds `kindBar`
(one bar on both pages, keyed by the kind's name, handlers passed in through opts), `kindModel` (In the model, from
`/api/kinds/K`) and `kindDefinition` (a closed `details`). On the Items page each kind's card is `kindBar` plus its
chart, and the bar's disclosure hides or shows that kind's list in place. The links to a whole kind go to its page:
the item page's Kind, the relations and timeline links, the process map's kind names, and `itemsHref` when the set
is exactly `{kind}`. SPEC §5a has *The kind's page*. The kind's page asks for `items`, `items-flow` and `items-graph`
of K alone and no remote's items. The `items` answer still carries every kind's counts (counts only, no items).

**Tests.** New in tests/test_items_page.py: test_a_kinds_page_shows_its_definition_and_model_place,
test_a_kind_chosen_ends_at_its_page_and_its_links_go_there (the redirect test), test_the_kind_bar_is_one_component,
test_a_kinds_state_link_filters_without_reload (both pages), test_a_kinds_page_stacks_at_phone_width,
test_an_uncounted_kind_says_so. Each was seen to fail with the code it guards broken (the bar's markup differing by
level, the redirect off, the chip navigating instead of filtering, the uncounted note removed, a 600 px-wide
definition). They were not run on `main`. There `/items/ticket` draws the plain Items page, with no `.kind-page` and
no `.kind-bar`, so each waits on a selector that never appears. Updated, with the reason in each: test_a_chosen_kinds_folded_system_is_shown (the
kind's page has no system headings), the model-changes test's address assertion and the snapshot test's chip selector
(test_items_page.py), and the old-address test in test_diagram_rendering.py (a kind chosen ends at its page).

**Defaults taken (the most reversible), and what waits on other gaps.**
- `items-one-section-per-kind-closed`, named in `depends-on`, is not on `main`. So the owner's addendum is only
  partly done: `/items` still has List, Graph and Timeline, and each kind's list there is still open by default.
  The overview's right-side legend, its state-group toggle and "the page's one finished parameter" (section 2's
  folding) do not exist yet, so the kind's page draws the chart as `/items` does today. Removing the views from
  `/items` belongs with that gap's overview change: about fifteen Graph and Timeline tests open `/items?view=…`
  across kinds, and the milestone frames need two kinds at once.
- On `/items` a chip click keeps today's address, `/items?kind=K&state=S`, filtered in place. A reload of it ends on the kind's page.
- `goalWord` does not exist on `main`. A goal's word is `statusEl(status)`, the word the Loops page uses.
- A goal links to `/diagram?around=loop/NAME` (its control loop, the panel's "Draw this loop alone"). A block links
  to `view=blocks&around=block/NAME`. A feedback loop has no address of its own, so it links to the Dynamics
  diagram drawn around its first part on the kind's footprint.
- 'draw what it touches' (`kind=K` on the diagram) is not linked: diagram-draws-what-an-item-or-kind-touches has not
  landed (diagram.js reads no `kind`).

**Not run here.** The unit suite and the four browser files as a whole (the factory runs them). Of tests/test_items_page.py as a whole
(58 tests): 57 passed. test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart failed, alone too. It
waits for the header's project switcher to list a second project (`/api/projects`, util.js `refreshProjects`), and
this branch does not touch that path. It could not be run on `main` here: a worktree of `main` and a checkout of main's
static files were both refused in this session. So it is reported as unrelated, unconfirmed on `main`.

**The build step (after round 1).** `[suites] build` failed with rc 5. It ran only the branch's two browser files, and
without Playwright both skipped, so pytest collected no test. The kind page's server address (`/items/<kind>`, served as
the page by `is_page_path`) is now in tests/test_graph_cli_web.py's page-address test. That is a unit test, so the build
step runs it and it passes. No code changed.

Round 2, 2026-11-23. Main (7a905955) merged in. The conflicts were resolved by keeping main's code and putting the
branch's work on top of it.

**Each finding of the review, and what changed.**
- *Built beside main's kinds.js, redirect and pageItems.* There is now one kinds.js: main's `pageKinds` overview plus
  the branch's `kindBar`, `kindModel` and `kindDefinition`, loaded once in index.html. There is one redirect, main's
  (`/items?kind=K` to `/items/K`, util.js `route`), and one `pageItems(main, q, only = false)` signature, main's. The
  kind comes from `q.get("kind")`, which the route sets. split.js keeps main's `/dashboard` and adds `/items/`, which
  main lacked. Without it, `/items/K` counts as a diagram address in the split view.
- *Done item 3's tests compare against a bar main's /items no longer draws.* Bare `/items` is main's overview of
  cards, and a card's name links to `/items/K`. The test of the redirect and the links now clicks that card's name.
  The Items page still draws `kindBar` in every kind's list (`/items?view=list`, a search). So
  test_the_kind_bar_is_one_component compares the ticket bar there with the one on `/items/ticket`, and the chip test's
  Items case runs there. A chip click there now writes `/items/ticket?state=review` (main's `go`), so a reload ends on
  the kind's page. These old tests were checked against main's `/items`: test_a_chosen_kinds_folded_system_is_shown
  passes, the model-changes test takes main's assertion, and the snapshot chip test passes.
- *Owner addendum.* `/items` no longer has Graph or Timeline. The view switch is drawn only on a kind's page, and
  `view=graph|timeline` is read only there. An old `/items?view=graph` draws every kind's list and asks for no graph
  (test_items_has_no_graph_or_timeline). The kind's page draws its chart as the overview does. By default it shows the
  state groups, from `/api/kinds/K`'s new `group` and `groups` (`items_overview.state_groups`, the overview's own
  rule). The legend sits at the chart's right. The overview's one switch, *State groups* or *Every state*, is kept as
  `?states=all` (test_a_kinds_chart_is_the_overviews). Ten Graph and Timeline tests that opened `/items?view=…` now
  open `/items/ticket?view=…`. The ticket graph still draws the items the tickets' relations reach (epics), so their
  assertions hold. Two were changed, each with its reason in the test: the snapshot test now checks the epic and
  ticket pages, and the Timeline's segment count is now "more than one a row". test_the_page_view_and_controls_are_named
  no longer expects a pressed List on `/items?view=list`. scripts/demo_check.py opens the Graph and the Timeline on the
  first kind's page.
- *goalWord.* A goal's word in In the model is `statusEl(goalWord(g))`. `/api/kinds/K` now carries each goal's
  `word` (tests/test_footprint.py), and the goalrow grep test passes.
- *An error shown as "no such kind" (lesson-3).* `apiText` now attaches the response status to its error. A 404 says
  "The model declares no such kind." Any other failure says "Could not read the kind from the model: …", in both In
  the model and the Definition (test_a_kind_unread_is_said_as_an_error_not_as_the_model, for 404 and 500).

**Defaults taken.** Main keeps every kind's list on `/items` (`?view=list`, and the overview's search lands there),
so the List itself stays there. Only its view switch is gone. Removing the cross-kind list would undo
items-one-section-per-kind-closed's own design, and the overview's search would have nowhere to land. Clicking a
state group on the kind's chart switches it to every state, because the list cannot filter by group. The snapshot
still holds the per-system graph answers that no page asks for now. "The page's one finished parameter" (section 2's
folding) still does not exist, and the grouped chart's *done* band is the folding there is.

**Tests run.** ruff is clean. Unit tests: tests/test_footprint.py (9) and tests/test_graph_cli_web.py (47) passed.
tests/test_items_page.py as a whole: 66 passed and 3 failed. The fix for the third then passed on its own:
test_the_timeline_draws_what_happened_and_what_is_projected expected more than 20 segments, and the tickets alone
draw 20. The other two are not this branch's:
- test_actions_say_per_class_asked_approved_denied_and_whether_held opens bare `/items` and waits for
  `.action-classes`. On main, bare `/items` is `pageKinds` (main's util.js:609), which draws no lists, and this branch
  changes neither that route nor that test. So it fails on main too, read from the code (not run on main here).
- test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart is the project-switcher failure reported in
  round 1. This branch does not touch that path.
tests/test_diagram_rendering.py as a whole was started under the watchdog and stopped at its 40-minute background
limit before it reported, so the file as a whole was not run here. Three of its tests did pass: the old-address and
new-tab test (whose merge conflict was resolved to main's side), the loading-heading test (both Items cases) and the
split test (split.js's `OTHER_PAGES`).
The three new tests were each seen to fail with the code they guard broken: the view switch drawn on `/items`, the
grouped chart turned off, and every unread answer called "no such kind". The 404 case rightly passed under the last.

Round 3, 2026-11-23. Main (f086f76e) merged in. That merge brought in items-pages-through-a-kind, which pages a
kind's list on the server, and it conflicted in docs/SPEC.md and static/pages.js.

**How the conflicts were resolved.** Main's paging is kept whole: `page=`, `sort=` and `size=` named by kind,
`go(load)`, the search's match count (`found`), and the pager above and below the table. Main dropped the
"N older items not loaded" note and the "All N" link, and the merge drops them from the branch's code too. The
branch's code is kept on top: `one`, `shut`, `unpick`, the kind's page's own layout (bar and model first, then the
list under the filters), `?states=all`, `kindHref` in the address, no remote items asked on a kind's page, and the
cycle chart only on `/items`. In SPEC §5a, main's paragraph is now titled *A kind's page's list*, so it no longer
clashes with the branch's *The kind's page*. The branch's views paragraph replaces main's older one, which still said
`/items` has Graph and Timeline.

**Tests run after the merge.** ruff is clean. Unit tests: tests/test_item_search.py (11), tests/test_graph_cli_web.py
and tests/test_footprint.py (56) passed. tests/test_items_page.py under the watchdog with Playwright: 70 passed and
2 failed. The two failures are the same two round 2 reported as not this branch's:
test_actions_say_per_class_asked_approved_denied_and_whether_held (bare `/items` is main's overview) and
test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart (the project switcher). Neither was run on main
here. Not run: tests/test_diagram_rendering.py and the other browser files. `node --check` on pages.js was refused, but
the page tests load it.

Round 4, 2026-11-23. Main (28ad5c4a) merged in. It conflicted in static/pages.js, where main's finished-items work
(`itemsFinished`, `hiddenStates`, *Show finished*, the at-once `Loading…` and each kind's finished note) met the branch's
`one`, `shut`, `lbox` and the kind's page layout. Both sides are kept. *Show finished* and `Loading…` sit in the
kind's page's filters too.

**The review's finding (the only one).** On the kind's page, folding the bar's disclosure rendered "Nothing matches."
under the Items heading of a kind that has items (lesson-3). The same happened on `/items?view=list` when a search's
matching kinds were all folded. The disclosure is kept: test_the_kind_bar_is_one_component holds that the two bars
have the same markup apart from level and open state, and the disclosure is part of that markup. Instead, `tables` now
marks a kind whose rows its own disclosure hides (`hid`), and `none` is not drawn when one is hidden. A folded list
is folded, not a miss. On the kind's page a folded Graph or Timeline goes through the same path. New test:
test_a_folded_kinds_list_is_not_said_empty (on `/items/ticket` and `/items/ticket?state=review`). It clicks the
disclosure, waits past a poll, asserts no "Nothing matches", and opens the list again. It failed (2 of 2) with the
`!hid` guard removed and passes with it.

**Found by the merge's tests.** main's test_a_state_click_answers_at_once_and_asks_once opens `/items?kind=gap`,
which now ends on the kind's page. Two changes were needed:
- **A bug fixed.** `go` hid the rows outside the chosen state in `box`, but the kind's page's list is in `lbox`, so a
  click there did not filter at once. It now uses `lbox`, which is `box` on `/items`.
- **A test updated, with its reason in the test.** It clicked `.kind-flow a.stbox`, and the kind's page's chart draws
  state groups by default. It now clicks the same states' chips in the kind's bar (`.kind-bar a.stbox`).

**Tests run.** ruff is clean. tests/test_items_page.py as a whole, under the watchdog with Playwright: 78 passed and
1 failed. The failure is test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart, which waits for a
second project in the header's `#project` switcher. It is the same failure reported in rounds 1 to 3, on a path this
branch does not touch. test_actions_say_per_class_asked_approved_denied_and_whether_held, reported as failing in rounds
2 and 3, passes now. Not run: tests/test_diagram_rendering.py, the other browser files and the unit suite (the factory runs
them). Commands refused in this session: a `python3 -` heredoc edit, a pytest run with output redirected to a file
under /tmp, a run piped to `grep`, and `ps -A … | grep -cE …` to look for other suites.

Round 5, 2026-11-23. Built on a1198300 (main 8a27f9e3 already merged in; `main` has nothing newer here).

**The queue's findings.**
- *tests/test_items_overview.py::test_the_overviews_script_asks_one_answer_and_draws_no_rows* (main's test). It reads
  kinds.js as the overview's script and holds that it draws no table. The branch's *In the model* table
  (`kindModel`) was in kinds.js, so the assertion `not table(` failed. The test is kept as it is. `kindModel`,
  `kindDefinition` and their helpers (`partHref`, `listOf`, `termOf`, `kindUnread`, `groupedFlow`) moved unchanged
  into a new static/kindpage.js, loaded right after kinds.js in index.html. kinds.js keeps `kindHref`, the one
  `kindBar` and main's overview. This is the most reversible option: no code changed, only where it lives. Net
  lines are about the same (a header comment more). The test now passes.
- *tests/test_compute_output.py::test_ended_after_last_out*. The branch changes nothing under ergostat/compute, nor
  that test (`git diff --stat main` lists only web, docs, scripts/demo_check.py and tests). It passed here when run
  alone. Reported as unrelated (lesson-13) and left alone. It may depend on the machine's load or its pipe buffers.

**Tests run.** ruff is clean. tests/test_items_overview.py, test_ended_after_last_out and tests/test_legend_memory.py
(which globs every static script): 9 passed. tests/test_items_page.py as a whole, under the watchdog with Playwright:
78 passed and 1 failed. Run alone, test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart also fails.
It is the project-switcher failure reported in rounds 1 to 4, and the count matches round 4. The failing test's name
in the whole-file run was not read, because piping that run to `grep` was refused. Not run: the unit suite,
tests/test_diagram_rendering.py and the other browser files.

Round 6, 2026-11-23. Main (ee43cf60) merged in (5304e2f4). It conflicted in docs/SPEC.md, in *The Items page's
views*. Main had added the case of items with no relations, and the order of systems in the Graph and the Timeline on
`/items`. The branch keeps those views only on a kind's page (the owner's addendum), so the resolution keeps the
branch's paragraph. Main's no-relations sentence is kept, said of a kind. The systems' order is dropped, because a
kind's page draws one kind and no system groups.

**What the merge's tests found, and what changed.**
- *Main's two new tests* (test_the_timeline_draws_each_items_states_without_relations_and_the_graph_says_there_is_none,
  test_the_timeline_of_tickets_with_relations_comes_before_ergostats_own_upkeep) opened `/items?view=timeline|graph`,
  which this branch no longer draws. They now open `/items/ticket?view=…`, with the reason written in each. Their
  row, state and label assertions are kept. Each "view above the system's charts" assertion is now "drawn in the
  kind's Items section". The systems' order is now "no `ergostat.message` row drawn" (the page loads only its kind).
  The rows' top bound is now 1600 px, because the bar, Now and In the model come first. The second test keeps its name
  for the queue's tracking, though its systems' order no longer applies.
- *Main's rule held on the kind's page.* On a kind's page, the Graph of a kind with no relations drew its cards
  silently, because `want` is always that kind. relPart now says main's "These items do not wait on one another, so
  there is no dependency graph." there (pages.js, 2 lines). With that line turned off, the desk test failed
  (timeout). test_a_snapshot_lets_a_kind_and_its_state_be_chosen expected the `note` kind's Graph to draw cards. It
  now expects the note there, and checks that the `note` items are drawn from the snapshot in the Timeline. The
  reason is in the test.
- *A race made wider by the kind's page* (lesson-10). test_a_kinds_search_reaches_every_item_and_its_sort_is_the_whole_sets
  failed in 2 of 3 runs. It read the old rows under the new "1 match, 1 finished". The count was written when the
  answer came, and the rows only after the later awaits (the graph and the kind's model). Now the count is written
  right after the rows it counts are patched. It then passed 2 of 2 runs.

**Tests run.** ruff is clean. Unit: tests/test_items_overview.py, tests/test_graph_cli_web.py and
tests/test_legend_memory.py, 62 passed. tests/test_items_page.py as a whole, under the watchdog with Playwright: 80
passed and 1 failed. The failure is test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart, the project
switcher (`#project`), reported in rounds 1 to 5 on a path this branch does not touch. Not run: the unit suite,
tests/test_diagram_rendering.py and the other browser files. Commands refused in this session: a `python3 -` heredoc
edit of SPEC, a whole-file run piped to `grep`, and a `for` loop running the two tests three times.

Round 7, 2026-11-23. Main (b7302db6) merged in (1672c687). It conflicted in static/pages.js and
tests/test_items_page.py.

**How the conflicts were resolved.** Main had added milestone-progress-per-group: each kind's progress per group
(`gps`, `groupRows` from itemsets.js), drawn on the old per-kind card in pageItems. It had also added the 1440 px
table test. The branch's card is `kindBar` plus its chart. So main's group rows are now one helper, `gpOf(k)`, drawn
under that card on `/items` and under the chart in the kind's page's *Now* section. Main's
test_a_milestones_row_opens_exactly_its_gaps_in_the_list_graph_and_timeline needs the second one, because a row's
click lands on `/items/gap?where=…` and the test asserts `.gp-row.on` there. The branch's `foundSaid` (the count
written with its rows, round 6) is kept, and `flowsWere` takes main's `[flows, gps]`. Main's `pick` let the kind go
to `null`, and the branch's lets it go to `one`, so the branch's is kept: on a kind's page a second click clears only
the state. In the tests, both sides only added tests, and all of them are kept.

**Tests run.** ruff is clean. Unit: tests/test_items_overview.py, tests/test_legend_memory.py and
tests/test_graph_cli_web.py (62 passed), and tests/test_group_progress.py (9 passed). tests/test_items_page.py as a
whole, under the watchdog with Playwright: 83 passed and 1 failed. Main's new tests passed: the 25-milestone card,
the milestone row's gaps, and the 1440 px table, which now opens `/items?kind=ticket` and ends on the kind's page.
The failure is test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart. It times out at
test_items_page.py:2301, waiting for a second project in `#project`. That is the project-switcher failure reported in
rounds 1 to 6, on a path this branch does not touch. Not run: the unit suite, tests/test_diagram_rendering.py and the
other browser files. Commands refused in this session: a `python3 -` heredoc that resolved the conflicts (done with
the editor instead), and a background run with output redirected to a file under /tmp.

Round 8, 2026-11-23. Main (2f08c24e) merged in (a412b1d2). It conflicted in static/pages.js only. Main's
inbox-says-what-a-person-may-do had added the `mayDo` line to the Items page's `p.append`. That line is shown when the
kind is the gated actions. The branch had split that append into one layout for the kind's page and one for `/items`.
Both sides are kept: `mayDo` sits right after the filters in both layouts. So `/items?kind=ergostat.action` (which
ends on the kind's page) and `/items/ergostat.action` show it, and bare `/items` does not. Nothing else changed.

**Tests run.** ruff is clean. tests/test_diagram_rendering.py::test_the_requests_group_opens_by_saying_what_a_person_may_do
(main's test, which opens both addresses): 2 passed. tests/test_items_page.py as a whole, under the watchdog with
Playwright: 84 passed and 1 failed. Run alone, test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart
also fails (a timeout). That is the project-switcher failure reported in rounds 1 to 7, on a path this branch does
not touch, and the count matches. Not run: the unit suite, tests/test_diagram_rendering.py as a whole and the other
browser files. Commands refused in this session: a single-test run without the watchdog piped to `grep` (to name the
failing line), and a `cat >> … <<'EOF'` heredoc append to this file (done with the editor instead).

## Where it stopped

Parked by the factory (merge-queue, 2026-11-23 12:03).

Failed its gates 8 times (the kill rule); the last, in the merge queue: conflicts with main: docs/SPEC.md ergostat/web/static/pages.js ergostat/web/static/split.js tests/test_graph_cli_web.py tests/test_items_page.py

Continued as gap/the-kind-page-continued, round 1, 2026-11-24. Main (59600738) merged in (ee5c0897).

**How the conflicts were resolved.**
- split.js: main's `/goals` and the branch's `/items/` both kept in `OTHER_PAGES`.
- tests/test_graph_cli_web.py: main's `/goals` and the branch's two kind-page addresses both kept.
- docs/SPEC.md §5a: the branch's *The kind's page* and main's *Where it went* and *Drawn alone* are separate
  paragraphs, so all three are kept, in that order.
- pages.js: main replaced the *Show finished* checkbox with the one *Finished items* choice (`finSeg`, `fin()`,
  `finChosen`) and dropped Frontier and Collapse done. Main's code is kept, and the branch's `one` and `shut` sit on
  it. The view switch is still drawn only on a kind's page (`if (one)`), now without main's removed `check` helper.
  Main had added a *process map* link (`a.pm-link`) to each kind's card. The branch's card (`kindBar` plus its chart)
  gets the same link (`pmOf`), next to the bar, not inside it, so the two bars still have the same markup. Main's
  item page now draws `...went` (its path) where the branch had `track`. Main's is kept, with the branch's
  `kindHref` for the timeline link.
- tests/test_items_page.py: main's finished-choice tests (`fin_pressed`, `fin_choose`, the renamed
  test_the_graph_draws_the_unfinished_with_the_finished_collapsed, the timeline's three finished cases, the
  milestone frames' `finished`) are kept. They now open `/items/ticket?view=…` because the views are a kind's page's,
  with the reason in each. The same applies to two of main's new tests that opened `/items?view=graph|timeline`
  (test_rg_model_draws_each_finished_choice_on_a_chain, test_an_old_graph_address_opens_with_shown_and_the_choice_survives_a_view_switch).
  The named-controls test takes main's `/goals` and keeps the branch's "no view switch on `/items?view=list`".

**Added (the definition's section 3).** main now has diagram-draws-what-an-item-or-kind-touches, so *In the model*
links "draw what it touches" (`/diagram?view=dynamics&kind=K`). The link is drawn only when something counts or
takes the kind, because otherwise the diagram would only say it is not counted. SPEC §5a says so. Tested in
test_a_kinds_page_shows_its_definition_and_model_place (the href) and test_an_uncounted_kind_says_so (no link).
That is 3 lines of code. Net lines outside tests, docs and dev: 181 (232 added, 51 removed against main).

**Tests run.** ruff is clean. Unit: tests/test_graph_cli_web.py (57), tests/test_items_overview.py,
tests/test_legend_memory.py and tests/test_footprint.py (18), and tests/test_group_progress.py and
tests/test_item_search.py (20), all passed. tests/test_diagram_rendering.py::test_items_links_each_kind_to_its_process_map_whose_states_say_how_many_are_there_now
(main's `pm-link` test) passed. tests/test_items_page.py as a whole, under the watchdog with Playwright, was run
three times: 96, 96 and 97 passed of 100. Failures:
- test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart failed 3 of 3. It is the project-switcher
  timeout (`#project`) reported in every round since round 1, on a path this branch does not touch.
- test_every_surface_prints_the_servers_one_count_of_goals_off failed 3 of 3, and it fails on main. Main's test
  asserts the Goals page's heading reads `Loops · goals off …`, but main's own `pageLoops` now titles it `Goals`
  (`page(main, "Goals")`). This branch changes neither. Unrelated (lesson-13), left alone.
- test_a_lease_taken_or_ended_comes_and_goes_in_the_valves_panel failed 3 of 3 in the whole file and passed alone.
  The cause is order: test_cost_is_stated_or_says_why_it_is_none_with_the_windows_total_and_on_an_item (line 471)
  records leases on `hypothesis/4` with fences 1 and 2. The lease test then writes a `lease.taken` for
  `hypothesis/4` with fence 1, which the fold does not take, so the item never appears. The two run together
  reproduce it (1 failed, 1 passed). Both tests are main's, in main's order, and the branch touches neither, so this
  fails on main too. Unrelated (lesson-13), left alone.
- test_the_graph_and_the_timeline_left_open_change_nothing[graph] failed in 2 of the 3 whole-file runs (3 mutations:
  a SPAN's `title`, a SPAN's and a BUTTON's children). It passed alone, after a 240 s wait, after the old-address
  test, and after the two Timeline tests before it (5 runs). The mutated nodes match the graph legend's estimate
  span and status keys, which come from the `items-graph` answer. Main's version of the test drew the same tickets'
  answer on `/items?view=graph`. Its cause was not found here, so this is a flake not explained (lesson-10). It is
  not shown to be unrelated.
Not run: the unit suite, tests/test_diagram_rendering.py as a whole and the other browser files. Commands refused
in this session: `git grep -n -A3 "def test_the_graph_and_the_timeline_left_open_change_nothing" main -- tests/test_items_page.py`.

Continued, round 2, 2026-11-24. Main (b9341591) merged in (2f90069f). It conflicted in static/pages.js only. Main's
ui-a-filter-that-matches-nothing-says-so-with-a-way had added the search's count beside the box (`hitsSaid`) and
renamed `hits` to `total`. Both sides are kept: `hitsSaid` sits in the filters of both layouts, and the branch's
`foundSaid` (the count written with its rows, round 6) is computed from main's `total`.

**The review's finding (the only one): the left-open graph test's flake, found and fixed.**
- *The cause, reproduced.* `relations_api` keeps the `items-graph` answer for `KEPT` = 300 s while the record is
  quiet, and its `now` and `since` are those of the moment it was built. When it is built again, `now` moves on by up
  to 300 s in one step. The legend's levelled finish (`now` plus the chain of unstarted work) moves, so the
  `rg-key rg-eta` span's title changes. Finished items whose last move has left the 3600 s window drop out (the
  roadmap's are seeded 47 to 22 minutes back), so the "finished not drawn" span and the status keys change. The
  estimates (`eta_api`, `KEPT` = 120 s) are worked out again the same way. The page is right to draw these: each is a
  new answer. The test failed when its watch straddled a rebuild, which depends on where in the file it falls. The
  repro opened the page, then slept until 1.5 s before the cached answer's `now` + 300 and watched. It failed with
  4 mutations, the first the `rg-key rg-eta` span's `title`. Timed instead to a ticket leaving the window, the same
  test passed, because the 300 s cache hides the exit until the rebuild.
- *A second cause, found by the same repro once the first was fixed.* The test watched `document.body`, so it also
  saw the header's held-up line (`#heldup`, util.js). Its title, "… 7 items wait on it …, 4h40m of waiting in all",
  counts up with the clock. That line is on every page, main's `/items?view=graph` included.
- *The fix (tests only).* `between_rebuilds(url, kind, span)` asks `items-graph` until neither answer will be made
  again by age within `span` s (from the answer's own `now` and `eta.at`, against the two modules' `KEPT`), waiting
  past a rebuild when one is due. The test calls it before opening the page, with 25 s. The page's load and watch take
  about 17 s, so the watch ends before the next rebuild and before the kind's chart asks for its flow again (every
  30 s). OBSERVE now watches `#main`, the page, not the header. It assumes that nothing writes the roadmap's record
  during the test, which holds: no test in the file writes to it after seeding.
- *Shown.* The same repro, timed to 10 s before a rebuild, with the fix: passed. tests/test_items_page.py as a whole,
  under the watchdog with Playwright, twice after the fix: 100 passed and 3 failed each time. The graph test passed in
  both, and also in one whole-file run before the fix (99 passed, 4 failed). The `rg-eta` span that failed the repro
  is inside `#main`, so the narrower watch still catches a change in the legend.

**Found by the merge's tests.** Main's test_a_search_on_a_kinds_own_page_keeps_its_one_count_and_its_section opens
`/items/ticket` and reads `.sys-head`, the system headings that main's kind page drew. The branch's kind page has
none (the-kind-page: the bar is its h1, then its sections). It failed in the whole-file run before this change. Its
assertions are kept, on the kind page's headings: no heading says a page's "match" count (the bar's title and the
sections' h2s), the count beside the box is one, and a miss keeps the one `.kind-items` section. The reason is in
the test. It passed after the change.

**Failures that are not this branch's** (each failed in all three whole-file runs, and each was reported in the round
before): test_a_lease_taken_or_ended_comes_and_goes_in_the_valves_panel (the order of two of main's tests on
`hypothesis/4`), test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart (the project switcher), and
test_every_surface_prints_the_servers_one_count_of_goals_off (main's test expects `Loops ·`, main's page says
`Goals ·`).

**Tests run.** ruff is clean. The runs above. Not run: the unit suite, tests/test_diagram_rendering.py and the other
browser files. One background run (the repro timed to the ticket's exit, superseded) was still sleeping in a test
when the next single-test run started, so two browser runs overlapped for about five minutes. Commands refused in
this session: `uv run python -c "import time; time.sleep(540)"` and `ps -A -o pid=,ppid=,command=` (to find that
background run and stop it).
