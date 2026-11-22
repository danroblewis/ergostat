# ui-a-caption-names-the-diagram-the-model-s-purpose: A caption names the diagram, the model's purpose and the verdict

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q02 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram (all views)

**The problem:** The home page has no h1, the SVG has no name, and nothing says which discipline's diagram this is or what the model is for. The model's purpose sentence is never shown.

**The change:** One line under the view switch, which is the page's h1 and the SVG's accessible name: 'Stock-and-flow diagram (system dynamics) · the-job: <purpose> · 2 systems · 28 goals, 2 off' and 'Block diagram (control) · … · 16 control loops, 2 off'.

**User stories it serves:** A1, G1, H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
/diagram has exactly one h1; it contains the project's purpose text and the view's diagram type; the diagram svg has aria-labelledby pointing at it; switching to Blocks changes the type words.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
