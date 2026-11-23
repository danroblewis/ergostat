# Diagram notation: owner items 6, 8, 9 (engineer's reading)

Code read at ergostat main 2468c59b. Screenshots: shots/plan-notation-*.png.

## Item 9: the side panel's default is the symbol legend first

Where: `ergostat/web/static/diagram.js:1332-1406` (`renderSide`). Order today: "Not running" note,
charts of chosen parts (1345), **Needs attention** (1347-1362, capped at 6), **Suggestions** (1363-1374,
open whenever a loop is off), charts charted last (1375), the loops list (`sdLoopList`,
`dynamics.js:421`, or the Blocks loop rows 1378-1388, or `pmSide`), "The model" edits (1390-1400), and
last **How to read it** (`legendBox`, 1405).

Why it behaves so: the legend is appended last, and `legendBox` (`diagram.js:1309-1314`) writes
`ergostat.legend = closed` to localStorage the first time it renders, so after the first visit the
legend is a closed `<details>` under 30 loop rows (shots/plan-notation-sf-dyn-open.png: the legend is
not even on screen at 1440x900).

Change: in the default state (nothing selected) put `legendBox(view)` first, open unless the reader
closed it; drop the first-visit "closed" write; then Needs attention; then Suggestions, the loops
list and The model each as a closed `<details>` with its count in the summary; the "charted last"
fallback charts go (charts show only when parts are chosen). All three views (Dynamics, Blocks,
Process). Quick: about 40 lines in diagram.js, a handful in dynamics.js (wrap `sdLoopList` in a
details), one render test.

Overlaps: Q42 (three headed groups in Needs attention) orders what sits *below* the legend, so it
still applies; Q43 asks for "what waits for me first on a phone", which collides with "legend first"
(question 1 below); Q35 and Q68 add legend rows; Q74 makes side rows buttons; R3 (side list as the
Inbox) is reshaped: the Inbox groups follow the legend.

Risk: low. The test at `tests/test_diagram_rendering.py:1970` splits the side text at "How to read
it" and checks the words before it; with the legend first that check must move to the text after the
legend.

## Item 8: a second tone, and system groups drawn as corners

Where:
- Tokens: `style.css:39-44` (light) and `:88` (dark). The SD view draws every stroke in one
  `--sd-ink`: stocks 510, valves 512, pipes 513/521, modules 516, connectors 523 (1.1 px), heads 524,
  signs 525. The only other tones are `--sd-muted` for text and the accent for what is lit. Blocks
  likewise: `bd-wire`, `bd-line`, `bd-bar` all `--ink` (454-476).
- Sector (open system) drawing: `diagram.js:652-675` (open systems laid out as containers) and
  `676-731` (overlapping outlines when no tree), styled inline by `hueOf` (`diagram.js:655`):
  `fill:var(--sd-hull);stroke:none`, rx 16. CSS `style.css:519` removes any stroke. So a sector is a
  4 % grey slab with round corners (shots/plan-notation-sf-dyn-open.png, the dark one
  plan-notation-tf-dyn-open-dark.png shows nested slabs). SPEC.md:3777 and DESIGN.md:151 describe
  it ("a light tint"); the render test `tests/test_diagram_rendering.py:1964,1972-1973` asserts it.
- Blocks frames: `blocks.js:778-800`, CSS `style.css:478-481` (1 px muted rectangle, cascades dashed).
  Process map frames: `style.css:390` (`--line-strong` rectangle).

Why it reads badly: everything that is structure (a pipe, a stock) and everything that is
information (a connector, a sensor's record line, a frame) is the same ink at nearly the same weight,
so in a 60-line drawing nothing comes forward. The standard practice the owner names is the hierarchy
material > information > grouping, done with tone and weight, not hue. It keeps decision 2 (Blocks
monochrome; Dynamics black on white): tones of the ink are still monochrome.

Change (decided here, so the gap has no open design question):
1. Two new tokens per theme in the token block: `--sd-ink-2` (information: about 62 % ink on paper,
   ≥ 4.5:1 so a 1.1 px line and its head stay readable) and `--frame` (grouping: about 35 %, ≥ 1.6:1),
   plus `--frame-mark` (the corners: `--ink-2`). Also `--accent-2` (the accent's lighter tone) so a lit
   loop's connectors are the lighter accent and its pipes the full one.
2. Dynamics: connectors, their heads, stubs and shadow lines in `--sd-ink-2`; pipes, stocks, valves,
   clouds, modules, loop markers and polarity signs stay `--sd-ink` (a sign is text; it keeps full
   contrast and so reads on its lighter line).
3. Blocks: the sensing chain (signals whose `what` is `record`, the collector-to-bus-to-sensor lines)
   and the bus bars in the second tone; the loop itself (r, e, u, y, y_m, d) stays ink. Needs a
   `bd-<what>` class on each edge group (`blocks.js:821`, where `bdEdgeContent` is used).
4. Sectors, Blocks frames and Process frames: no fill; a hairline rectangle in `--frame` with square
   corners, and over it an L-shaped mark at each corner (12 px arms, 1.4 px, `--frame-mark`); a
   nested frame's arms 8 px. The rectangle element stays (colours.js:79 and interact.js:104 select the
   frame's `rect:not(.hull-grip):not(.hull-mark)` for the correspondence rings and the cross-pane
   mark); the corners are one `path.frame-corners`. The name stays at the top left. Modules (closed
   boxes) are parts, not groups, and keep their outline.
5. Legend rows (`SD_LEGEND`, `dynamics.js:450`; Blocks legend `blocks.js:~1122`; process legend) show
   the tones and the new sector glyph; the export legend (`export.js:58-68`, `sdExportLegend`) the
   same; export inlines computed styles (`export.js:14-21`) so tones carry into PNG/SVG.
6. Docs: SPEC.md:3777 "a sector, framed by its corners", DESIGN.md:151 and the Colour paragraph
   (one sentence on the three tones), layout-rules if it names the tint.

Size: incremental (style.css tokens and ~15 rules, diagram.js ~30, blocks.js ~15, process.js ~5,
dynamics.js legend ~10, tests ~30; about 120 net lines). Risk: dark-theme contrast (compute it in the
test), the Guide's thumbnails (Q06 is about their box fill: they use the same drawing, so check
/guide?frame=2 and 12), `tests/layout_geometry.js:45` treats `g.hull` as a hit target (unchanged), and
`test_style_tokens.py` (new colours only as tokens).

Overlaps: Q13 (modelling drawn with a dashed outline: its frame becomes dashed corners+line, same
code), Q27 (a box holding an off goal has a heavier outline: modules, not sectors; compatible), Q35
(dashed stock), Q70 (export), Q06 (Guide box fill). None is superseded.

## Item 6: MIMO (bundled) connectors in Dynamics

Where Blocks has them: `ergostat/blockdiagram.py:672-688` (a collector read by 3+ counts goes through a
bus bar), `:943-962` (a MIMO process gets a mux before it and a demux after it, carrying vectors u
and y), `:1325-1341` (two or more signals between the same two subsystem blocks become one vector
`vec:a>b` with a count). Drawn by `blocks.js:932-950` (bold wire, a slash, the count) and the bars
at `blocks.js:671-672`. Seen in shots/plan-notation-sf-blocks-top.png: one bold line, slash, "3".

Where Dynamics lacks them: `ergostat/fold.py:112-137` gives a closed system one port per part that
crosses its edge, and every connector keeps its own line; `ergostat/dynamics.py:320-432` (`finish`,
`shadows`) then turns lines to parts not drawn into shadows and stubs, never merging them. Drawn
per line by `dynamics.js:186-214` with its own sign; ports laid out per row by `diagram.js:97-101`.
Measured on the demos (GET /api/graph): ticket-factory with factory and modelling open has 37
connectors, 21 of them between two closed modules, in 7 pairs, 5 pairs with 2 or more (up to 6
parallel lines): shots/plan-notation-tf-dyn-open-dark.png shows the six-line cables between review,
shipping and oversight. software-factory's top level: 6 lines in 2 pairs, signs stacked at the
receiving edge (the problem Q25 names). Bundling would draw 7 lines in place of 21.

Why it is large: it is a notation decision under decision 2 ("each diagram true to its discipline;
never mix the notations"). The Blocks vector (slash and count, mux/demux bars) is control notation and
must not be copied as is. System dynamics does have its own form: Stella's modules connect through
bundled connectors and bundled flows (isee systems), and Vensim has none; that has to be checked and
the glyph chosen to match. And several questions are not code questions:
- polarity: a bundle has no single sign. Q25 (filed) wants every top-level link signed and each sign
  on its own arrow; bundling replaces that for module-to-module lines. What does the line carry
  ("3 +, 1 −") and where do the signs live (its panel)?
- material vs information: a pipe crossing modules is a flow; Flows only (`dynamics.js:499`,
  `sdFlowLinks`) keeps connectors whose tail is a rate. One bundle or two (a bundled flow and a
  bundled connector)?
- where it unbundles: at a closed box the members meet their port rows, so the bar is the box edge
  spanning those rows (needs the rows of one bundle adjacent: port order in `diagram.js:45-46`). A
  part that feeds two modules is in two bundles: repeat its row or not? Into an open sector, the
  members go to parts spread over the sector: unbundling there is edge bundling in the router
  (`avoid.js`, libavoid), which belongs with the layout work of owner item 10.
- loops: a loop through one member lights the bundle and says which ("R3 runs through 1 of 4");
  `correspond.py` must make the bundle stand for its members' parts.
- R1 (the closed box as control panel, goal rows) changes what the rows of a box are; the bundle's
  bar must sit with the port rows, not the goal rows.
- threshold (2 lines, as Blocks between subsystems, or 3, as the bus) and whether a toggle exists
  (default on, no toggle, is my recommendation).

So: a proposal gap first (`docs/proposals/dynamics-bundled-connectors.md`), then module-to-module
bundles (incremental, the bulk of the value: closed boxes are the folded "control panel" view), and
trunk bundling across open sectors filed by the proposal for after the layout rewrite.

Risk of the implementation: the layout (ELK ports, `diagram.js:97-101`, `portSides`), the line
redraw after a drag (`diagram.js:602`, owner item 7's cluster), `layouts.js:170,312` port ownership,
loop highlighting (`sdApply`, `dynamics.js:400`), correspondence colours (`colours.js`), export, and
Q25's acceptance test, which counts a sign per link.

## Other things seen

- The live factory's graph API (`GET http://127.0.0.1:8798/api/graph?view=dynamics`) did not answer
  within 170 s (twice; 60 s then 170 s). For owner item 2's cluster.
- DESIGN.md:146-148 still says "action purple" and "green holding": stale against the monochrome SD
  view; fix in the same docs pass as item 8.

## Questions for the owner (one sentence each)

1. On a phone, should requests waiting for your answer sit above the symbol legend (Q43), or is the
   legend first everywhere?
2. For system groups: corner marks joined by a light hairline (my pick), or corner marks alone?
