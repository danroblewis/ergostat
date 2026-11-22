# ui-an-agent-s-recent-runs-name-the-item-the-outcome: An agent's recent runs name the item, the outcome and what it asked to do outside

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q39 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** agent panel 'Recent runs'; /items Actions table; item 'Gated actions'

**The problem:** Recent runs has no item, outcome or outward action and no links; its table is clipped at 1440 px. The Actions 'by' column is '–' for all 121 actions though each action page names its asker and approver.

**The change:** Columns: when, item (link), outcome (done or refused, with why), outward actions asked (links), cost. Move CPU and memory behind a 'resources' disclosure so the table fits. Fill 'by' with the block that asked and 'approved by' with who answered ('owner (offline stand-in)').

**User stories it serves:** D2, E3

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791 the panel for 'work' lists at least three runs each with a link to /item/ and an outcome word, and the table's right edge is inside the panel; on /items?kind=ergostat.action no 'by' cell is '–'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
