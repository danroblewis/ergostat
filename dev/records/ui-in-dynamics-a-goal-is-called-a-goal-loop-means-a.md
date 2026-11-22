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
