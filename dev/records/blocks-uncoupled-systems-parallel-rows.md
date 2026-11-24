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

## Where it stopped

Built, round 1. 99 net lines outside tests and docs (blockdiagram.py 56, blocks.js 41, style.css 2), within the 100
budget. layouts.js is not changed: the rows are stacked in blocks.js after ELK (the proposal's fallback, "blocks.js
stacks rows that ELK laid out separately"), so no ELK preset was needed. style.css, not in the Files list, gets the two
rules for the outline and the caption (no inline styles in the canvas).

- blockdiagram.py: `fold()` passes `_top_loops` a second group, `_uncoupled(spec, boxes, out, edges)`: the top-level
  systems (closed boxes or open frames) that no wire joins to anything outside them, at the whole top level only (no
  `system=` focus, no item filter). They are a group only when there are two or more. `_top_row` draws a closed one
  as `ref:top:S` (r_S, every goal inside S, a vector with its count) into `sys:S|in|r`, and `sys:S|out|y` into
  `out:top:S` (y_S, the distinct parts those goals hold). An open one's row is its frame `frame:S`. The answer gains
  `rows` (each `{system, nodes, frame?}`, top to bottom) and `caption` ("no signals between these systems", or null).
  The two row ports carry `"row": true`: they are not border wires, so the class's p × m and `ports` are unchanged.
- blocks.js `bdStackRows`: after ELK and the wrap, each row's parts (and, for an open one, its frame and everything in
  it) are moved below the coupled group, left edges aligned at one x, top to bottom in `g.rows` order. Each row has a
  dashed outline (`rect.bd-row`) as wide as the widest. The caption (`text.bd-row-caption`, 12 px, `--canvas`) is
  under the last row. A line within a row moves with it. A line between a row and the rest has none, and its ELK
  points are dropped until libavoid routes it.
- docs/SPEC.md (Drawn as parts) says the rows.

Choices made alone, the most reversible:
- Only two or more uncoupled systems form the group. On software-factory (:8796), factory and product are one loop
  and `modelling` is the only system left alone. It stays as it was drawn, under its upkeep rule, with no row and no
  caption (done item 3). The proposal's §3 table would make it a second row with the caption. To get that, change
  `> 1` in `_uncoupled`; the test parameter for software-factory pins today's choice.
- Order: the model's order (`spec.systems`) with the model's upkeep (the modelling template's system) last. In big,
  `spec.systems` puts `modelling` first. The proposal settles that model order puts `modelling` last in all four
  examples, and the upkeep is read last everywhere else in Blocks. The Dynamics view has no stated order of its
  boxes (ELK places them), so done item 4's "as in Dynamics" is read as this model order. No test compares it with
  the Dynamics drawing.
- the-job: `job` is opened by default (default_open: the only own system at the top), so its row is its frame, with
  its loops' references inside it and no r/y of its own. `modelling` is the second row with r and y.
- An r over more than four goals gives its count ("21 goals") instead of listing them beneath it. the-job with `job`
  closed listed 21 names and drew 2604 px wide, which failed the Blocks aspect rule. Its panel lists every goal.
- The box's p × m (for example `0×1` on big's boxes) is still counted from border wires only. Showing the row's r and
  y in it is blocks-closed-block-r-y-and-status (proposal §5), not this gap.
- Text: the caption is 12 px in drawing units. At the fit zoom of a tall drawing (the-job's open frame), it is drawn
  smaller on screen, as every canvas text is. The test checks the computed size (≥ 11).

Tests (each seen failing with the change undone, lesson 9):
- Unit, tests/test_blockdiagram.py: `test_an_uncoupled_spec_yields_parallel_rows_each_with_its_r_in_and_y_out` (a
  two-system fixture: rows in model order, r → block → y and nothing else, r a vector of 2 with its goal keys, y the
  held parts, and one system opened is a frame row). `test_the_examples_uncoupled_top_systems_are_rows_in_model_order`
  [big: seven rows api … web, modelling; the-job: frame:job, modelling; software-factory: none, no caption]. With
  `_uncoupled` returning nothing, 3 failed. With a single system counted as a group, software-factory failed.
- Browser, tests/test_diagram_rendering.py:
  `test_uncoupled_systems_are_parallel_rows_each_with_r_left_and_y_right_and_a_caption` [big, the-job,
  software-factory]. It checks the row order, outlines with equal left edges and no vertical overlap, each row's
  parts inside its outline, r's right edge left of the box and y right of it, one caption below the last row at
  ≥ 11 px, and none on software-factory. With `bdStackRows` returning nothing, big and the-job failed.
- Changed to allow the new nodes and ports: `test_closed_systems_are_subsystem_blocks_and_vectors_join_them`
  (image-squeeze's `modelling` and `regressions` are rows beside the service loop) and
  `test_every_system_has_the_same_letter_and_p_by_m_closed_and_open` (a row's r/y ports are not border wires).

Done items 1-3 name live servers (:8797, :8792, :8796) that this container cannot reach. They are checked on the
demos read as them by the textbook-levels proposal: big, the-job, software-factory. Screenshots:
shots/uncoupled-rows-big-blocks.png, uncoupled-rows-big-blocks-dark.png, uncoupled-rows-the-job-blocks.png.

Run here: ruff clean; tests/test_blockdiagram.py and tests/test_correspond.py 140 passed; the new browser test and
the G6 top-loop test passed; `test_the_control_view_draws_every_example_cleanly_as_a_block_diagram` passed on 22 of
23 examples. It failed on autoscaler, which timed out in `wait_for_function(READY)` before any rule was read. That is the same
failure blocks-top-level-reference-and-sum's record notes. Autoscaler declares no systems, so no rows are made
there. `test_every_view_draws_cleanly_and_in_time` passed on big and image-squeeze. It failed on the-job with
`valve-orientation-mismatch: 3 instances, the ceiling is 2`, a Dynamics rule that this branch does not touch; the
same record names that failure on the-job. Neither was rerun on clean main here. Not run: the whole unit suite and
the four browser files. Main was merged in (already up to date).

## Entry

**Blocks: uncoupled systems are parallel rows.** Two or more top-level systems that no signal joins are drawn as
parallel rows below the coupled loop, in the model's order with the upkeep last. Each row is in a dashed outline,
with the left edges aligned. A closed one has its r (its goals' references, a vector with its count) on the left
and its y on the right. An open one is its frame. One caption under the rows says "no signals between these
systems". A single uncoupled system is drawn as before.
