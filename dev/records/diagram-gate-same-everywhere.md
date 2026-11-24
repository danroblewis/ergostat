# diagram-gate-same-everywhere: The clean-drawing gate gives the same answer on every machine

tests/test_diagram_rendering.py::test_every_view_draws_cleanly_and_in_time passes on the coordinator's machine for all examples on main 617734422, and fails on 8 of 23 in the agents' container (alert-triage, big, coordinator, image-squeeze, ops, software-factory, the-job, ticket-factory: lines through parts, overlaps, crossings in a net, drawings up to 1.6x their recorded size). The gate that pins the drawings cannot judge a rewrite while its answer depends on the machine.

Change. Find what differs (fonts and text measurement, browser version, device scale, timing) and make the drawing depend on none of it: pin the font files the pages use (served with the app, not system fonts), the Chromium build, the device scale factor and viewport in the test; measure text from the pinned font. Then re-record the fault ceilings and sizes once, from the pinned setup, in tests/fixtures (layout_known.json, diagram_sizes.json), with the before and after lists in the record.

Done. The test gives the same result in the agents' container, the merge queue's container and a plain local run, on all examples, three runs each.
