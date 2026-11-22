# ui-the-window-in-the-header-never-claims-more-than: The window in the header never claims more than the record

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q19 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** header window menu; /loops footnote; charts

**The problem:** The header says 'Last 1h' while 33 minutes are recorded; percentages such as 'off 93% of the time' look heavier than the data supports.

**The change:** When the record is shorter than the window the header reads 'Last 1h (33m recorded)', and every 'of the time' figure says 'of the 33m recorded'.

**User stories it serves:** B5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On a demo started less than an hour ago the header window control contains 'recorded' and a duration; a suggestion containing '% of the time' also contains 'recorded'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
