# ui-a-system-alone-at-its-level-opens-whatever-model: A system alone at its level opens, whatever modelling does

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q15 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram top level (the-job)

**The problem:** The-job's README says the page opens with 'job' open; it opens as two closed boxes because modelling counts as a sibling. The stock-and-flow diagram is three levels down.

**The change:** When the level holds one system besides modelling, start with that system open.

**User stories it serves:** A1, H2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8792/ at first load the 'job' system is open (its ten domains are drawn as boxes) and modelling is closed; a stock of 'incidents' is reachable in at most two clicks.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
