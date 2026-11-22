# ui-modelling-is-drawn-last-set-apart-and-labelled: modelling is drawn last, set apart and labelled

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q13 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram top level (Dynamics and Blocks)

**The problem:** In every demo ergostat's model of its own upkeep is the top-left box, read first, unexplained and unconnected. A newcomer concludes the product is about itself.

**The change:** Lay modelling out last (bottom right), with a dashed outline and the line 'ergostat's upkeep of this model, not the system'. Same place in Blocks, below a thin rule.

**User stories it serves:** A2, B6

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796/ and :8797/ in both views the modelling box's top-left corner is below or right of every other system box, its outline has a stroke-dasharray, and it contains the words 'upkeep of this model'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped (round 1)

Built, 36 net lines outside tests (53 added, 17 removed).

- Which box: the system made by the `modelling` template (`spec.uses[name].template`), flagged `upkeep` on its box by
  `ergostat/fold.py` (Dynamics) and `ergostat/blockdiagram.py` (Blocks). These two files are outside "Files to touch"
  (one helper and one field). I chose this over matching the name "modelling" on the page, because a name match would
  miss an instance named otherwise and would mark an owner's own system that happens to be called that. Taking it out
  is one line in each file.
- Dynamics: at the top level (nothing open), the box is left out of ELK's layout when it is linked to nothing. Then
  `packLoose(lay, nodes, last)` (places.js) puts it at the best-fitting free spot whose top-left corner is below or
  right of every other part (not just every other system box), as near the bottom right as that fit allows. The
  outline is dashed ("6 4") and it says "ergostat's upkeep of this model, not the system" under the loops line.
- Blocks: at the top level, the block is left out of ELK's layout when it is linked to nothing. It is then put below
  every other part, right-aligned, under a thin rule (`path.bd-upkeep-rule`), with the same dashed outline and line.
- Decisions taken without the owner (the most reversible option each time): a modelling box that is linked to
  something, or that sits beside an open system, keeps its old place. A lone modelling system that opens by default
  (`default_open`) is drawn open and is not changed. The gap is the top level only. My first version also moved the
  box beside an open system; that grew big's open=build/open=data and ops' open=backups past their recorded sizes, so
  it was narrowed to the top level.
- Acceptance test: `tests/test_diagram_rendering.py::test_modelling_is_drawn_last_set_apart_and_labelled[alert-triage|big]`.
  It runs on examples, since :8796/:8797 (the owner's demos) are not reachable from here. It checks in both views:
  the corner below or right of every other part, a stroke-dasharray, the words, that the line fits inside the box,
  and in Blocks the rule between the rest and the box. Seen to fail under four breaks: Dynamics placement not last,
  Blocks placement left to ELK, Dynamics outline undashed, Blocks line empty.
- No screenshots: the page was only checked by the test's geometry. Writing a scratch script to /tmp was refused
  (the file tools are confined to /work).
- tests/test_diagram_rendering.py, the whole file, serially under the watchdog: 194 passed, 8 failed (43 min). Every
  failure was rerun alone after the fix:
  - test_every_view_draws_cleanly_and_in_time[big] and [ops], and the module-caption test: mine. Fixed (top level
    only; the label drawn after the loops caption), and they pass.
  - [ticket-factory] passes. [image-squeeze] (routing open=* 20.9 s against 20 s) and the stress test (open=* drawn in
    2637 ms against 2500 ms) pass when run alone. Both are timing under load, in views this change leaves alone.
  - [coordinator] was rerun with the 3-test batch whose output showed only the stress test's and the equation test's
    errors (2 failed, 1 passed), so it passed.
  - test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page fails every time on the Model page's
    "Nothing waiting." after an Accept. That page is untouched here, and an earlier review (parts-belong-to-their-system)
    names the same test failing. Not confirmed on main: the run in a main worktree (`git worktree add ... main`) was
    refused. Left to the factory's rerun on clean main (lesson 13).
- Also run: tests/test_blockdiagram.py (67 passed); ruff clean. Not run: the unit suite, the other three browser files,
  demo_check (no example touched). main has not moved since the clone, so there was nothing to merge.

## Where it stopped (round 2)

The one finding (conflict with main in `ergostat/web/static/dynamics.js`) is resolved in the merge of main 720426bd.
Main replaced the closed box's "N feedback loops inside" line with its description, wrapped to at most two lines
(`sys-desc`). Both are kept: main's description lines, then the upkeep line under them at `y = 44 + 14 × lines`
(58 for one line, 72 for two, both inside the box's 96 px minimum height). Still 36 net lines outside tests
(53 added, 17 removed).

- The acceptance test (`[alert-triage]`, `[big]`) and main's `test_each_closed_system_box_says_what_the_system_is`:
  4 passed after the merge. ruff clean. tests/test_blockdiagram.py: 67 passed.
- tests/test_diagram_rendering.py, the whole file, under the watchdog: 200 passed, 6 failed (48 min). Each was rerun
  alone afterwards:
  - test_a_block_dragged_in_the_blocks_view_stays_pinned_... passes alone.
  - test_the_dynamics_view_speaks_system_dynamics_... fails: it finds the word "Goals" in the side panel's
    "Goals off" heading. That heading comes from main's cd71c13e (needs-attention-is-three-headed-groups), not from
    this branch. Unrelated (lesson 13).
  - test_an_equation_its_numbers_..._accepted_from_the_page fails as in round 1 (the Model page's "Nothing waiting.").
    Unrelated.
  - test_every_view_draws_cleanly_and_in_time[coordinator] and [image-squeeze] (routing open=* 31.6 s / 32.4 s against
    20 s), and test_a_big_tangled_model_lays_out_in_time_and_cleanly (open=* drawn in 2908 ms against 2500 ms) fail
    alone too, all on open=* timing. This branch's code does not run there: the upkeep box is moved only when
    nothing is open (`open.size ? []` in diagram.js, `!(g.open || []).length` in blocks.js). Not confirmed on main:
    `git checkout main -- ergostat/web/static ...` to run them on main's page code was refused. Left to the
    factory's rerun on clean main.
- Not run: the unit suite, the other three browser files, demo_check (no example touched).
