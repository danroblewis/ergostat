# ui-agents-each-row-says-how-it-is-engaged-and-which: Agents: each row says how it is engaged and which goal it serves

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q38 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /agents; agent panel

**The problem:** A blank 'runs when' cell means on demand; the panel says 'Runs: not run by ergostat' beside '28 runs, 0 failed'; roles name valves, never goals ('valve work'); '0 failed' hides that most runs were refused.

**The change:** 'runs when' reads 'on demand, per item (leased)' when blank. The panel line becomes 'started per item by its lease, not on a schedule'. Roles read 'valve work → goal located-worked'. The run tally reads '28 runs: 9 done, 19 refused (workspace pool full), 0 failed'.

**User stories it serves:** D1, D2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791/agents no 'runs when' cell is empty; the 'work' row contains 'on demand' and a goal name; its panel does not contain 'not run by ergostat'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
