# ui-a-goal-s-behaviour-label-does-not-flip-between-r: A goal's behaviour label does not flip between reloads, and flapping has a name

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q18 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /loops, loop detail

**The problem:** Labels flip with no change of state ('within its bound' → 'past its bound 4%' → 'within its bound'); 'past its bound 0%' contradicts itself; a goal that crossed its bound 23 times in 32 minutes reads 'holding … Oscillating: no'; 'time off 0%' sits beside 'past its bound 5%'.

**The change:** Apply hysteresis to the behaviour class (it changes only after the new class has held for a set share of the window). Write '<1%', never '0%', for a non-zero share. When crossings pass a threshold the label is 'flapping (23 crossings in 32m)'. Show one share in the row ('time off'), and define 'past its bound' beside it in the detail.

**User stories it serves:** B2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
Five reloads of :8791/loops in 60 s: any goal whose status did not change keeps the same behaviour text; no cell contains '0%' next to 'past'; on :8797 a goal with 20 or more crossings in the window shows the word 'flapping' and its count.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
