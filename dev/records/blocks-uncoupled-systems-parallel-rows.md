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

Round 2. The one finding (blocking): the row outlines and the caption were worked out in `bdStackRows`, before
`anchorLayout` (a system just opened or closed is kept where it was) and `applyPins` moved the parts, so they were
drawn away from their rows. Fixed: `bdStackRows` now only stacks the rows and keeps which parts are in each
(`lay.rowMembers`) and the caption's text. The new `bdRowOutlines(lay)` works out the outlines and the caption when
they are drawn, from where the rows' parts are then. So they follow the anchor shift, a pin, and a drag that settles
without a new layout. The widths are still equal (the widest), and the caption sits under the lowest outline. The
outlines still share one left edge after an anchor shift, which moves everything by the same amount. A pin that moves
one part moves its row's outline with it. SPEC (Drawn as parts) says so.
- New browser test `test_rows_keep_their_outlines_when_a_coupled_system_opens_or_closes_in_place`, on image-squeeze.
  It opens service, closes it, then opens it again with `modelling`'s block pinned at (1500, 40). Each time it checks
  that an anchor was set, each row's parts are inside its outline, and the caption is below every outline. It also
  checks that the pin took. I broke the fix on purpose (outlines copied before `anchorLayout` and drawn from that
  copy) and the test failed on the first opening: regressions' parts at x 959-1603 against an outline at x 20-690.
- Run here: ruff clean. The new test and the three `test_uncoupled_systems_are_parallel_rows_…` cases passed.
  `test_the_control_view_draws_every_example_cleanly_as_a_block_diagram` passed on 22 of 23 examples. It failed on
  autoscaler, the same READY timeout as round 1, in an example with no systems and so no rows. It was not rerun on
  clean main. The Python is unchanged this round. Not run: the whole unit suite and the four browser files.
Overrun reason: 110 net lines against the 100 budget; the 10 over are bdRowOutlines, the review's fix (outlines worked out at draw time, after the anchor shift and the pins), which the round-1 design had no room for.

Round 3. The one finding: main (d0f95413) conflicted in ergostat/blockdiagram.py, at the return of `fold()`. Main
added `modelling: True` to the `tree` entries of the model's upkeep systems; the branch added `rows` and `caption`.
Both are kept in the merge commit. No other change this round; the size is as in round 2.
- Run here after the merge: ruff clean; tests/test_blockdiagram.py 128 passed; tests/test_correspond.py 12 passed;
  the three `test_uncoupled_systems_are_parallel_rows_…` cases and
  `test_rows_keep_their_outlines_when_a_coupled_system_opens_or_closes_in_place` passed.
  `test_the_control_view_draws_every_example_cleanly_as_a_block_diagram` passed on 22 of 23 examples and failed on
  autoscaler (READY timeout of 240 s, in its loop over the tree's views). This round it was rerun with main's
  blockdiagram.py, blocks.js and style.css put in place: autoscaler fails the same way there, so it is not this
  branch. Not run: the whole unit suite and the four browser files.

Round 4. The findings: the merge of a batch of 16 failed, and alone it failed
`tests/test_known_laws.py::test_a_declared_law_is_drawn_as_its_blocks_function_and_a_block_without_one_as_before`.
Both are one cause. That test pins a hash of the whole Blocks answer for a model with no systems ("a block without a
law as before"), and the branch added `rows: []` and `caption: null` to every answer, so the hash changed. Seen
failing here before the fix. Fixed in the branch, not by changing the golden: the answer gains `rows` and `caption`
only when there is an uncoupled group, so a model without one answers exactly as on main (blocks.js already read a
missing `rows` as none). The unit tests that read `g["rows"]` now read it as absent when there is no group, and the
software-factory case checks that both keys are absent. Two net lines in blockdiagram.py changed in place, so the
size is as in round 2.
- Run here: ruff clean. tests/test_blockdiagram.py, tests/test_known_laws.py and tests/test_correspond.py: 156
  passed. Browser: `test_uncoupled_systems_are_parallel_rows_…[software-factory]` and `[big]`, and
  `test_rows_keep_their_outlines_when_a_coupled_system_opens_or_closes_in_place` passed. Main merged: already up to
  date. Not run: the whole unit suite and the four browser files (the merge queue runs them).

Round 5. The one finding (blocking): `test_modelling_is_drawn_last_set_apart_and_labelled[big]` failed. Big's
`modelling` is one of the rows, with its r and y (done item 1 names all seven systems as rows). So `bdUpkeep`, which
needs a block with nothing wired to it, returned null and no rule was drawn. Its own `out:top:modelling`, right of
the block in the same row, also read as a part "ahead" of it. Design settled, the most reversible option: the upkeep
keeps its row, r and y (done item 1), and it is still set apart. When the last row is the model's upkeep (`tree[S]
.modelling`) and there is a row above it, `bdRowOutlines` gives a rule, as wide as the outlines, halfway in the gap
above that row's outline. It is drawn as `path.bd-upkeep-rule`, like the lone upkeep's. The test was changed on
purpose, and SPEC (Drawn as parts) says so: the parts of the upkeep's own row (its r and y, `S.layout.rowMembers`)
are part of it, not parts ahead of it or below the rule. Every other part must still be above the rule, and the
block must still be last. alert-triage (no rows) reads exactly as before.
- Lesson 9: with the rule drawn only from `lay.rule` (the fix undone), `[big]` failed with "[blocks] no rule above
  the modelling block". With the fix it passes.
- Run here: ruff clean. tests/test_blockdiagram.py, tests/test_known_laws.py and tests/test_correspond.py: 156
  passed. Browser: `test_modelling_is_drawn_last_set_apart_and_labelled` [alert-triage, big], the three
  `test_uncoupled_systems_are_parallel_rows_…` cases and
  `test_rows_keep_their_outlines_when_a_coupled_system_opens_or_closes_in_place`: 6 passed.
  `test_the_control_view_draws_every_example_cleanly_as_a_block_diagram`: 22 passed, autoscaler failed with the
  same READY timeout (240 s) that round 3 reproduced with main's files, so it is not this branch. Main merged:
  already up to date.
- Not run, contrary to the finding's request: the whole unit suite and the four browser files. This session's
  rules forbid running them here ("never the whole unit suite or the four browser files yourself"; the merge queue
  runs them). This is the gap that let the finding through, and it is still open until the queue runs them.
Overrun reason: 114 net lines against the 100 budget; round 2's 10 (bdRowOutlines) and 4 more for the rule above the upkeep's row, the round-5 finding's fix.

## Entry

**Blocks: uncoupled systems are parallel rows.** Two or more top-level systems that no signal joins are drawn as
parallel rows below the coupled loop, in the model's order with the upkeep last. Each row is in a dashed outline,
with the left edges aligned. A closed one has its r (its goals' references, a vector with its count) on the left
and its y on the right. An open one is its frame. One caption under the rows says "no signals between these
systems". The model's upkeep, the last row, is set apart by the thin rule above its row. A single uncoupled system is
drawn as before.
