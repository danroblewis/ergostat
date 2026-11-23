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
