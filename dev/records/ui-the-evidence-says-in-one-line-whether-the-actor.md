# ui-the-evidence-says-in-one-line-whether-the-actor: The evidence says in one line whether the actor was commanded, ran and moved anything

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q28 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** goal evidence panel; /agents rows of rules

**The problem:** requests-handled: 'u: never opened. Its valve did not open' beside 'Moves requests-answered 1.62/h' and a suggestion to do 'more per run'; Agents shows fixer with 34 runs; the Record shows it commanded every minute; its log says 'no open request the rule tier answers'. keep-requests-handled reads 'no roles, not run here'. A sensor reads 'unfilled' beside 'read 2s ago: 36'.

**The change:** Build the actor lines from the same counts Agents and the Record use: 'fixer: commanded 34 times, ran 34, moved nothing (its log: no open request the rule tier answers)'. Show 'Moves' only for what this goal's own valve moved. When it moved nothing the suggestion says 'acts but moves nothing', not 'more per run'. Give each keep-* rule its controller role on Agents. Drop 'unfilled' when a reading exists.

**User stories it serves:** C3, C2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791 the evidence for requests-handled contains 'commanded' and 'ran' with numbers equal to the fixer's run count on /agents for the same window; it does not contain both 'never opened' and 'Moves requests-answered'; the Agents row keep-requests-handled contains 'controller'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
