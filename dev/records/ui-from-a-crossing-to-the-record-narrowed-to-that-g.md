# ui-from-a-crossing-to-the-record-narrowed-to-that-g: From a crossing to the Record, narrowed to that goal and time

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q31 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** goal evidence panel; /record

**The problem:** Crossings and Decisions rows are not clickable; the Record filters by event type only, so a goal or agent name answers 'Nothing recorded yet.'; the filter is not in the address.

**The change:** Each crossing row links to /record?about=<goal>&from=…&to=…, which shows events of the goal, its controller, its actor and its valve. The filter box also matches item and source. The filter and the window live in the address.

**User stories it serves:** C5, H6

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8797 clicking a crossing of billing-q0-low lands on /record with 'about=' in the URL and only rows whose type, item or source belong to that goal; typing 'fixer' on :8791/record shows rows; reloading the URL keeps the filter.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
