# diagram-routes-fast-then: two-stage routing in the worker, a fast pass drawn first and the careful pass swapped in only while its drawing is still current
depends-on: []

## Definition of done
- When the main diagram (`avoidStart` in `ergostat/web/static/avoid.js`) asks the worker for routes, it gets two answers for one request. First comes a fast pass that routes every line with no crossing weighing (crossing penalty 0 in every group). The page draws it at once, with the same after-passes as today (straighten, untangle, uncross, the dynamics passes, unjog). Then comes the careful pass with today's penalties.
- The careful answer replaces the fast lines only if all three hold when it arrives: its layout is still `S.layout`, no newer route was asked, and no part of that layout was moved (dragged) since the route was asked. Otherwise it is dropped: the fast lines stay, nothing is redrawn from it, and routing for that layout ends. The worker does not start a careful pass when a newer route or a move is already queued. It answers that careful pass as skipped.
- A layout gets each step once from the router's first pass (valve slides and turns), not once per stage. After the careful swap, valve positions equal those after the fast pass.
- `lay.routing` stays true and `lay.whenRouted` stays pending until the careful pass is drawn or dropped. That way the layout rules and the existing tests that wait for routing still judge the careful lines. Drags between the two stages work on the fast lines as they do on routed lines today.
- The page-mode fallback (no worker: snapshots) and the Blocks and Process views keep a single routing, unchanged.
- SPEC's diagram section says in one sentence that lines are drawn from a quick routing first and refined in the background.
- House rules: the acceptance tests exist and pass; the unit suite and the four browser files pass with rc 0 and no page test is skipped for want of a port; ruff is clean; origin/main is merged in and the suites are run again. For each acceptance test, the branch's report names the break in the code that was seen to make it fail.

## Relation to other work
- gap/diagram-line-tones: active, may touch diagram drawing in `ergostat/web/static`; this gap edits only `avoid.js`'s routing request and answers, not line styles.
- gap/diagram-frames-corners: active, frame drawing; no shared code expected, so merge main before review (lesson-7).
- gap/ui-the-blocks-legend-defines-every-symbol-and-a-nam: active in `ergostat/web`; this gap leaves `blocks.js` untouched.
- gap/ui-the-diagram-loads-without-console-errors: merged, changed `avoidCore` pin placement; builds on it.

## Files to touch
- `ergostat/web/static/avoid.js`
- `tests/test_diagram_rendering.py`
- `docs/SPEC.md`

## Risks
- lesson-1: the page checks "still the current layout" and then writes the careful lines, but a drag or re-route can land between the fast and the careful answer, so careful lines at old places overwrite the dragged lines.
- lesson-5: one layout object takes two answers, so the valve slides/turns are applied twice or `AV.routed` keeps the fast state.
- lesson-9: a test that never holds the careful answer back never opens the window between the two stages and passes whatever the page does.

## Acceptance tests
- `tests/test_diagram_rendering.py::test_fast_routes_drawn_before_careful`: with the worker's careful answers held back by the test, the page has drawn routed lines (every line end within 4 px of its part) while `S.layout.routing` is still true. When they are released, the careful lines are drawn and routing ends. It fails if the fast answer is not drawn.
- `tests/test_diagram_rendering.py::test_careful_routes_of_replaced_layout_not_drawn`: the careful answer is held, then the view is toggled to a new layout, then the old careful answer is released. The current drawing's lines do not change. It fails if the current-layout check is removed (lesson-1).
- `tests/test_diagram_rendering.py::test_careful_routes_dropped_after_a_drag`: the careful answer is held, a part is dragged 150 px, then the careful answer is released. Every line of that part still ends within 4 px of its new place. It fails if the moved-since check is removed (lesson-1).
- `tests/test_diagram_rendering.py::test_valve_slides_applied_once_across_stages`: on a dynamics demo whose valves slide, valve positions after the careful swap equal those after the fast pass. It fails if the slides are applied for both answers (lesson-5).
- `tests/test_diagram_rendering.py::test_queued_careful_pass_skipped_for_newer_route`: two routes are asked back to back while the worker is busy. The first route's careful pass is answered skipped, and only the second's careful lines are drawn.

## Size budget
110 net lines
size: M (confidence: medium)

## Where it stopped
Built, round 1. About 40 net lines in `avoid.js`, within budget. SPEC's sentence is in §4a "Drawn as parts", the
main diagram's paragraph (SPEC has no diagram section of its own).

How it works: `avoidStart` posts `route` with `refine: true`. The worker answers `routed` from a pass with
`spec.fast` (crossing penalty 0 in every group). It then queues a `careful` job behind whatever arrives meanwhile,
and answers it `refined`. The job is skipped when a route or a move was asked in the same batch or is queued
before it. The careful pass is `core.route(spec, true)`: no first pass, on the spec the fast pass already slid and
turned, so it brings no slides or turns. The page also never applies slides or turns from a careful answer.
The page draws the careful answer only when all three hold: `lay === S.layout`, `lay.routeSeq === seq` (no newer
route of this layout) and `lay.moves` unchanged (counted in `avoidMove`/`avoidMoveMany`). Otherwise it drops it.
`lay.routing` turns false, and `whenRouted` resolves, only on the careful answer (drawn or dropped), and only
for the layout's latest route. Blocks and Process post no `refine`, and page mode is unchanged: one routing each.

Choices taken without asking (the most reversible):
- "Toggled to a new layout" in the second test is `S.relayout()`: a new layout object, drawn.
- "The current drawing's lines do not change" is checked as the layout's sections, `AV.raw` and `AV.routed`.
  Every real toggle also asks a newer route.
- "No newer route" is per layout (`lay.routeSeq`), not the global `AV.seq`.
- The fifth test also checks a route with a move queued behind it, and the busy route's own careful pass.

Each acceptance test was seen to fail on a break in the code:
- test_fast_routes_drawn_before_careful: the fast answer not applied (`done(m)` only when skipped); timed out
  waiting for the fast lines.
- test_careful_routes_of_replaced_layout_not_drawn: `lay === S.layout` removed; AV.raw changed to the old routes.
- test_careful_routes_dropped_after_a_drag: the `lay.moves` check removed; 5 line ends left at the old place.
- test_valve_slides_applied_once_across_stages: the careful pass with its first pass and the page applying its
  slides and turns; deps' flow:update-opened slid twice (y 334.7 to 363.7).
- test_queued_careful_pass_skipped_for_newer_route: the move-queued skip (`todo.length > 1`) removed; the
  in-queue skip (`asked`) removed; both together with the wholesale `refined` skip removed. Each failed.

Suites: ruff is clean. The five acceptance tests pass. `tests/test_diagram_rendering.py` was run whole on this
branch: 34 failed and 293 passed, none skipped. All 34 also fail with the page switched to single-stage routing
(main's behaviour), and those reruns all failed for the same reasons:
- 21 `test_sensors_are_blocks…[*]`: a `<title>` tooltip from `dynamics.js:467`, a file this branch leaves alone.
- `every_view…[image-squeeze, coordinator]`: routing over ROUTED_BOUND_MS on this machine (21.8 s and 20.3 s
  single-stage).
- `every_view…[autoscaler, the-job, ticket-factory]`: layout-rule ceilings.
- The rest are Blocks-view, keyboard, PNG, panel and Model-page tests.
The factory runs these again on clean main.
Not run by me, as the rules say: the unit suite, the other three browser files, demo_check (no example touched).
main (a08e4b3e) was already merged into the branch before the work, and nothing newer is on main.

Cost of the change, said plainly: `whenRouted` now waits for both passes. On image-squeeze open=* (this machine,
loaded) the fast pass took about 4.8 s of worker time and the careful pass about 21 s. TIMED rose from 21.8 s
(single-stage) to 26.4 s, while the first routed lines come at about 5 s instead of about 22 s. Where a view
routes close to ROUTED_BOUND_MS on main, this branch can push it over. The bound was not raised. A cheaper fast
pass, or a bound on the fast stage, would be a gap of its own.

Build step after round 1 (rc 5): `scripts/affected_tests.py` picked only `tests/test_diagram_rendering.py`, because this
branch changes no `ergostat/**/*.py`. That file is a Playwright browser file, and the build step's pytest has no
`playwright`. So its one module-level `importorskip` skipped everything, and pytest exited 5 (no tests ran). No test
failed, and nothing in `avoid.js` caused it: any branch that changes only static JS and a browser test file gets the
same rc 5. The code was left as it is. I did not add a unit test just to give the step something to run, and I did
not change `affected_tests.py` (it is outside this gap, lesson-13). The most reversible choices left are to run this
gap's build step with `build_browser = true` (Playwright installed), or a gap of its own where `affected_tests.py`
counts a browser file as covered by the browser suites. Commands refused in this session: `git log --stat -3`, the
first shell command I gave, was denied, so no shell command was run in this round.
