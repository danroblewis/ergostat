# export-model-and-loops-markdown: Export the model behind the picture: Dynamics as a variable table and loop list, Blocks as a loop table, in Markdown

depends-on: []

Problem (R10): WHY.md leads with design documents, proposals and projection, but Export offers SVG, Design SVG and PNG only (ergostat/web/static/export.js, 114 lines; shots/story-6-g8-export-menu.png, sdx-8796-export.png). An SD modeller cannot audit the equations in one pass; a control engineer cannot read the loops as a table. Story G8: picture yes, model no.
Change: two entries in the existing Export menu, each for the system drawn (what is open or entered), produced by a server endpoint so the CLI can use it too (GET /api/export?view=dynamics|blocks&format=md&system=...): (1) Dynamics 'Model (Markdown)': a variable table (name, kind: stock/flow/auxiliary/goal, unit, equation or sensor in words, value now), the flows per stock (in, out), and the loop list (name, R/B or '?', path, the goal it closes); (2) Blocks 'Loops (Markdown)': one row per control loop (goal, reference, measured output, controller and its law in words, actuator, process and whether identified, sensor and period, the goal's word). The document starts with the model's name, purpose, the moment and the window, and names the system. Equations use the same words as the panels (equations.js / block_fn). Download with a file name carrying project, view and date.
Definition of done:
1. On :8796 ?system=product Export > Model (Markdown) downloads a file whose variable table has one row per part drawn and whose loop list equals the side list's.
2. On :8791 ?view=blocks Export > Loops (Markdown) has one row per goal in view, with the law's words equal to the Blocks panel's.
3. The Markdown renders as tables (a test parses it).
4. The export of a snapshot file works offline or says it cannot.
Files: new ergostat/web/export_api.py, ergostat/web/server.py, ergostat/web/static/export.js, tests/test_export.py.
Acceptance tests: unit tests of both documents on a small spec; a browser test of the two menu entries.
Budget: 180 net lines.

Milestone: r10-take-the-model-out. Owner items: R10 pieces 2, 3 (piece 1 is filed Q70). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. Net lines outside tests and docs: 144 (export_api.py 114, server.py 16, export.js 12,
diagram.js 2), within the 180 budget.

What was chosen where the definition left room (each the most reversible reading; none changes the model or a page):
- Both documents are read off the answer the page itself draws (`/api/graph`, same `system`, `around`, `open`,
  `since`, `at`), so "a row per part drawn" and "the loops in view" are the page's own sets, not a second derivation.
- Dynamics: a variable is a drawn stock, auxiliary, flow (valve or disturbance), or a goal's desired level or gap
  (kind "goal"); clouds, system boxes and shadows are not variables. A flow's words are `dynamics.equation` (the
  panel's "equation" row); an auxiliary's its written equation, else "from outside the model (exogenous)" or
  "no equation"; a stock's "the integral of its flows"; each followed by its sensors and how often they read.
- The loop list is the side list's set (dynamics.js `sdLoopList`), in its order: drawn loops of known polarity, then of
  unknown polarity, then the loops inside a closed system, which the side list only counts (column "drawn" says
  "inside S"). The count equals the side list's heading count.
- Blocks: a row per loop in the side list (`g.loops`), in its order (off first). The law is `block_fn`'s `says` for
  each of the loop's controllers, the words of the Blocks panel's first paragraph (the panel draws `y_inbox` as a
  subscript; the text is otherwise equal, and the browser test checks it). "The goal's word" is read as the loop's
  status now (holding, off, unknown), in the column "now".
- The endpoint answers `format=md` (the default: text/markdown, for curl) or `format=json` ({file, markdown}: the
  page uses it for the file name); any other view or format is a 400.
- A snapshot file has no server: the menu entry says so in a dialog rather than export a partial document.
- The menu entries are added in diagram.js (where the Export menu is built), a file not in the Files list: two lines.
- The file name is `<project>-<system or all>-<view>-<YYYY-MM-DD>.md`, the date of the moment shown.

Not run here: the definition's checks 1 and 2 name the demo ports :8796 and :8791, which this container does not
serve. In their place: `test_software_factory_product_dynamics_matches_what_is_drawn` (the software-factory example,
system=product) and the browser test on a small model served by `ergostat web`. Each new test was seen to fail on a
deliberate break: disturbances dropped from the variable table, the Blocks entry asking for the Dynamics document,
and the snapshot check inverted.
