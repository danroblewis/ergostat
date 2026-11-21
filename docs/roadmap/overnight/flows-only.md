# flows-only: the Dynamics page's ⋯ menu toggles a flows-only view

depends-on: []

The owner (2026-11-20): "on the dynamics page, I want another button (in the dropdown menu with Unpin Parts and Open all
systems) that toggles to only show flows, the double-line things, not showing the information links or anything else
that is not a connector."

## Definition of done

- The ⋯ menu on the Dynamics view (`ergostat/web/static/diagram.js`, the `more` menu beside "Show loop markers") has a
  checked item **"Flows only"**. On, the diagram shows only the flows (the double-line pipes with their valves) and what
  they connect (stocks and the clouds at their ends); information links, auxiliaries, constants, sensors, goals and loop
  markers are hidden. Off, the diagram is as before. Only on the Dynamics view.
- Done as a body class (like `no-loops`) and CSS, not a re-layout: the parts keep their places, so toggling is instant
  and pins are untouched. Remembered per browser in `localStorage` (`ergostat.flowsOnly`), read with try/catch as the
  loop markers' is.
- Both themes; works in the SVG export only as shown on screen (the export of a flows-only view is flows-only).

## Acceptance tests

- `tests/test_diagram_rendering.py::test_flows_only_hides_links_and_non_flow_parts` (a browser test: toggle on, no
  visible `.info` paths or auxiliary/goal nodes; stocks and flows still visible; toggle off restores them)
- `tests/test_diagram_rendering.py::test_flows_only_is_remembered`

## Size budget

40 net lines of code outside `tests/` and `docs/`.
