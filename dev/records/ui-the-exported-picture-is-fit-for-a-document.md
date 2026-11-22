# ui-the-exported-picture-is-fit-for-a-document: The exported picture is fit for a document

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q70 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram Export (PNG, SVG)

**The problem:** The Dynamics PNG loses every loop name, turns connectors into dotted fragments where label halos were, cuts '225 users' and breaks links; the Blocks PNG has no legend and clips subscripts.

**The change:** Rasterise from the same SVG the page shows (halos as paint-order strokes, fonts embedded), in light mode whatever the theme. Include title, date, window and the legend in both views.

**User stories it serves:** G8

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
Export PNG of :8796 ?system=product: the image text (by OCR or by the intermediate SVG's text nodes) contains every loop name on screen and '225 users'; the Blocks export contains the legend's text; the background is white in dark mode too.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
