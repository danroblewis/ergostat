# ui-from-items-to-the-process-map-and-the-map-says-h: From Items to the process map, and the map says how many are there now

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q57 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /items; /diagram?view=process (States)

**The problem:** Where work queues is shown only on the Process map, which Items does not link to; the map's node counts are visits ('18× · 16 items'), not how many items are in the state now; node text is about 8 px at Fit.

**The change:** Each kind's name on Items has a 'process map' link to /diagram?view=process&kind=<kind>&mode=states. In States mode each node shows 'now 3' before the visit count. The map fits at no less than 11 px text and says which way more lies.

**User stories it serves:** F3

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796/items the ticket kind has a link whose href contains 'view=process'; on that map every node contains 'now ' and a number equal to the Items legend's count for that state; no node label is below 11 px.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
