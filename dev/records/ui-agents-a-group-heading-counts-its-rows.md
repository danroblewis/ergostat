# ui-agents-a-group-heading-counts-its-rows: Agents: a group heading counts its rows

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q37 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /agents

**The problem:** The summary says '2 person → 4 ai → 13 program → 16 rule'; the headings below say '0 person', '1 ai', '4 program', '5 rule'. The heading number is the rung of the ladder, set exactly like a count. Seven reviewers read it as a bug.

**The change:** Headings read 'person · 2', 'ai · 4' with the rung as small text ('rung 0, the most general'). The summary chips drop the arrows or say 'most general → most specific' once.

**User stories it serves:** D1

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791/agents each group heading's number equals the number of rows under it and equals the summary line's number for that kind.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
