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
