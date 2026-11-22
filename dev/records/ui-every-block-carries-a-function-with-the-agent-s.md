# ui-every-block-carries-a-function-with-the-agent-s: Every block carries a function, with the agent's name as its caption

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q65 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram Blocks

**The problem:** open-pr, work, fixer, judge, improver and the drains are drawn as name-only boxes; the law, or that none is stated, appears only on click. Decision 2 asks for a function in every block.

**The change:** Main label is the function: the known law ('u = max(0, y − r/2)'), 'f(·), law not stated' for an unknown one, 'H = 1, every 3 s' for a counting sensor. The agent's name and kind go in small text above the block, where the kind badge is.

**User stories it serves:** G5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791 ?view=blocks&system=making every block's main label contains '=', '(s)', '(z)' or 'f(·)'; the texts 'open-pr' and 'work' appear only as captions outside or at the top of the box.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1. Net +9 lines outside tests/docs (blocks.js +8, blockdiagram.py +1).

- A named block (ai, program, person, external, and the rule-run kinds) now has its function as its main label. That is
  the identified law (`u = …`) when there is one, the standard nonlinearity it is (`u = relay(e)`, `u = sat(x)`,
  `u = dz(e)`, `u = ZOH(x)`, `u = table(x)`, …), or else `f(·), law not stated`. Its name and tier (its kind when it
  has no tier) are its caption, `open-pr · program`, in the top band where the tier badge was (`text.bd-tier`, so
  the existing badge test still holds).
- A sensor with H = 1 says `H = 1, every 3 s`, using the sensor's own period (`fn.every` from blockdiagram.py). Choice
  made: the period with the collector's added (13 s in the ticket factory) stays in the panel. The reads line beneath
  still says `every 3 s` as well, because removing the repeat would change what
  test_sensors_are_blocks_with_what_they_read_and_no_part_has_a_tooltip pins. These are the most reversible options.
- Collectors (drawn as sensors, an instrument rather than a law) are unchanged. None is drawn in making.
- Acceptance: tests/test_diagram_rendering.py::test_every_block_carries_a_function_with_the_agents_name_as_its_caption
  passes. It failed against two breaks: the name drawn as the main label again, and the caption reduced to the tier.
- The full test_diagram_rendering.py had 197 passed and 4 failed. All four failures are outside this change, which
  touches only `?view=blocks`:
  - test_every_view_draws_cleanly_and_in_time[coordinator] and [image-squeeze] (routing open=* 37 s / 34 s > 20 s),
    and test_a_big_tangled_model_lays_out_in_time_and_cleanly (3351 ms > 2500 ms). All three draw only the default
    view, not Blocks. They failed again when rerun alone. They were not run on main: `git worktree add` of main was
    refused in this session.
  - test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page ('Nothing waiting.'): earlier
    reviews already reported this failure on other branches.
