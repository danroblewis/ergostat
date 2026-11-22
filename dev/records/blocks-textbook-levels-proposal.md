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

## Where it stopped

Written: docs/proposals/blocks-levels.md (settles 1-5, sketches for software-factory's top level, big's top level and
ticket-factory making, a textbook citation for each form, the tests each build gap adds) and the link in
docs/DISCIPLINES.md. Choices made alone, each the most reversible: :8796 is read as software-factory and :8797 as big
(from the screenshots' names); the build gaps' names are the proposal's own; uncoupled rows follow model order. The
widths in the sketches are read from the YAML: running a script to print `diagram()` was refused in this session, so
the build gaps' tests pin them. Nothing left for this gap beyond review.

Round 2 (answering review 1's two findings, both blocking; there were no others):
- Classification contradiction (§1): the rule now reads only the wires crossing a system's border, marked u
  (set by a controller inside the source, entering the target's flow or stock) or y. C means u wires out and none in.
  P means u wires in and none out. Named covers both (mixed) and neither. Inner loops never enter the rule, so
  software-factory's factory is C with no second answer. Test 1 now computes the class from the edges for every
  system and adds a mixed a → b → c fixture.
- Uneven `modelling` counting (§2/§3): one rule, rows are the connected components of the top level's
  system-to-system edges, with `modelling` counted as any system. A table gives the counts: software-factory 2
  (the §2 loop, then modelling), ticket-factory 2, big 7, the-job 2. The software-factory sketch places modelling
  as the second row. Tests 2 and 3 follow this rule. The proposal says these counts assume, from the YAML, that
  modelling has no top-level wire. If it has one, the rule decides.
- Not run: `diagram()` was never printed. A shell command was refused in this session (a grep and sed over
  blockdiagram.py and the examples), so the facts were read with the file tools.
Overrun reason: the proposal is 236 lines against about 200, because round 2 adds the u/y wire rule, the rows table and the modelling note that review 1 asked for.
