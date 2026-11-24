# item-page-draws-its-path: The item page draws its path on the Dynamics and Blocks diagrams, on demand

depends-on: [diagram-draws-what-an-item-or-kind-touches]

Problem: the owner asks to see, on the item page itself, the subset of the Dynamics and Blocks diagrams an item leased to agents passed through. diagram-draws-what-an-item-or-kind-touches gives the subset on the Diagram page and links to it; the item page still shows no picture. diagram.js (pageDiagram and its drawers) runs on the page-global S, #detail and pins, so it cannot be mounted elsewhere as it is. Build this as docs/proposals/item-and-kind-footprint.md decided (inline on demand is the default; if the proposal chose links only, close this gap).
Change: under 'Where it went' a closed section 'Draw its path' with a Dynamics/Blocks switch. Opening it draws item=ID in a box about 420 px high, full width, fitted, with no toolbar, side panel, pins or address changes, by the embedding the proposal chose (the renderer mounted with {view, item, embedded: true} and its own state object, or the ?pane=1 frame). A click on a part goes to /diagram with that part selected. Nothing loads (no ELK, no libavoid) until the section opens; the item page's poll does not re-lay the diagram unless the path changed; closing and reopening leaks no listeners or timers (the page guard of diagram-lines-stay-attached).
Definition of done:
1. On the roadmap demo /item/ticket%2F<done ticket> opening 'Draw its path' shows an svg with the stocks todo and in-progress and the valve started; switching to Blocks shows the developer's block and its loop whole.
2. With the section closed no request for elk.bundled.js is made and the item page's load time is unchanged (measured before and after).
3. No console error; the Diagram page's render tests and page-polling tests pass.
Files: ergostat/web/static/diagram.js, dynamics.js, blocks.js, interact.js (state scoping), pages.js, style.css, tests/test_items_page.py.
Acceptance tests: the browser checks above. If mounting needs more than the budget because of global state, stop and file a proposal splitting the renderer's state first.
Budget: 180 net lines.

Milestone: kind-and-item-pages. Owner items: 20 (the subset of the diagrams, on the item page). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. 76 net lines outside tests and docs (118 added, 42 removed), within the 180.

**The embedding: the proposal's, not either of the two this definition names.** The definition says "by the
embedding the proposal chose" and names a per-mount renderer or the `?pane=1` frame; the proposal (§2, §6.4)
chose neither: it rejected both and chose `drawStatic`, the Guide's one-drawing-at-a-time renderer moved out of
guide.js. That is what is built: `drawStatic(svg, g, view, {aspect, toggle})` in diagram.js (the Guide now calls
it), which sets the renderers' S fields for one drawing, queued, and puts them back after (but `toggleSystem` while
a drawing's own toggle lives, the Guide's open/close), and sets nothing once its svg has left the page. No
state-scoping change in interact.js, dynamics.js or blocks.js was needed, so none was made. This is the more
reversible choice: nothing in the main diagram's code path changed but one line (ELK asked for early, below).

**ELK loaded on the first layout, app-wide (outside the Files list: util.js, index.html, server.py,
snapshot.py).** Done item 2 asks that no request for elk.bundled.js be made with the section closed, but on main
`<script src="/static/elk.bundled.js">` is in index.html, so every page, the item page included, fetched and ran
it at its start. The only call into it is `elk.layout(...)`, so `elk` is now a small object whose `layout` awaits
`elkReady()`: the page's own ELK when it has one (a snapshot's, a test page's), else the script loaded once, at
its version (the server's `ergostat-assets` meta tag now lists elk.bundled.js, as it lists libavoid's files). The
Diagram page calls `elkReady()` as it opens, so the fetch runs beside its first graph request. A snapshot inlines
ELK before util.js (with the data, as before). The reversal is one line in index.html put back.

**Measured (done item 2):** `test_the_item_page_loads_no_slower_without_elk_at_its_start` loads the item page
alternately as main serves it (ELK's script put back into the page by a route rewrite: the only boot difference)
and as this branch does, 5 cold loads each, navigation to the path's last step on the page. In this container:
main 148 ms median (122-239), this branch 102 ms (75-113). The test asserts no ELK request on this branch and a
median no slower than main's + 100 ms. "Unchanged" is therefore met as "not slower" (it is faster).

**Tests (tests/test_items_page.py):** `test_the_item_page_draws_its_path_on_demand` (done items 1 and 3's console
check; closed: no elk.bundled, libavoid or /api/graph request; open: every node of `/api/graph?view=V&item=ID`
drawn, todo, in-progress and started among them, 400-440 px high and the section's width, a viewBox, no toolbar,
aside or pins; a forced whole refresh lays nothing out again; Blocks: block.developer's shape and every node of
its goals drawn; three rounds of close, open, Dynamics, Blocks add no window or document listener and no
interval; a drag moves nothing and saves no pin; a click on the developer opens
`/diagram?view=blocks&item=ticket%2Fe1-design&select=block.developer` with it chosen) and
`test_the_item_page_loads_no_slower_without_elk_at_its_start`. Broken on purpose and seen to fail: the
same-path check removed (laid out again: 4 layouts for 2), the click guard moved off capture (no navigation), a
window listener added per drawing (listeners 40 then 42). Not seen to fail: the drag check with the pointerdown
guard removed still passes, because S is put back after drawing and the renderers' drag then finds no layout;
the guard stays as a second line (the Guide has the same one).

**Not covered:** a path that changes while the section is open (a re-layout then) has no browser test: making
one would add events to the roadmap fixture other tests count. Timers are checked as intervals only; drawStatic's
one 5 s wait for the lines is cleared when they come.

**Suites run here:** ruff clean; tests/test_graph_cli_web.py (59 passed: the page and snapshot tests);
tests/test_items_page.py whole: 88 passed, 4 failed. Of the 4, `test_a_lease_taken_or_ended_comes_and_goes_in_the_valves_panel`
and `test_the_graph_and_the_timeline_left_open_change_nothing` (both params) passed when run again alone;
`test_every_surface_prints_the_servers_one_count_of_goals_off` fails alone too, on the /loops page's heading
('Goals · …' where the test wants 'Loops · …'), code this branch does not touch: a failure of main, left alone.

tests/test_page_polling.py: 23 passed. tests/test_diagram_rendering.py: 322 passed, 32 failed. Done item 3 is
therefore not shown green here, and none of the 32 is this branch's, as far as could be checked without running
main (`git checkout main -- ergostat/web`, to run main's code in this tree, was refused):
- 22 are `test_sensors_are_blocks_with_what_they_read_and_no_part_has_a_tooltip[*]`: each finds the `<title>`
  "Drawn alike here with …" that dynamics.js:597 puts on a loop marker (main's, from dynamics-every-goal-drawn and
  dynamics-off-status-on-the-part, 2026-11-23; dynamics.js is not changed here).
- `test_every_view_draws_cleanly_and_in_time[autoscaler, the-job, ticket-factory]`: layout-rule ceilings
  (satellite-far, valve-orientation-mismatch) and one 240 s wait in autoscaler's control view.
- `test_blocks_crossings_hop_dots_…`: `get_by_role("button", name="fit")` now matches main's `model-fits` upkeep
  goal's blocks besides the Fit button. `test_the_dynamics_view_speaks_system_dynamics_…`: the panel says "goal".
  `test_an_equation_its_numbers_…`: the Model page's text. `test_a_suggestion_appears_when_it_has_a_verdict`.
- `test_an_open_system_dragged_by_its_outline_takes_its_parts_and_stays`,
  `test_the_exported_png_shows_every_loop_name_…` and `test_a_panel_open_on_what_is_chosen_stays_open_…` fail run
  alone too; the first was run again with ELK's script tag put back into index.html (so nothing is lazy) and
  still failed, so lazy ELK is not its cause; the Diagram page runs none of the other new code.
The Guide's `test_the_guide_draws_every_frame_live_and_in_a_snapshot` (drawStatic, ELK inlined in a snapshot) and
`test_a_snapshot_page_still_routes_its_lines` passed. Main is the base as cloned (no newer main to merge).

## Entry

section: Done recently

- **The item page draws its path** (item-page-draws-its-path): under *Where it went*, a closed *Draw its path* with
  a Dynamics / Blocks switch draws `item=ID` in place (drawStatic, moved out of the Guide); a click on a part opens
  the diagram with it chosen. ELK is now loaded on the first layout, not by every page.
