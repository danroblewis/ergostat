# blocks-uncoupled-systems-parallel-rows: Blocks: uncoupled systems are parallel rows with their own r and y and a caption saying no signals join them

depends-on: [blocks-textbook-levels-proposal, blocks-top-level-reference-and-sum]

Problem (R4 piece 5): on big the Blocks top level is seven boxes in a column with no signals, on the-job two unconnected boxes (shots/ceb-big-blocks-dark.png, sreb-job-blocks-fit.png); a reader cannot tell whether signals are missing or there are none. The top-level assembly (ergostat/blockdiagram.py:1325-1341) is restructured by blocks-top-level-reference-and-sum into one function over groups of systems; this gap adds the uncoupled group to it, so it follows that gap.
Change, as the proposal settles: systems with no signal between them are laid as parallel rows (a new arrangement of the top level: rows stacked, not ELK's column of boxes), each row drawn as its own loop outline with its references r entering on the left and its outputs y leaving on the right (counts as vectors), and one caption under the group: 'no signals between these systems'. Coupled systems keep the form of blocks-top-level-reference-and-sum; a model with both shows the coupled group first.
Definition of done:
1. On :8797 ?view=blocks each of the seven systems is a row with r on its left and y on its right, and the caption is present.
2. On :8792 the two systems are two rows with the caption.
3. On :8796 (coupled) the caption is absent.
4. Rows are ordered as the systems are in Dynamics; text at least 11 px.
Files: ergostat/blockdiagram.py, ergostat/web/static/blocks.js, layouts.js, tests/test_diagram_rendering.py.
Acceptance tests: browser checks 1-3; a unit test that an uncoupled spec yields rows with r/y ports.
Budget: 100 net lines.

Milestone: r4-blocks-textbook. Owner items: R4 piece 5. From the owner's list and the design review of 2026-11-22.
