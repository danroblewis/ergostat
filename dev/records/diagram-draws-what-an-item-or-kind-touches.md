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
