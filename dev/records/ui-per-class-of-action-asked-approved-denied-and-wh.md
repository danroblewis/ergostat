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

## Where it stopped

Round 1: built. 35 net lines of code outside tests, docs and dev (record.py 21, pages.js 12, actions_api.py 2,
server.py 0), within the 60 budget.

- `ergostat/actions/record.py` `asked()`: per class, the actions asked this week, each counted once by where it ended
  (approved: ran, failed or still to run, and how many by the gate; denied: by the gate, the owner or at the act;
  waiting: held now), so asked = approved + denied + waiting by construction; the class's gate (the model's, else the
  newest asked's). Served at `GET /api/actions?classes=1`.
- `ergostat/web/static/pages.js` `actionClasses()`: above the Actions rows on /items, one line a class, e.g.
  `jira-transition: 5 asked, 3 approved (by the gate), 1 denied, 1 waiting this week · let through`. The search
  narrows the lines with the rows (a line stays if its class matches, or one of its actions is in the rows left).
- SPEC §12k: a paragraph on the line and the endpoint.

Choices made without asking (each easy to change):
- The line shows **waiting** as a fourth number. The acceptance asks for asked = approved + denied + waiting, which
  a reader can only check if waiting is shown.
- The approver is said as the record says it: "(by the gate)", "(by a person)", or "(N by the gate)" when mixed. The
  record has no "offline stand-in" approver for actions (auto approvals are `approved_by: gate`), so it is not said.
- A `deny` gate is said "never run" (neither "held for approval" nor "let through" is true of it).
- The rows' search: `_as_listed` already matched the search against every field (action, class, command). No change
  to it was needed. The new browser test shows it narrowing the action rows by class and by command. I did not find
  why the design review saw it fail on the demo.
- The test gets its own site (`acted` fixture: image-squeeze with two actions appended to its ergostat.yaml). The
  Actions kind exists only when the model declares actions, and image-squeeze declares none.

Tests: `tests/test_items_page.py::test_actions_say_per_class_asked_approved_denied_and_whether_held` (browser) and
`tests/test_gated_actions.py::test_each_class_says_asked_approved_denied_waiting_and_its_gate` (unit). I broke the
code twice and both tests failed as they should: with the lines' search filter removed, the browser test failed
(`['jira-transition', 'outward'] == ['jira-transition']`); with a denial counted as an approval, both failed. Whole
files run: tests/test_items_page.py 22 passed with none skipped (under suite_watch, rc 0), and
tests/test_gated_actions.py 11 passed. Ruff is clean. main has no commits beyond this branch's base, so there was
nothing to merge. Not run here: test_diagram_rendering.py and the other browser files (this change does not touch
the diagrams), and the whole unit suite (the factory's to run).
