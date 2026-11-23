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

## Where it stopped

Built, round 1. 84 net lines outside tests and docs (blockdiagram.py 81, correspond.py 2, blocks.js 1), within the
160 budget.

- `fold()` calls `_top_loops(d, cls, boxes, edges, out, groups)` over `_coupled(boxes, edges)`, the (C box, P box)
  pairs joined by a u wire. `_top_loop` draws one pair: `ref:top:P` (r_P, bold with the goals beneath it when there
  are several), `sum:top:P` (+ r on the west, − y_m on the south), e into C, the existing u wire, y out to `out:top:P`
  and to `h:top:P` (a sensor block, so it lies on the return), y_m into the junction, and `dist:top:P` (d_P) into P's
  north side when P has disturbance ports. The P→C y wire is replaced by the return. A C box's input port becomes e,
  carrying the measured keys C reads. A bundled vector leaving a C is now named u_C, not y_C. A collector's record
  crossing between systems, which had no symbol, is labelled y_collector (ticket-factory's only unlabelled wire).
- correspond.py: each `*:top:*` node is a region standing for the parts of the signals it carries. Without this it
  read `sum:top:product` as a goal named `top:product`. tests/test_correspond.py gains the rule for these shapes.
- blocks.js: a vector input's width makes room for its goals written beneath it. A comparator over several loops does
  not write the first loop's error state after its e.
- SPEC §4a says the loop.

Choices made alone, the most reversible:
- r is every goal inside P whose loop has a controller or actuator inside C and none inside P. This approximates the
  proposal's "C's u reaches it", read from `spec.loop`, not from a causal walk.
- The loop is drawn only when both systems are closed boxes at the same level. Opening either one gives the existing
  wires, so the frame's ports carry the same keys as the top-level wires (done item 3, pinned by key sets).
- e and y_m are drawn bare, without the `_product` subscript, as the textbooks write them beside their Σ. With the
  subscript they found no free spot beside the vector slashes and went undrawn. r, y and d keep the system's name.
- H's head is `H_P = <entry>` when every sensor has the same function, otherwise `H_P = diag(H_1 … H_m)`. Its panel
  math gives the full diag.
- When C serves no goal of P (proposal §2's empty r), nothing new is drawn and the wires stay as they were. P's
  "r: none, held inside P" port text is not built: no done item asks for it.

Tests: tests/test_blockdiagram.py `test_a_two_system_spec_draws_junction_r_e_u_y_and_h_on_the_return_at_the_top_level`,
`test_every_wire_at_the_top_level_has_a_label_and_software_factory_closes_its_loop` (every wire touching a system
box or the loop, every system closed, every example with systems),
`test_the_top_loop_stands_for_its_goals_and_signals_in_the_correspondence`,
`test_opening_either_subsystem_shows_the_same_signals_at_its_frame_ports[two|software-factory]`. Browser:
tests/test_diagram_rendering.py `test_the_top_of_blocks_is_a_loop_with_its_junction_ahead_of_the_controller_and_h_beneath`
(Σ left of C, H's centre below C's and P's, both signs, every wire's label drawn or said by its input/output node,
the port marks of each opened frame). Each was seen failing with `_top_loops` given no groups. The label test failed
on ticket-factory before the record label. `test_closed_systems_are_subsystem_blocks_and_vectors_join_them` now
pins the subsystem boxes and allows the loop's nodes beside them.

Done item 4: `test_the_control_view_draws_every_example_cleanly_as_a_block_diagram` (the Blocks layout rules, every
view of every example, 23 examples) passed on all 23. In the same run, every failure was in the Dynamics view, which this branch does
not touch. `test_sensors_are_blocks_with_what_they_read_and_no_part_has_a_tooltip` failed on 22 examples, all at
`view=dynamics&open=*` on a `<title>` "Drawn alike here with …" that `ergostat/web/static/dynamics.js:580` writes.
`test_every_view_draws_cleanly_and_in_time` failed on autoscaler and ticket-factory (satellite-far over its ceiling)
and the-job (valve-orientation-mismatch over its ceiling). These are Dynamics rules. Not rerun on clean main here:
`git checkout main` was refused in this session.
Not run here: the whole unit suite and the four browser files (the factory and the merge queue run them).
In the opened product frame one of the four port marks has no room for its name. That view is unchanged by this
branch, and the browser test checks only that each named mark is a u or y.

Round 2. Main (278f54a4) is merged in. The conflict in tests/test_blockdiagram.py kept both sides: main's
`test_a_systems_letter_carries_its_name_once_closed_and_open` and this branch's top-loop tests.

The blocking finding is fixed. Each loop is now keyed by its (C, P) pair, not by P alone. Its r, Σ, H and y nodes are
`{ref|sum|h|out}:top:C>P`. Its signals are `top:{r|e|y|ym}:C>P`. C's error port is `{c}|in|e<P`. So two Cs on one P
draw two loops, each with its own goals, and one C on two Ps gets two e ports. P's disturbance stays per system
(`dist:top:P`, port `{p}|in|d`) and is drawn once, however many Cs act on P. Two Cs on one P each draw their own y
out of P. I kept this over merging every C on a P into one group: it is the smaller change and the easier one to
undo. New test: `test_two_cs_on_one_p_and_one_c_on_two_ps_draw_one_loop_per_pair` (a, a2 → b; a → c). It checks
that node ids and port ids are unique, that no wire appears twice, one junction per pair with one + and one − input,
each junction's goals, two e wires into a, and one d into b. Seen failing on each defect the review named, one at a
time: ids keyed by P (19 wires, 17 distinct), C's port `{c}|in|e` (sys:a has it twice), and d not held to one (sys:b
has `|in|d` twice). The image-squeeze, correspondence and G6 browser tests now use the pair ids.

Run in round 2: ruff clean; tests/test_blockdiagram.py 124 passed; tests/test_correspond.py 12 passed; the G6 browser
test passed. `test_the_control_view_draws_every_example_cleanly_as_a_block_diagram` passed on 22 of 23. It failed 3
times out of 3 on autoscaler, timing out in `Page.wait_for_function(READY)` (240 s) before any layout rule was read.
Autoscaler declares no systems, so `_top_loops` draws nothing there. In round 1 it passed on this branch's blocks.js,
so the new input is main's merge. Not checked on clean main: `git worktree add --detach /tmp/mainwt main` was refused
in this session. Left for the factory's rerun on main (lesson 13).
