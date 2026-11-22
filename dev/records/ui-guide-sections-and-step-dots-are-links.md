# ui-guide-sections-and-step-dots-are-links: Guide sections and step dots are links

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q08 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /guide

**The problem:** Section names ('Control: what we control', 'Yours') do nothing; dots are 12 px targets named only by title, with the current step shown only by fill.

**The change:** Section names jump to their first frame. Dots get a 24 px hit area, aria-label 'Step n of 13' and aria-current='step'.

**User stories it serves:** A3, H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
Clicking 'Control: what we control' changes ?frame to that section's first frame; each dot's clickable box is at least 24x24; exactly one dot has aria-current='step'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
