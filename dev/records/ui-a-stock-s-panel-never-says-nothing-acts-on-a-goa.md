# ui-a-stock-s-panel-never-says-nothing-acts-on-a-goa: A stock's panel never says nothing acts on a goal that has an actor

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q24 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** stock panel (Dynamics)

**The problem:** users: 'desired users = 180 (nothing in the model acts on its gap: no feedback closes it)' while Loops lists users-growing, moved by product-manager, and the stock is in 13 loops.

**The change:** The 'Desired level' row names the goal and what serves it ('goal users-growing, served by product-manager in factory'). Say 'nothing acts on its gap' only when the goal has no controller anywhere.

**User stories it serves:** B5, C3

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796 the users stock panel contains 'users-growing' and 'product-manager' and does not contain 'nothing in the model acts'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1. `ergostat/dynamics.py` gives each goal said on its stock or flow `by`: the blocks that serve it
anywhere in the model (`spec.loop(goal).controllers`), each with its top system (`spec.chain(...)[-1]`). `acted` now
means "its gap is drawn here, or something serves it". `ergostat/web/static/dynamics.js` writes the row as
`desired users = 180 (users-growing), served by product-manager in factory`, and says "nothing in the model acts on its
gap" only when `by` is empty and no gap is drawn. Net code: +3 lines.

Choices made alone (each easy to reverse):
- Outside "Files to touch": `ergostat/dynamics.py`, the view's server side. The page's graph never carried a goal's
  controllers (the Dynamics view draws none), so the script alone could not name them.
- The row leaves out the word "goal" that the change's example text uses: the Dynamics view keeps its discipline's words
  (tests/test_diagram_rendering.py `SD_WORDS` keeps "goal", "controller", "setpoint" off its panels, and no other
  Dynamics text says "goal"). The goal is named in brackets after its desired level; the acceptance check is unchanged.
- "in factory" names the block's top system (product-manager is in intake, within factory), as the change's example does.
- tests/test_dynamics_view.py pinned the old claim (no-live-bugs `acted: False`, though support serves it, as its own
  line 39 says); it now pins `by: [support in factory]` and `acted: True`. A new test makes nothing read bugs-live and
  shows that goal is still said unacted, with `by: []`.

Tests: tests/test_dynamics_view.py (11 passed);
tests/test_diagram_rendering.py::test_a_stocks_panel_names_its_goal_and_what_serves_it_and_never_says_nothing_acts_on_it,
::test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known and
::test_every_part_opens_its_panel_when_clicked_even_mid_redraw (3 passed, rc 0 under suite_watch); ruff clean.
Breaks seen to fail (lesson-9): `by` forced empty failed the acceptance browser test and the updated unit test;
`acted` forced true failed the new no-controller test. Not run here: the unit suite and the four browser files in full
(left to the factory and the merge queue). main merged: already up to date.

Round 2: main (720426bd) merged in. The only conflict was in tests/test_diagram_rendering.py: main renamed the next
test to `test_a_module_counts_its_loops_in_the_side_list_not_on_its_box_and_draws_no_port_squares`. Both are kept
(this branch's acceptance test, then main's renamed test). The code diff against main did not change (ergostat/dynamics.py,
ergostat/web/static/dynamics.js).

Tests after the merge: tests/test_dynamics_view.py 13 passed; ruff clean; under suite_watch the acceptance test and
main's renamed module test passed. `test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known`
fails (rc 1). The side list's text matches `SD_WORDS` on "Goals off 0 / No goal is off.", which is the needs-attention
heading main added in cd71c13e (ergostat/web/static/diagram.js:1377). This branch leaves diagram.js and the side list
alone, and the assertion that fails reads only the side list, so I believe it is a failure on main and not
this gap's (lesson 13): reported, not fixed. I could not confirm it on clean main: making a worktree of main under /tmp
to run the test there was refused.
