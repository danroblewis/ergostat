# ui-approve-and-deny-say-what-they-answer-in-an-orde: Approve and Deny say what they answer, in an order the keyboard can use

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q48 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list

**The problem:** No button anywhere is labelled Approve where only person asks wait; buttons are 'Deny' and 'Done' with no object; Deny comes before its reason box in tab order, so the keyboard path denies before a reason can be typed; Deny is borderless beside a bordered Approve.

**The change:** Buttons carry their object in the accessible name and, where it fits, visibly ('Approve the push', 'Deny the push'). Order in the row: sentence, reason field, Approve, Deny, with equal weight. Deny is disabled until a required reason is typed.

**User stories it serves:** E3, H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
Tabbing through a request reaches the reason field before the Deny button; each button's accessible name contains more than one word and is unique in the list; Approve and Deny have the same border style.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
