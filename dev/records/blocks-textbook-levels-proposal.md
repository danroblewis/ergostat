# blocks-textbook-levels-proposal: Proposal: Blocks above the leaf: classified subsystems, a top level with references and summing junctions, rows per loop (docs/proposals/blocks-levels.md)

depends-on: []

Problem (R4): at the leaf the notation is right (summing junctions, r/e/u/y/d, H on the return, C(z) with sampler and hold). Above the leaf it is not a block diagram: the top level is opaque 'Q' boxes, seven in a column with no signals on big, two unconnected on the-job, one unlabelled wire on ticket-factory; no reference, no summing junction; Q is undefined (it reads to a control engineer as the Youla parameter) and changes to P with different dimensions when opened (shots/story-6-g6-blocks-top.png, ceb-annotated-sf-top.png, ceb-big-blocks-dark.png, story-7-h2-into-api-blocks.png). Inside, loops are not laid in signal order (story-6-g5-blocks-making.png, ceb-big-api-blocks.png). Subsystem nodes and their vectors are built in ergostat/blockdiagram.py (:1325-1341, :1423) and drawn in blocks.js.
Change: write docs/proposals/blocks-levels.md settling: (1) classification of a subsystem as C (it holds controllers acting on another system's process), P (it is acted on) or a named block when mixed, with the same letter and p x m at both levels (the disturbance counted at both); Q dropped; (2) the top level's form: references and a summing junction ahead of the controlling subsystem, labelled signals between systems, H on the return (acceptance: story G6 on software-factory); (3) uncoupled systems as parallel rows each with its own r and y and the caption 'no signals between these' (big, the-job), built on the same top-level assembly as (2), after it; (4) the row layout inside a system: one loop per row in signal order, upstream first, couplings downward, the sensor under its own process (acceptance: story G5 on ticket-factory making and the chain on big api), and whether ELK layered can do it with constraints (with diagram-layout-engine-proposal); (5) how the closed block's r/y and status (blocks-closed-block-r-y-and-status) sit on the classified block's ports. It confirms or amends the four build gaps.
Definition of done:
1. The proposal settles 1-5 with a sketch for :8796 top level, :8797 top level and ticket-factory making.
2. A control engineer's textbook reference is cited for each form.
3. It lists the tests each build gap must add.
Files: docs/proposals/blocks-levels.md, docs/DISCIPLINES.md (link).
Acceptance tests: review only.
Budget: about 200 lines, no code.

Milestone: r4-blocks-textbook. Owner items: R4 (pieces 3-6). From the owner's list and the design review of 2026-11-22.
