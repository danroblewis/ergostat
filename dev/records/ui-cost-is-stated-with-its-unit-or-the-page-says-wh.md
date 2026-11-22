# ui-cost-is-stated-with-its-unit-or-the-page-says-wh: Cost is stated, with its unit, or the page says why it is zero

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q40 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /agents; agent panel; item header

**The problem:** Cost and tokens are '–' or '$0' for every agent with no reason; items show 'AI cost $0.0000'; there is no total; the words 'free stand-in' appear only on Check.

**The change:** A cost cell for an agent on a stand-in reads 'free stand-in, $0'. Add a total row for the window. The item header shows 'cost $0 (stand-in)' as the sum of its sessions. Hide a column that is empty for every row.

**User stories it serves:** D3

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8793/agents no cost cell is a bare '–' or '$0'; the table's last row starts with 'total'; /item/hypothesis%2F1 has 'cost' in its header line.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
