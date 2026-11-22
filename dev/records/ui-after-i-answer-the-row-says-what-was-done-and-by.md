# ui-after-i-answer-the-row-says-what-was-done-and-by: After I answer, the row says what was done and by whom, and the item shows it

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q49 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list; /item/… 'Gated actions'

**The problem:** Nothing confirms an answer; the item's Gated actions lines say 'ran 31m ago, gate approve' without by whom.

**The change:** The answered row is replaced in place by 'Denied by you at 04:02, reason: … · see ticket/SCRUM-2' and stays until the next visit. The item's Gated actions line reads 'jira-transition: approved by owner (offline stand-in) 03:24, ran 03:24' or 'denied by … : reason'.

**User stories it serves:** E3

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
After pressing Deny on a test request the row contains 'Denied by' and a link to the item; that item's page contains the same request with 'denied by'. Every Gated actions line contains 'approved by' or 'denied by'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
