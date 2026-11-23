# diagram-spoken-names: Every part of the diagram has a spoken name in its discipline's words, with its state and the loops it belongs to

depends-on: []

Problem (R9 piece 5): the diagram is one unnamed SVG; a screen reader hears nothing useful for a stock, a valve, a connector or a block (shots/a11yb-8793-into-service-block-click.png, a11yb-8793-deadband-panel.png). Filed Q74 gives parts a name for focus; the names need to carry what a sighted reader sees.
Change: one function per view builds each part's accessible name (aria-label on the part's group, role img or button as Q74 set): Dynamics: 'stock users, 152 of desired 180, in product; in balancing loop word of mouth and 2 others'; 'flow signups, 3.1 per hour, from cloud to users'; 'connector from churn to support load, positive'; 'goal gap users-at-180, off by 28' (the goal's state is its `word` from the server when goal-row-one-renderer has landed, never a second mapping). Blocks: 'controller C keep-located-worked, on-off, control loop located-worked, off'; 'summing junction of located-worked: reference minus measurement'; 'signal e, error, minus 36'. System boxes: name, description, goals holding and off. Names use each discipline's words only (no 'sensor' in Dynamics), update with values on the poll without stealing focus, and the SVG itself has the caption of filed Q02 as its name.
Definition of done:
1. On :8791 in both views every focusable part has a non-empty aria-label containing its kind word and its name; none contains 'undefined' or a raw id with a colon.
2. A stock's label contains its value and unit; on a fixture an off goal's contains 'off'.
3. No Dynamics label contains 'sensor' or 'controller'; no Blocks label contains 'stock'.
4. A unit test covers the name function for each part kind in each view.
Files: ergostat/web/static/dynamics.js, blocks.js, process.js, diagram.js, tests (a JS unit test or a browser test reading labels).
Acceptance tests: the label sweep over the six demos; the vocabulary check in 3.
Budget: 120 net lines.

Milestone: r9-diagram-without-a-mouse. Owner items: R9 piece 5. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built (round 1). Each view has one name function: `sdSpoken` (dynamics.js) and `bdSpoken` (blocks.js), for every part kind, each line and each frame. Q74 had already landed as keys.js, which makes every clickable part a `role="button"` with an `aria-label` after each draw. So the names go in through its `ariaOf` (keys.js, 5 lines), not new attributes in diagram.js: that is the smaller and more reversible place, and the focus keeping is still keys.js's own. Goal states are `goalWord` (goalrow.js), never a mapping here. The SVG's name is still the Q02 caption (unchanged). Net lines outside tests and docs: about 69 of 120.

Choices made with nobody to ask (each easy to undo):
- "The six demos" are taken as six examples under examples/: software-factory, ticket-factory, image-squeeze, first-loop, autoscaler, ops (`SPOKEN_DEMOS`). The sweep serves each from a fresh copy on a free port, not the owner's :8791, which this container does not have. Item 1 on :8791 itself was not run here.
- "Both views" are taken as Dynamics and Blocks. The Process view keeps the names keys.js already gives it, and process.js and diagram.js are unchanged.
- Item 2's value and unit: the demos are served unrun, so a stock has no value there. The sweep checks each stock's unit; the value and an off goal's 'off' are checked on the fixture in the unit test.
- The Blocks frames (an open system, a cascade's inner loop) are named too. Blocks says 'subsystem NAME, open' for an open system.

Tests: tests/test_diagram_rendering.py::test_every_focusable_part_is_named_in_its_views_words_with_its_kind_and_name (the sweep, items 1-3: kind words checked against each view's allowlist, the name, no undefined/null/NaN or word:word id, the vocabulary check) and ::test_each_views_name_function_speaks_every_part_kind_with_its_state_and_loops (item 4, with item 2's fixture). Seen to fail: with the keys.js routing turned off (old names: "pipe line from ..."), and with "stock" added to every Blocks name.

Failing with and without this change, so not caused by it (lesson 13, left alone): test_everything_clickable_in_the_diagram_is_reached_and_acted_on_by_keyboard (the focus never moves to the opened panel's heading, a 5 s timeout at line 2576) and test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known (the side panel says "goal ... cannot close" and "serves goal"). Both were run again with the new names turned off in keys.js, and both failed the same way.
