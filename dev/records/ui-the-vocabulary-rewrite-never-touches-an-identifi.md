# ui-the-vocabulary-rewrite-never-touches-an-identifi: The vocabulary rewrite never touches an identifier

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q46 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list (Dynamics wording)

**The problem:** The Dynamics wording is a find-and-replace: 'queue-goal-tolerance on goal.ci-upgrade-planned' becomes 'queue-desired level-tolerance on desired level.ci-upgrade-planned', and 'a desired level's desired level and tolerance'. The same request reads 'decision tier' in one view and 'rule tier' in the other.

**The change:** Translate only the sentence's own words, never codes, ids or part names (render them as separate tokens). The tier named comes from the request, not the view.

**User stories it serves:** E2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8792/ in Dynamics the text of request/80fe1e93e1 contains 'queue-goal-tolerance' and 'goal.ci-upgrade-planned' or its plain name, and does not contain 'desired level.' or 'desired level-'; its text in Blocks names the same tier.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
