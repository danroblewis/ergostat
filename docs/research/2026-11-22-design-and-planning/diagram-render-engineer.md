# Diagram correctness and speed (owner items 5, 7, 10): engineer's notes

Read-only study of `ergostat/web/static/` on current main (2468c59b), with measurements in a headless
browser on the demos (probe scripts in `scratchpad/plan-diag/`, screenshots `shots/plan-*.png`). The
probe reads every drawn line's path in the visible SVG and measures how far each end is from the part
it joins (as drawn, including a part being dragged); "off" below means more than 24 px away.

## How a drawing is made (what matters for these items)

1. `pageDiagram` (diagram.js:1017) builds a new SVG on every route: every view switch, Open/Close,
   Into, "Wrap loops into rows" and "Open/Close all" call `go()`/`route()` (util.js:498), which
   empties `#main` and calls `pageDiagram` again.
2. `tick` asks `/api/graph`, `show` (diagram.js:1169) sets the global `S.graph` (1171), awaits
   `layoutGraph`, then sets the global `S.layout` (1239) and draws (1247).
3. `layoutGraph` (diagram.js:74) runs ELK (elk.bundled.js on the **main thread**: `new ELK()` with no
   worker, util.js:6), then a chain of passes that move parts: flatten, `placeSatellites` (188),
   `packLoose` (189), a re-layout when ports face away (197, up to twice), `restack`/`routeCuts`,
   `anchorLayout` (204), `seatCloudFlows` (206), `centreValves` (207), a second whole layout to compare
   without satellites (212), then `applyPins` and `orientValves` (226-227). Most of these move parts
   and leave ELK's lines where they were.
4. `avoidStart` (avoid.js:620) sends every line to libavoid in a worker; when it answers, six more
   page passes run (straighten, untangle, uncross, sdSeparate, sdAroundSatellites, unjog) and the
   page redraws only if that layout is still `S.layout` (avoid.js:657). An older routing still queued
   is answered `skipped` (avoid.js:326) and its layout keeps ELK's lines.
5. Dragging (interact.js:184-280): each pointermove sends the parts' places to libavoid
   (`avoidMoveMany`, one at a time, the latest) and redraws the lines that came back.

## Item 7: lines do not follow a dragged part

**Cause found (confirmed).** `panZoom(svg)` (diagram.js:881) calls `interactions(svg)` (diagram.js:898),
which adds `pointermove`/`pointerup` listeners to `window` (interact.js:187, 210, 231, 252) bound to that
page's SVG. They are never removed. After one route (any toggle, Open, view switch, or a visit to
another page and back) there are two sets; the oldest one, bound to the detached SVG, takes the shared
`S.nodeDrag` first: it greys and redraws lines in the detached SVG, sets `d.moved` and `d.busy`, so the
visible SVG's handler greys nothing and never redraws a line. On drop the oldest handler calls
`putDown(oldSvg)` (interact.js:165), which draws into the detached SVG. The visible lines move only when
the full re-route after the drop finishes and `S.redraw` fires, or at the next poll (2.5 s, up to 60 s
when the graph answer is slow), or on reload: "not updated until a refresh".

Measured on :8791 `open=*`, dragging `model-error` 150 px: on a fresh page the visible lines caught up
1.0 s into the drag; after one `route()` they had not moved 6 s later (7 lines 103-184 px off, not
greyed), while the detached SVG's lines had changed. After three toggles: not moved after 8 s.

**Also slow when it works.** Each move is a libavoid transaction over the whole router with crossing
weighing on (avoid.js:283, 292): 0.4 s per move on ticket-factory `system=factory`, ~1 s with
everything open, ~2 s on software-factory. Until it answers the lines stay at the old place, greyed.

**Change.** Listeners once per page (an `AbortController` per `pageDiagram`, aborted by `route()`), or
added once at module level reading the current SVG; draw an immediate stand-in on every pointermove
(the end on the moved part and its neighbouring bend shifted by dx, dy, greyed) so a line never points
at the old place; route drag moves with crossing weighing off (set back for the full routing on drop).

**Risk.** Low. The Blocks and Process views share `interactions` and get the same fix. Existing drag
tests (test_diagram_rendering.py:556, 614, 672) drag only on a freshly loaded page, which is why this
was never caught: a new test must drag after a route.

**Size.** Quick to incremental (about 60-90 lines in interact.js and diagram.js, plus one test).

## Item 5: lines connect to nothing after toggles

**Causes found.**

1. *ELK's lines are drawn after parts have moved* (confirmed). The passes in step 3 move parts but not
   lines; `squareLines` (interact.js:117) greys only lines with a slanted piece. Until libavoid answers,
   lines run from where ELK left the parts. On image-squeeze (:8793, `open=*`) after Open/Close of one
   system, 40 of 183 drawn lines had an end 81 to 759 px from its part, most **not greyed**; this lasts
   the whole routing, 8 to 10 s there. On the-job (:8792) after a Wrap toggle, 48 of 240 lines, ends
   64 to 92 px off, for about 1.7 s. This is what the owner sees: lines pointing at an old position
   while "several passes of positioning and path finding" have not all finished.
2. *An old page's drawing can overwrite the new one's state* (by reading). `route()` stops the poll
   (util.js:503) but not a `tick` already awaiting its layout; that `show` then writes the global
   `S.layout` and `S.graphSig` (diagram.js:1239-1240) after the new page set them. With the same
   structure signature (Wrap, Flows only, a view toggled back) the new page keeps drawing that layout;
   if its routing was answered `skipped` (avoid.js:326) its lines stay ELK's for good.
3. *Lines libavoid never sees.* The wrapped rows' coupling pipes (`routeCuts`, diagram.js:310) are
   excluded from routing (avoid.js:399, `!le.cut`), and `applyPins` moves their ends and drops their
   bends (places.js:306-313): after a pin or drag they stay a greyed L-shape at the old place.
4. libavoid's port pin at `x = c.width` (avoid.js:516) logs "xOffset value … greater than shape width"
   on every load with closed systems. Already filed as Q81 (gap/ui-the-diagram-loads-without-console-errors).

**Change.** A generation number per `pageDiagram`; `tick`/`show` and routing callbacks give up when it
is not the current one. At the end of `finishLayout` (diagram.js:223), and after `applyPins` on a drop,
every line whose end is more than 4 px off its part (or port) is replaced by an orthogonal stand-in
from the parts' current places and greyed (`le.stale`), and cut lines are recomputed the same way, so no
drawn line ever points at a place a part has left. Optionally keep the previous drawing dimmed until
the new one has routed lines (Q11 asks for the dimmed drawing already).

**Risk.** Medium-low: the layout rules (tests/layout_rules.py) read the routed geometry, not the
provisional one; the stand-in must not count as a routed line in tests that wait for `!S.layout.routing`.

**Size.** Incremental (diagram.js, interact.js, places.js, a test; about 100 lines).

## Item 10: layout time, and a re-arrange for Flows only

**Where the time goes (measured, demos with everything open).**

| demo | parts / lines | ELK runs on a toggle | ELK total | libavoid | to routed lines |
|---|---|---|---|---|---|
| ticket-factory :8791 | 108 / 155 | 2 | 84 ms | 667 ms | 1.1 s |
| the-job :8792 | 203 / 240 (toggle: 183 / 217) | 1, **10** on a toggle | 39 ms, **1.6 s** | 590-815 ms | 1.2 s, 3.6 s |
| image-squeeze :8793 | 163 / 202 | 2 | 94 ms | **8.3-9.4 s** | 9.3-11 s |
| software-factory :8796 | 63 / 92 | 2 | 60 ms | 1.3 s | 1.7 s |
| big :8797 | 143 / 175 | 1-3 | 64-112 ms | 260 ms | 0.7 s |

- **Routing, not ELK, is the time**, and within routing the crossing weighing: on image-squeeze the
  same spec routes in 183 ms with `crossingPenalty` 0, 7.0 s at 20 and 15.6 s at 80 (the page uses 50).
  scale.md row 13 already records routing as about shapes^2.8.
- ELK is cheap per run (16-350 ms) but is run up to 10 times for one change on the-job: the port-turn
  re-layout (diagram.js:197, twice), the whole second layout without satellites to compare (212), the
  wrap trial in `show` (1236), and the preset's wrap/stack retries (layouts.js:226-236). It runs on the
  main thread, so the page does not answer while it runs.
- The page polls every 2.5 s and redraws the whole SVG each time; with a changed structure (the live
  factory adds parts as items arrive) it lays out and routes again from nothing.
- The live factory (:8798) answered no GET (page, static file, `/api/status`, `/api/graph`) within
  100 s during this study; that is owner item 2's cluster (the notation engineer saw the same).

**Flows only today** is a CSS class (diagram.js:1066-1068, style.css:550-553): "nothing moves", so the
pipes keep the places the full diagram gave them, around auxiliaries that are now hidden. A layout of
the flows alone (the same `sdFlowLinks` set, dynamics.js:499, with stocks, valves, clouds, systems and
flow ends), tried in the page with the current engine: ELK 29-116 ms, routing 54-287 ms, and a
drawing 40-60% the area of the full one (ticket-factory 73 parts / 66 lines, image-squeeze 127 / 102,
the-job 147 / 128). So the re-arrange the owner asks for needs no new engine: Flows only becomes a
layout of its own, and "Unpin all parts" (diagram.js:1056) becomes "Re-arrange" in the same menu.

**Is a rewrite warranted?** Not on this evidence, not yet. The slowness is one parameter's cost in the
router, plus avoidable repeated ELK runs; the wrong lines are three specific bugs. What is warranted is
(a) the fixes above, (b) a fast-first routing (no crossing weighing, drawn at once, then refined in the
background and swapped in when it is still the current drawing), fewer ELK runs, ELK off the main
thread and a cache per structure, and (c) a proposal that decides the larger questions with numbers
taken after (b): whether the 15 passes between ELK and libavoid should become one geometry owner,
whether Dynamics should use a domain layout (chains of a conserved quantity as rows, upstream first;
connectors as arcs, as Vensim draws them, instead of orthogonal routes eased into curves), how a
system opens without moving the others (R8 piece 5), and how a large view routes only what is shown
(scale.md #13). The layout corpus and its `--engine ../other-checkout` comparison
(docs/layout-rules.md) make any rewrite measurable against today's.

## Gaps proposed

1. `diagram-drag-lines-follow` (item 7; quick/incremental).
2. `diagram-lines-never-point-at-old-places` (item 5; incremental).
3. `diagram-routes-fast-then-refined` (item 10, speed; incremental; after 2).
4. `flows-only-is-its-own-layout` (item 10, re-arrange; incremental).
5. `diagram-layout-proposal` (item 10, rewrite question; large: a proposal first).

Overlaps: Q81 (pin offset error, filed), Q11 (dimmed old drawing until the new one is ready, filed),
Q71 (Fit includes every wire, filed: stale lines out of the frame skew Fit), R8 pieces 1 and 5, R4/R5
(layout work), the notation engineer's MIMO proposal (trunk bundling after the layout work).

## Questions for the owner (one sentence each)

- May a first drawing show lines that cross more than they will a second later (fast routing first,
  refined in the background), or must the lines never change once drawn?
- Should Flows only remember parts you place by hand separately from the full diagram?
