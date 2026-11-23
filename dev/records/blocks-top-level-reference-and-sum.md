# blocks-top-level-reference-and-sum: Blocks top level: references and a summing junction ahead of the controlling subsystem, labelled signals, H on the return

depends-on: [blocks-subsystems-classified-c-p]

Problem (R4 piece 4): the Blocks top level shows subsystem boxes joined by an unlabelled wire, with no reference, no summing junction and no return path, so it does not read as a control loop (shots/story-6-g6-blocks-top.png, ceb-annotated-sf-top.png). Story G6 on software-factory failed. Needs the C/P classification to know which subsystem controls which.
Change, as the proposal settles: when a C subsystem's controllers act on a P subsystem's processes, the level above draws the loop between them in textbook form: the references r (a vector when several, with count) entering a summing junction ahead of C, the error e into C, the command u from C to P labelled, the output y leaving P, and the return through H (the sensing vector) to the junction's minus input. Signals between systems are labelled with their names or 'k signals' as vectors. The disturbance d enters P. Built in ergostat/blockdiagram.py's top-level assembly (:1325-1341), which this gap restructures into one function taking groups of systems (coupled groups here; blocks-uncoupled-systems-parallel-rows adds the uncoupled group to the same function), drawn with the existing glyphs in blocks.js.
Definition of done:
1. On :8796 ?view=blocks top level a summing junction precedes the controlling subsystem, with r, e, u, y labelled and H on the return (story G6 passes).
2. Every wire at the top level has a label.
3. Opening either subsystem shows the same signals at its frame's ports.
4. Layout rules report no new critical violation on the six demos.
Files: ergostat/blockdiagram.py, ergostat/web/static/blocks.js, tests/test_diagram_rendering.py, a blockdiagram unit test.
Acceptance tests: unit: a two-system spec yields junction, r, e, u, y and an H return at the top level; browser: story G6 on :8796.
Budget: 160 net lines.

Milestone: r4-blocks-textbook. Owner items: R4 piece 4. From the owner's list and the design review of 2026-11-22.
