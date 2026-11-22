# ui-what-i-selected-stays-selected-with-its-panel-wh: What I selected stays selected, with its panel, when I switch view

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q63 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram (Dynamics ↔ Blocks)

**The problem:** Selecting the stock quality and switching to Blocks highlights the sensor H(s), not the process output, and the panel falls back to Needs attention. Clicking a flow's label opens 'Charts of the parts chosen' instead of its panel; in Blocks its panel is titled 'Valve'.

**The change:** Keep the panel open across the switch, titled in the target discipline's words: 'output y_quality of P_service', 'actuating signal u_tuner', 'reference r = 0.93 and its summing junction'. Map a stock to y at the process output. A plain click on a flow's label opens the flow's panel.

**User stories it serves:** G2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8793 ?system=service select stock quality, switch to Blocks: within 1 s the element y_quality at the process output has the selection ring and the side panel's title contains 'y'; clicking the label 'quality-steps' in Dynamics opens a panel whose title contains 'quality-steps'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
