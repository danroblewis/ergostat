# ui-off-in-a-chart-is-a-mark-as-well-as-a-colour: 'Off' in a chart is a mark as well as a colour

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q76 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** loop evidence scope charts; /item lifecycle; /agents tier arrows

**The problem:** Off periods in the y/u/e charts are a pale pink (light) or maroon (dark) band keyed only by the text 'Red: off'; tier arrows and count arrows are 1.6:1.

**The change:** Hatch the off bands and label them 'off' on the time axis; the key is a hatched swatch labelled 'off'. Raise arrows and Guide dot borders to at least 3:1.

**User stories it serves:** H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
The scope's off bands have a pattern fill; the legend contains a swatch element with the same pattern and the word 'off', and no text 'Red: off'; computed contrast of tier arrows against the background ≥ 3:1 in both themes.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
