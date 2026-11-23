# diagram-draws-what-an-item-or-kind-touches: The Dynamics and Blocks diagrams draw only what an item passed through, or what a kind touches

depends-on: [kind-and-item-footprint-api, item-and-kind-footprint-proposal]

Problem: owner item 20: 'the subset of the Dynamics and Blocks diagrams it passed through'. /api/graph draws an explicit subset only through around= (one part and its neighbours, ergostat/graph.py:19, server.py:512) and only in Dynamics; Blocks (blockdiagram.diagram, blockdiagram.py:1423) takes only open_ and focus.
Change, as the proposal decided: /api/graph accepts item=ID or kind=K. Dynamics: the footprint's or path's parts become the set passed to graph.select, as around= does. Blocks: the control loops (goals) the footprint touches, drawn whole. The Diagram page shows a chip ('what ticket/SCRUM-2 passed through ×', like the around chip at diagram.js:1118), numbers each stock on an item's path in move order and prints attempts on each valve. Pins key on item and kind too (diagram.js:1032) so a subset's pins never move the full diagram; the folded system tree is skipped for a subset as for around, with each part still showing its system. The item page's 'Where it went' gains 'Draw its path in Dynamics' and 'in Blocks' links (/diagram?view=dynamics&item=ID); the kind's footprint is reachable as &kind=K.
Definition of done:
1. /diagram?view=dynamics&item=ticket%2FSCRUM-2 on ticket-factory draws exactly the stocks and valves on that ticket's path, numbered 1..n in move order, and nothing else.
2. view=blocks&item=... draws the control loops it touched, each whole.
3. kind=ticket draws the kind's footprint.
4. An item of a kind nothing counts shows 'not counted anywhere in the model' and no link.
5. Clearing the chip draws the diagram as before; no console errors; layout time for a subset on the factory graph fixture under 1 s.
6. SPEC's diagram section documents item= and kind=.
Files: ergostat/web/server.py, ergostat/graph.py, ergostat/blockdiagram.py, ergostat/web/static/diagram.js, pages.js (links), docs/SPEC.md, tests/test_diagram_rendering.py, tests/test_items_page.py.
Acceptance tests: test_an_items_path_is_drawn_alone (node ids equal the path's parts; numbers in order), test_blocks_draws_whole_loops_an_item_touched, the link test on the item page. Each fails on main.
Budget: 200 net lines.

Milestone: kind-and-item-pages. Owner items: 20, 15. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1: every done item has code and a test. The size is 105 net lines of code (126 added, 21 removed, in
ergostat/), inside the 200-line budget. Decisions taken alone, each the most reversible option:

- *Where it went* is not on main yet (item-page-says-where-it-went has not landed), so the item page gets a minimal
  section in its place, after the state track. It holds the two links and the kind's (`what every K touches`), or
  "Its moves are not counted anywhere in the model." with no link. That gap can take the section over and add its
  path strip.
- Numbers follow this definition (1..n in move order), not the proposal's visit counts. Only the steps whose state a
  stock counts are numbered, so the drawn numbers run 1..n with no gaps. A valve's `attempts` is the number of runs
  of its block that took the item.
- Blocks keeps the nodes `mark_loops` marks with a touched goal. It also keeps any node fed by one of those and
  feeding one (a stock's `psum:` sum). Without that, a loop drawn alone was cut at its sum; a mutation run showed it.
  `mark_loops` itself is left alone.
- An item's pins use its kind's key, which the page learns from the answer's `subset.kind`. A kind's pins use
  `.kind:K`.
- dynamics.js is outside the Files list. It draws the marks: 5 lines in `sdStock` and `sdLabelLines`.
- Not built, because this definition does not ask for it: the proposal's fallback for a set over 150 shapes, its
  measurement on dev/model, the kind's marks (items now, attempts in the window), and the Blocks strip that names
  footprint parts that are in no loop.
- Done item 5's "factory graph fixture" was not identified. The 1 s bound is checked in
  test_an_items_path_is_drawn_alone, on the ticket-factory subset, with the page's own layout timer.

Tests run, one file or test at a time: the three acceptance tests (they pass, and each was seen to fail with its
guarded code broken: fold's `keep`, the sum kept, the stock numbers drawn, the item link).
test_blockdiagram.py, test_footprint.py, test_graph_parts.py, test_graph_cli_web.py and test_correspond.py all pass.
test_every_view_loads_with_no_console_error_or_warning[ticket-factory] passes. Ruff is clean. `main` was merged and
was already up to date. Not run here: the whole unit suite and the four browser files (the queue runs them).

Round 2: the queue's one finding was a conflict with main in ergostat/blockdiagram.py. Main added `_effects` and
`_classes` (a system's C/P class) just above `fold`; the branch had added fold's `keep` parameter. The merge
(dc8ad98d) keeps both: main's two functions as they are, and `fold(d, open_, focus, keep=None)` with the branch's
docstring. No other finding was raised. After the merge: the three acceptance tests, test_blockdiagram.py and
test_correspond.py pass; ruff is clean. Not run here: the whole unit suite and the four browser files.

Round 3: the queue's one finding was a conflict with main (b7302db6) in tests/test_diagram_rendering.py. Both sides
had added tests at the same place, the file's end: the branch's item=/kind= tests and main's closed-module sparkline
tests. The merge (ddba6aae) keeps both blocks whole, the branch's first. No code changed. After the merge, these
pass: the two acceptance tests in test_diagram_rendering.py, main's two sparkline tests (3 cases), and in
test_items_page.py the link test and the lifecycle strip test. Ruff is clean. Not run here: the whole unit suite and
the four browser files.
