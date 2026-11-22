# ui-an-agent-that-never-ran-is-behind-schedule-or-la: An agent that never ran, is behind schedule or last failed stands out

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q41 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /agents

**The problem:** improver: '0 runs, never ran, every 3m' in the same grey as everything else, with no reason. judge: 'not run here' with a blank runs cell beside 'every 30s', while its panel says 10 runs (about 120 expected).

**The change:** Mark such rows with a word in the alarm colour ('never ran', 'behind: 10 of ~120', 'last run failed') and a one-line reason under the row. The top line counts them ('2 behind schedule'). The list and the panel take their run count from one source.

**User stories it serves:** D4

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8797/agents the improver and judge rows each contain an element with the exception class and one of the three phrases; the page's top line contains 'behind schedule' or 'never ran' with a count; judge's runs cell equals its panel's count.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
