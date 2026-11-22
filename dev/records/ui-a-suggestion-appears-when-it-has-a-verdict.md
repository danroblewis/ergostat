# ui-a-suggestion-appears-when-it-has-a-verdict: A suggestion appears when it has a verdict

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q80 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list Suggestions

**The problem:** 'loop requests-handled was off 92% of the time; why (a flow too small to close the gap, or acting too seldom) is said after 10m of record (1m51s so far)': it names the goal twice, offers two causes and defers. The Agents page calls the same cause 'a valve too small'.

**The change:** Hide a suggestion until its verdict exists; until then its goal's entry carries 'diagnosis in 8m'. Name the goal once. One phrase for the cause on every page.

**User stories it serves:** C2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
No suggestion contains 'is said after'; no suggestion contains its goal's name more than once; the cause phrase for one goal is identical on /diagram and /agents.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
