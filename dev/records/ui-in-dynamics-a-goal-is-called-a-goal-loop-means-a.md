# ui-in-dynamics-a-goal-is-called-a-goal-loop-means-a: In Dynamics a goal is called a goal; 'loop' means an R or B loop

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q62 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list and Suggestions in Dynamics

**The problem:** The Dynamics side list says 'loop requests-handled' directly above 'Feedback loops 18: R2, R3 …'. One word names a controlled goal and a causal loop in one panel; counts (49 against 16) look like double counting. Suggestions speak of 'its decision (fixer, every 1m)' in the SD view.

**The change:** In Dynamics write 'goal requests-handled' and 'what serves it'. Keep 'Feedback loops' for R and B. In Blocks write 'control loop'. Where an R or B loop closes a goal, its row says 'serves goal model-fits'.

**User stories it serves:** G1

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796/ in Dynamics no side-list entry or suggestion starts with 'loop '; the heading 'Feedback loops' remains; in Blocks the list heading reads 'Control loops'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1 (8 net lines outside tests: 14 added, 6 removed).

- Dynamics' cards: `ergostat/dynamics.py` `attention()` (the Dynamics view's words, which the page shows as given) now
  writes `goal NAME` for a controlled goal's card where it wrote `loop NAME`, also inside the text ("goal a keeps
  feeding x while goal b is off"), and `what serves it` where it wrote `its decision`. Only names of the model's
  goals are rewritten, whole, so "feedback loop q-x" is left alone. This file is outside "Files to touch"
  (`ergostat/web/`): it is where the Dynamics words are made, and the page has no other place to change them.
- Suggestions' "Evidence" link (`diagram.js`) reads `goal NAME` as well as `loop NAME`.
- Dynamics' Feedback loops list (`dynamics.js`): a loop whose parts include a goal's gap says
  `serves goal NAME` (`serves goals a, b` for several). The heading "Feedback loops" is unchanged.
- Blocks (and the control view): the list heading is "Control loops", its empty text "No control loops in view.".
  Choice, the most reversible one: in Blocks the cards keep `loop NAME` (no R or B loop is drawn there, and the same
  `what` is the CLI's, the Loops page's and other tests'); only the heading says "control loop".
- Tests: `tests/test_diagram_rendering.py::test_in_dynamics_a_goal_is_called_a_goal_and_loop_means_an_r_or_b_loop`
  (software-factory, one reading of backlog above its goal so `backlog-clear` is off: no card in Dynamics starts with
  `loop `, one starts with `goal `, "Feedback loops" stays, every loop through a goal says `serves goal`; in Blocks
  the heading is "Control loops"). Seen to fail with each change undone in turn (card `loop backlog-clear`; no
  `serves goal`; heading "Loops"). Not seeded in the browser: a suggestion (the ladder hints need 10 minutes of an
  off record); its words are pinned by the unit tests `test_the_attention_cards_speak_system_dynamics` (changed: it
  forbade the word goal, which this gap asks for) and `test_a_goal_s_suggestion_says_what_serves_it` in
  `tests/test_dynamics_view.py`.
