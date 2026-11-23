# blocks-subsystems-classified-c-p: Blocks: subsystems are classified C, P or a named block, with the same letter and dimensions at both levels

depends-on: [blocks-textbook-levels-proposal]

Problem (R4 piece 3): every closed subsystem is 'Q_name p x m'; Q is undefined in the legend and becomes P with different dimensions when opened, because the disturbance is counted at one level and not the other (shots/story-7-h1-blocks.png, story-7-h2-into-api-blocks.png, ce-sf-blocks-factory.png).
Change, as the proposal settles: ergostat/blockdiagram.py classifies each subsystem node from what it holds (controllers acting on another system's process: C; processes acted on from outside: P; both or neither: its own name as a named block) and counts inputs and outputs, disturbances included, the same way at the level above and inside; the node carries {letter, p, m} and its ports in a stated order (references, outputs, disturbances) that later gaps print on. blocks.js draws the letter with the system's name as subscript and p x m; the legend (filed Q68) defines the letter and p x m. Q is removed everywhere.
Definition of done:
1. On :8796, :8797 and :8791 no block is labelled Q.
2. For every subsystem the letter and p x m printed on the closed block equal those in the frame title when opened (a test walks every system of every demo).
3. The legend defines C, P and p x m.
4. Render tests pass.
Files: ergostat/blockdiagram.py, ergostat/web/static/blocks.js, tests (a blockdiagram unit test of classification on a small spec; tests/test_diagram_rendering.py).
Acceptance tests: unit: a system holding only controllers is C, only processes P, mixed named; the both-levels walk on the six demos.
Budget: 110 net lines.

Milestone: r4-blocks-textbook. Owner items: R4 piece 3. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 14:22).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 669, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 14:22).

Its runs failed past their attempts (a dead letter):
- attempt 1: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 2: nack given back
- attempt 3: nack exited 1
- attempt 4: nack the run ended with gap/blocks-subsystems-classified-c-p still parked

## Where it stopped

Built (round 1, continued, 2026-11-23). `_classes()` in ergostat/blockdiagram.py classifies each system once, from the
flat diagram's wires that cross its border, by the proposal's rule (docs/proposals/blocks-levels.md §1, with rule (b)):
C, P or named. It counts p outputs by m inputs, and m includes the disturbances that arise inside the system as well as
those that enter it. `fold()` gives the closed box and the open frame the same `fn` (`sym`, `sub`, `letter`, `p`, `m`,
`expr` "p×m", `named`) and the same `ports`. blocks.js draws a named block's name upright, adds p×m to the frame title
(a named frame's name is drawn once), and its legend has a row that defines C_name, P_name, the named block and p × m.
The legend no longer mentions Q. Q is gone from the code, the math text and the docstrings.

Choices made alone, each the easiest to reverse:
- The ports' stated order is inputs, outputs, disturbances (`as`: "in", "out", "d"). "References" in the definition
  is read as every input that crosses the border: references, u wires and y wires from other systems. A disturbance
  entering from outside is put in "d", not "in".
- A named block's `fn.sym` is its own name with no subscript (`named: true`), so every block still has a function
  (the existing test), and it is drawn upright.
- p×m is always written, also 0×2 or 1×0. Before, it was hidden when a side was empty.
- A system with no part in the control system (autoscaler's `rescales`) has no box, so the walk skips it.
- Classes found (from a probe run, not pinned except where the proposal pins them): software-factory factory C 1×3,
  product P 3×2 (one d), intake P, delivery C. Every top-level system of big, the-job and ticket-factory is named.
  image-squeeze: service P, rollout C, lab P, benchmark P. coordinator: owner P, the rest named.

Not done or not checked:
- Done item 1 names the live demos on :8796, :8797 and :8791. They cannot be reached from this container. The unit
  walk checks every example's closed boxes and frames for a Q symbol, and the new page test checks software-factory's
  drawn page for one.
- The rows, references, Σ and H of the top level are left to the later gaps (blocks-top-level-loop and after), as the
  definition asks.

Tests, each seen failing when the code it guards was broken (lesson 9):
- tests/test_blockdiagram.py::test_a_system_of_controllers_is_c_of_processes_p_and_mixed_or_neither_is_named
  fails when rule (b) always reaches a goal.
- tests/test_blockdiagram.py::test_every_system_has_the_same_letter_and_p_by_m_closed_and_open (every example)
  fails on 14 examples when internal disturbances are dropped from m. It counts p and m again from the opened drawing.
- tests/test_diagram_rendering.py::test_a_system_is_drawn_c_p_or_named_with_the_same_p_by_m_closed_and_open
  fails when the frame title loses p×m.

Runs: tests/test_blockdiagram.py passes (92). tests/test_correspond.py, test_guide.py and test_remote_pair.py pass (21).
Ruff is clean. The whole of tests/test_diagram_rendering.py was run serially under the watchdog in this container:
277 passed and 35 failed. Three of the failures were this branch's: test_each_blocks_legend_row_is_a_symbol_drawn,
because the new legend row had no selector in BD_LEGEND_DRAWN. The selector is added, and those three pass now. I
could not run the other 32 on main here, because `git worktree add` for main was refused. Why I take them as
unrelated (lesson 13):
- test_sensors_are_blocks_with_what_they_read_and_no_part_has_a_tooltip, 22 examples: a tooltip on a Dynamics loop
  title ("Drawn alike here with B.. changes-testing via fixer"). That is Dynamics, which this branch does not touch.
- test_every_view_draws_cleanly_and_in_time for autoscaler (satellite-far 6 > 0), the-job (valve-orientation-mismatch
  3 > 2) and ticket-factory (satellite-far 15 > 14): Dynamics views only (no view=blocks).
- test_the_control_view_draws_every_example_cleanly_as_a_block_diagram[autoscaler]: `view=blocks&system=rescales`
  draws 0 nodes, and READY waits for one. A probe found that this is the only view that hangs. This branch does not
  change which nodes fold() draws, so main draws 0 there too.
- test_the_exported_png_shows_every_loop_name_the_values_and_its_legend_on_white_in_dark_mode: 6 legend rows
  against more than 10 wanted, in `system=product`. That view has no subsystem or system frame, so the new row is not
  shown there and no row was removed.
- test_parts_chosen_with_a_box_move_together_pinned_and_with_no_new_layout (Dynamics stock:users),
  test_everything_clickable_in_the_diagram_is_reached_and_acted_on_by_keyboard (focus after opening a Dynamics
  stock), test_blocks_crossings_hop_dots_only_at_takeoffs_slashes_clear_and_a_drag_and_the_export_keep_them
  (get_by_role("button", name="fit") also matches modelling's keep-model-fits blocks, whose labels this branch does
  not change), test_a_panel_open_on_what_is_chosen_stays_open_across_a_switch_of_view_in_its_words (a routed
  /api/part/flow response never comes), test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page
  (the Model page) and test_needs_attention_is_three_headed_groups_in_a_fixed_order (a timeout).
The other three browser files were not run (the factory runs them).
Merge: main (f086f76e) was already merged into the branch (2d58c420) before this work, and main has not moved since.
