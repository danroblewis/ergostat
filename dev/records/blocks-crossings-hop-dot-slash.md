# blocks-crossings-hop-dot-slash: Blocks: a hop at a crossing, a dot only at a take-off, the vector slash away from crossings

depends-on: []

Problem (R4 piece 9): in Blocks two wires that cross are drawn as a plain cross, the same mark a junction without its dot would make; take-off dots are sometimes drawn where wires merely cross; and a vector's slash and count can land on a crossing (shots/ceb-is-service-fit.png, ce-sf-blocks-product.png). A control engineer cannot tell a connection from a crossing.
Change: after routing, blocks.js computes the crossings of drawn wire segments (segments are orthogonal, so the test is cheap) and draws a small semicircular hop on the horizontal wire at each crossing; a filled dot is drawn only where a wire takes off from another (a shared end point on a segment's interior in the graph, not geometry); the vector slash and its count (blocks.js:932-950) are placed on the longest crossing-free stretch of the wire, at least 12 px from any crossing or bend. Add layout rules 'crossing-without-hop', 'dot-not-at-takeoff' and 'slash-on-crossing' to tests/layout_rules.py. Export keeps the hops.
Definition of done:
1. On :8793, :8796 and :8797 in Blocks with everything open, every wire crossing has a hop and no dot.
2. Every dot is at a take-off in the graph.
3. No vector slash lies within 12 px of a crossing.
4. The three rules report 0 on the six demos; redraw after a drag keeps them.
Files: ergostat/web/static/blocks.js, export.js, tests/layout_rules.py, tests/layout_geometry.js, tests/test_diagram_rendering.py, docs/layout-rules.md.
Acceptance tests: the three rules over the corpus; a drag-then-check browser test.
Budget: 120 net lines.

Milestone: r4-blocks-textbook. Owner items: R4 piece 9. From the owner's list and the design review of 2026-11-22.
