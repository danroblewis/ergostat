# ui-a-number-or-reason-asked-of-a-person-has-a-full: A number or reason asked of a person has a full label and a unit

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q45 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list inputs

**The problem:** Inputs are 80 px wide with placeholders cut to 'how ma' and 'why (to de'. 'how many' has no unit; it appears even on a yes or no decision ('declare an incident?'). The reader cannot say what a typed number means.

**The change:** A visible label above each input, from the ask: 'Ramps you decided (number)', 'Reason for denying (required)'. Inputs take the row's width. An ask whose answer is yes or no gets two buttons, not a number box.

**User stories it serves:** E2, H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
Every input in the side list has a visible <label> whose text is fully shown (scrollWidth ≤ clientWidth) and, for a number, names a unit; no placeholder is truncated.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
