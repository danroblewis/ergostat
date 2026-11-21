# flows-only-closed-systems: flows-only shows the flows between closed systems

depends-on: []

The owner asked for a Dynamics toggle that shows "only flows, the double-line things". An audit found that on the view the page opens with (systems closed), `software-factory` loses all 6 of its connections: three boxes are left, no pipes, and port labels such as `bugs-live` and `fixes` point at nothing. The hide rule keeps only `.edge.pipe`, and a connection between closed systems is not drawn with that class even when what crosses is a flow. The acceptance tests only used an open view.

## Definition of done
- With systems closed, a connection that carries a flow across a system boundary stays visible; a connection that carries only information is hidden. Which is which comes from the model, not from the drawing's class alone.
- A port with no visible connection is hidden. Its row returns when the toggle is off.
- If a level has no flows at all, the diagram says so in place and names the way to see them (open a system), using the existing diagram surface: no new panel.
- The exported SVG's legend lists only what the flows-only view shows.

## Files to touch
`ergostat/web/static/diagram.js`, `ergostat/web/static/dynamics.js`, `ergostat/web/static/style.css`, `tests/test_diagram_rendering.py`.

## Risks
- lesson-9: each test must fail on today's code, on a closed `software-factory` view.

## Acceptance tests
- `tests/test_diagram_rendering.py::test_flows_only_keeps_flows_between_closed_systems`
- `tests/test_diagram_rendering.py::test_flows_only_hides_information_links_between_closed_systems`
- `tests/test_diagram_rendering.py::test_flows_only_hides_ports_with_no_connection`
- `tests/test_diagram_rendering.py::test_flows_only_says_when_a_level_has_no_flows`
- `tests/test_diagram_rendering.py::test_flows_only_export_legend_lists_only_what_is_shown`

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built (round 1); 31 net lines of code (diagram.js +5, dynamics.js +22, style.css +4), and one phrase in
docs/QUICKSTART.md. **Not run in a browser:** this container has no Playwright, so the five acceptance tests skip here
and none was run, nor broken on purpose to watch it fail (lesson-9). They rest on the factory's browser gate running
`tests/test_diagram_rendering.py`, not skipping it. The graph the tests name was checked against the server's real
answer: on the closed view, `/api/graph?view=dynamics` gives the three boxes and exactly the six connectors the tests
list, and the edited model the no-flows test serves loads with only the three stock reads left.

Choices made alone (each easy to undo):
- **What "carries a flow" means.** Every one of the six lines between closed systems in `software-factory` is a
  connector, so the drawing class can't tell them apart. The rule, in `sdFlowLinks` (dynamics.js), reads the model:
  a pipe, or a line that crosses a system's edge (at a port, or ending at a shadow or a stub) whose tail part is a
  flow (a valve or a disturbance, i.e. a flow's rate goes across). So `deployed` → `fixes`, `regressions` and
  `shipped` stay; `bugs-live`, `missing-ops` and `users` read by intake's flows are information and are hidden. A
  shadow or stub at the end of a kept line stays too.
- **Open systems are unchanged.** A connector from a flow to a flow, both drawn in open systems (`open=*`), is still
  hidden, as `test_flows_only_hides_links_and_non_flow_parts` requires (no `.info` line seen). Giving it the same
  rule would change that accepted test, so this gap leaves it alone.
- **The note** is an SVG text in the drawing itself, centred above it, shown only with Flows only and only when the
  level keeps no line at all. Because it is part of the drawing, an export made with Flows only on carries it too.
- **The legend with Flows only** lists stock and source / sink when the level has them, flow and biflow only for
  pipes kept, and connector + / − only for the signs of the lines kept. It never lists auxiliary, exogenous or the
  loops. export.js was not touched, so a view with no stock (the closed view itself) still gets no legend. That is
  why the legend test uses `open=product`: factory and modelling stay closed, and `<deployed>`'s lines into
  product's flows are kept.
- **lesson-9's "closed software-factory view":** tests 1 to 3 use the plain closed view. Test 4 uses the closed view
  of a copy with `deployed`'s couplings taken out, since the real model does carry flows across. Test 5 uses
  `open=product` (reason above). Each asserts something today's code does not do: links kept, the exact set hidden,
  ports hidden, the note, the legend without auxiliary or loops.
