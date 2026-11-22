# ui-per-class-of-action-asked-approved-denied-and-wh: Per class of action: asked, approved, denied, and whether it is held

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q51 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /items › oversight › Actions

**The problem:** No page states per-class totals. The tallies '0 requested, 0 approved, 121 ran, 0 denied' count present state, so '0 approved' misleads; '11 asked, 0 approved' for the person ask contradicts 121 actions approved by the stand-in. The Items search does not match the action field.

**The change:** Above the Actions rows, one line per class: 'jira-transition: 24 asked, 24 approved (by the offline stand-in), 0 denied this week · held for approval'. The search matches class and command.

**User stories it serves:** E5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791/items the Actions section has a row starting 'jira-transition' with three numbers and either 'held for approval' or 'let through'; asked = approved + denied + waiting; typing 'jira-transition' in the search narrows the action rows.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
