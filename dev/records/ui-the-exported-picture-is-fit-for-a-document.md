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

## Where it stopped

Round 1, built: 25 net lines in `ergostat/web/static/export.js` and `style.css` (+33 −8).

What was wrong, and what changed:
- Loop names lost: `.marker-name` gets its halo from CSS `paint-order: stroke`, which the exporter did not copy, so the
  paper-coloured halo was painted over the text. Connectors broken: the loop markers' ground (`fill-opacity: 0.85`)
  came out opaque. The exporter now copies `paint-order`, `fill-opacity`, `stroke-opacity` and `font-style` as
  resolved values.
- Light whatever the theme: style.css's dark tokens are now `:root:not(.export-light)`. `standaloneSvg` sets that class
  on `<html>` while it reads computed styles and removes it in a `finally`, so SVG, Design SVG and PNG all come out light
  (a white ground, dark ink). The page is never repainted in between.
- The Blocks legend: the export added a legend only where a `.k-stock` was drawn, so Blocks had none. A new
  `bdExportLegend` builds it from `blocksLegend()` (the same rows as the page's legend: each symbol, then its words
  wrapped to the drawing's width). Title, date and window were already in both views' pictures (`exportTitle`).
- Fonts: the page has no web font (no `@font-face`), only the system stack. That stack is written on the file's root as
  before, so there is nothing to embed.
- Subscripts: I tried widening the picture to the viewport's bounding box, but with or without it no text in the product
  Blocks export lies outside the image. Nothing showed the change mattered, so it was taken out (the more reversible
  choice). The test checks instead that every text in both pictures lies inside them. If subscripts are still cut in
  another view, that is not shown here and is not claimed fixed.

Test: `tests/test_diagram_rendering.py::test_the_exported_png_shows_every_loop_name_the_values_and_its_legend_on_white_in_dark_mode`.
With the page in dark mode and `users` recorded at 225, it rasterises the export as `exportPng` does and checks:
- the corner pixel is white;
- each loop name on screen, '225 users' and the title lines have ink of their own (dark pixels where the text is that the
  same picture drawn with no text lacks);
- every translucent part on the page stays translucent in the file;
- the Blocks picture has every row of the Blocks legend and the title.

Each fix was broken once and the test watched to fail: no `paint-order` (loop name 'churn and asks' had no ink), no
light class (corner 23 ≠ 255), no Blocks legend (rows missing), no `fill-opacity` (17 seen-through parts on the page,
0 in the file).

Run: the new test, with `test_flows_only_export_legend_lists_only_what_is_shown` and
`test_flows_only_hides_links_and_non_flow_parts`, passed. `tests/test_style_tokens.py` passed and ruff is clean. The whole
`tests/test_diagram_rendering.py`, run serially under the watchdog, gave 200 passed and 1 failed in 37 min. The failure,
`test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page` (tests/test_diagram_rendering.py:3390,
"Nothing waiting." not on /model after a calibration is accepted), fails alone too. It runs in the light scheme on the
/model page and never calls the exporter; this branch only adds code that runs on Export plus a selector that applies
only in dark mode, so it is unrelated (lesson 13). I could not show it fails on main: `git checkout main -- <files>` was
refused. Not run here: the other three browser files and the unit suite (left to the factory and the merge queue).
There is no remote in the clone, so local `main` is the base and nothing was merged.

## Where it stopped (round 1, after the build step)

The factory's `build` step failed with rc 5. It runs `affected_tests.py` without Playwright. This branch's only changed
test file was the browser file `tests/test_diagram_rendering.py`, so the whole module was skipped and nothing ran. The
page code was not at fault. `tests/test_style_tokens.py` now has
`test_the_dark_tokens_stand_aside_while_a_picture_is_exported`, a unit check of the style.css change: every dark-theme
rule excludes `.export-light`, and export.js sets and clears that class. With this file changed, the build step has a
test that runs without a browser. Broken once (`:root:not(.export-light)` put back to `:root`): the test failed.
Restored: `tests/test_style_tokens.py` passed (6), and ruff is clean. No change outside `tests/` and this record.
That a build of browser-only test files returns rc 5 is a factory matter (scripts/affected_tests.py), not this gap's.
It is reported here and not fixed (lesson 13).
