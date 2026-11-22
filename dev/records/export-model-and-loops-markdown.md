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
