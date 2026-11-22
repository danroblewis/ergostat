# ui-timeline-draws-each-item-s-states-over-time-rela: Timeline draws each item's states over time, relations or not

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q59 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /items Timeline and Graph

**The problem:** On demos whose items have no relations Timeline shows the same charts as List plus a configuration instruction, though its tooltip promises 'A Gantt chart: each item's states over time'. Switching mode barely changes the screen.

**The change:** Without relations, Timeline draws one bar per item, split by state over time. Graph says 'These items do not wait on one another, so there is no dependency graph'. In both modes the mode's own content comes first, above the per-kind charts.

**User stories it serves:** F5, F2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791/items?view=timeline one row per ticket (8) is drawn with segments labelled by state, within the first 900 px; the page does not contain 'relations:'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
