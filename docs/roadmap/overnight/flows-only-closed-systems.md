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
