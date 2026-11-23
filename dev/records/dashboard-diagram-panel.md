# dashboard-diagram-panel: A diagram in a Dashboard panel: a Diagram or Items Graph address drawn read-only

depends-on: [dashboard-page-v1]

Problem: the owner wants a nodes-and-edges diagram on the dashboard. The model diagram runs on page-global state S with an ELK layout and is embedded today only as a whole page in an iframe with ?pane=1 (ergostat/web/static/split.js:1-40); layout is slow on large models (owner item 10), so a dashboard poll must never re-lay it.
Change: a diagram panel takes a Diagram address (view dynamics, blocks or process; system; opened; selection; item= or kind= when available) or an Items Graph address (kinds or system). The Items Graph draws through relGraph directly. The model diagram is drawn read-only and fitted, by the embedding the proposal chose: the existing ?pane=1 frame with toolbar and side panel hidden, or an embeddable entry point in diagram.js with its own state object if the proposal's cost check allows. Values update in place through graph_poll; no re-layout while the structure signature is unchanged (the layout cache of diagram-routes-fast-then-refined is used when present). At most one model-diagram panel is live per dashboard (others draw on click), nothing loads until the panel is on screen, and clicking opens the full page at that address. Text is never drawn under 11 px: when the drawing will not fit, the panel shows the closed boxes and says 'open on the Diagram'.
Definition of done:
1. On :8796 a panel for view=dynamics&system=product draws within 3 s, and on the next poll redraws values without calling layout (asserted by a counter).
2. On :8797 a whole-model panel shows the folded boxes, not unreadable text.
3. The click opens the same address.
4. No console errors on any demo; no elk request before the panel is on screen.
Files: ergostat/web/static/panels.js, dashboard.js, diagram.js or split.js (the embedding), ergostat/web/graph_poll.py if needed, tests/test_dashboard_page.py.
Acceptance tests: the browser checks for 1-4.
Budget: 220 net lines.

Milestone: dashboard. Owner items: 18 (a nodes-and-edges diagram), 10. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Round 1, built. The panel, the embedding and six acceptance tests are in. What follows says what each done item is
checked against, and where the claim is narrower than the item's words.

What was built (about 140 net lines of code, inside the 220 budget):
- A draft panel `{form: "diagram", display: {address}}` (panels.js: `diagramPanel`, `diagramAddress`; dashboard.js
  draws it in place of a chart, 10 rows by default, with no Edit tool since the panel editor has no form for an address).
  A Diagram address keeps view, system, open, select, item, kind and window; an Items Graph address is `/items?kinds=`
  or `kind=` or `system=`, or `/items/KIND`. Anything else says it is neither, and asks nothing.
- The embedding: the existing frame, `?pane=embed` (split.js: `EMBED`), with the toolbar, zoom, side panel, legend,
  split grips and open-level note hidden and the canvas taking no pointer. Chosen as the more reversible of the two the
  definition allows: no second state object in diagram.js. The frame does not poll on its own: the dashboard's poll
  sends it a message and it asks `/api/graph` with the structure it holds (graph_poll), so an unchanged structure gets
  the values alone and `sig()` keeps the layout. graph_poll.py needed no change.
- Fitting (diagram.js: `embedFit`): the drawing is shown at its own size or larger (zoom ≥ 1, so the 11 px text is
  never drawn smaller). Too large, the frame reloads once with `open=-` (every system closed); still too large, it is
  shown from its top-left corner. In both cases the panel's note says "... open on the Diagram". The Process view has no
  systems to close, so it is only shown from its corner, with the note.
- One model diagram live: one IntersectionObserver for every diagram panel. The first panel in reading order to come
  on screen loads its frame; another one shows "Draw this diagram here", and clicking that moves the frame to it.
  Nothing (frame, `/api/graph`, `/api/items-graph`) is asked before the panel is on screen.
- The Items Graph is drawn by `relGraph` from `/api/items-graph`, asked again on the dashboard's poll. It is drawn
  again only when the answer changed (the way the Items page keeps it). Too large for zoom 1, it is shown at zoom 1
  from its corner with "open on the Items page".
- A click on the panel goes to the address through the page's own link handling. In edit mode the click does nothing.

How each done item is checked (tests/test_dashboard_page.py):
1. `test_a_diagram_panel_draws_in_3s_and_a_poll_brings_its_values_without_a_layout`: drawn under 3 s from page
   open, then `dashRefresh()`. The frame's `S.layouts` (the counter diagram.js already keeps) is unchanged, and
   the answer was values only (`S.embedSame`). Marked serial (a wall-clock bound).
2. `test_a_whole_model_panel_shows_its_systems_closed_and_no_text_under_11px`: `open=-`, at least two system
   boxes, every drawn text's font size × zoom ≥ 11, and the note.
3. `test_a_click_on_a_diagram_panel_opens_its_address`: the top page goes to /diagram with view=dynamics and
   system=product and no pane mark, toolbar shown. The Items Graph test checks its click as well.
4. Every acceptance test asserts no page error and no console error in the page or its frame.
   `test_nothing_loads_until_on_screen_and_one_model_diagram_is_live` checks that before scrolling there is no
   frame, no `/api/graph` request and no extra elk.bundled.js request. `test_a_diagram_panel_says_no_error_on_other_demos`
   covers five more examples.
   `test_an_items_graph_panel_is_drawn_by_relgraph_when_on_screen` covers the Items Graph.

Narrower than the words, said plainly:
- :8796 and :8797 are the owner's live servers, which this container cannot reach. The tests serve their examples
  instead: software-factory (:8796) and big (:8797), as earlier records read them. The 3 s is measured against that
  local copy.
- "No elk request before the panel is on screen": index.html loads elk.bundled.js on every page, the Dashboard
  included (that is not this gap's). The check is that nothing more is asked (no frame, which would run ELK, and
  no `/api/graph`) until the panel is on screen.
- "No console errors on any demo": checked on seven examples (software-factory, big, the-job, ops, autoscaler,
  first-loop, todo-list), not on every folder in ~/ergostat-demos.
- The layout cache of diagram-routes-fast-then-refined is not on main. The frame is diagram.js itself, so it will use
  that cache when it lands, but that is not tested here.
- The values come on the dashboard's poll, so with the dashboard's Refresh at Off the diagram's values stay as first drawn.
- A diagram panel is added through the draft (a link, or localStorage). The panel editor offers no diagram form,
  because panel-editor.js is not in the Files list.

Lesson 9, each new test seen to fail: forcing a re-layout on each poll fails item 1 (layouts 2 ≠ 1). Fitting with no
11 px floor and no folding fails item 2 at `open`. Keeping the folding but dropping the floor fails it at 8.2 px.
Loading the frame whatever is on screen fails the lazy-loading test and the Items Graph test. A link to bare /diagram
fails item 3. Making every model panel live fails the one-live test.
Lesson 10: the one-live test failed 2 of 4 whole-file runs at first. The cause was in ergostat, not the test: each
panel had its own observer, so when two panels came on screen in the same frame either could become the live one. One
shared observer, taking panels in document order, fixed it, and the next three whole-file runs passed.

The Items Graph in a panel: relGraph sizes its stage for the Items page (an inline height) and has Fit, + and −
buttons. In the panel the height is cleared, the drawing is fitted again (Fit, called without letting the click bubble
to the panel's link), the buttons are hidden and the drawing takes no pointer, so a click opens the address and never
an item.

Runs on the last commit:
- tests/test_dashboard_page.py whole: 46 passed (all 41 that were there before, and the new ones). Ruff clean.
  tests/test_style_tokens.py: 15 passed. That run caught an `!important`, which is now gone.
- Against the house rule, I started two of the four browser files myself: tests/test_page_polling.py passed (rc 0).
  tests/test_diagram_rendering.py was stopped at the session's background time limit, at about a quarter of the
  way through, with failures among its first tests. It ended with no summary, so the failing tests are unnamed
  (`pytest --collect-only` was refused). It was not started again, since the rule is not to run it here.
  Outside the `?pane=embed` frame, diagram.js now differs only in setting two flags (`S.embedSame`,
  `S.embedFits`). `fit()` and `sideHidden()` change only when `EMBED` is true. So these failures are not expected to
  come from this branch, but that is a reading of the code, not something shown by a run. The merge queue's run of the
  four browser files is the real check.
- Not run: the unit suite, test_items_page.py, test_page_refresh.py, demo_check.

Round 2. The review's one finding, answered:
- `diagramAddress` (panels.js): an Items path that will not decode (`/items/%zz`, `/items/%E0%A4%A`) threw a URIError
  out of the Dashboard's drawing. The decode is now in a try that returns null, so that panel says "Not a Diagram or an
  Items Graph address", asks nothing, and the rest of the Dashboard is drawn. +2 net lines.
- New test `test_an_address_that_will_not_decode_stops_at_its_panel`: both addresses beside a line panel; each says it
  is neither, the line panel is there, no `/api/items-graph` is asked, no page or console error. Lesson 9: with the
  try removed it fails (the panels never appear, the Dashboard stops drawing).
- Runs: tests/test_dashboard_page.py whole, 48 passed. Ruff clean. main (59600738) was already merged in; no newer
  main in this clone. The four browser files, the unit suite and demo_check were not run here (the house rule); what
  round 1 said about test_diagram_rendering.py stands, unchanged.
