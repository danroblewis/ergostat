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
