# ui-the-list-holds-still-while-i-am-in-it-and-a-requ: The list holds still while I am in it, and a request stays until it is answered

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q47 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list; /agents table

**The problem:** With the pointer on the list the three requests were pushed out by new alarms within 24 s; a typed deny reason vanished with its request and focus fell to the body. On Agents a click opened a different agent because rows re-sorted between hover and click.

**The change:** While the pointer or focus is inside the side list (or the Agents table) do not reorder or remove rows; show '3 updates waiting' at its top and apply them on leave. A request stays in place until answered or withdrawn, and then says so in its row.

**User stories it serves:** E3

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
Hover the third request on :8792 for 40 s: its bounding box top changes by 0 px and it is still present; type in its reason box and wait 40 s: the text and focus remain. On /agents hovering a row for 20 s leaves the row order unchanged.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
