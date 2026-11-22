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

## Where it stopped

Built (round 1). There are 43 net lines in blocks.js, against a budget of 120.

- **What blocks.js does now.** `bdCrossings` finds each place where a level stretch and an upright stretch of two
  lines both pass through one point. A line that only ends on another line is a take-off, not a crossing. The level
  wire's path carries a half-circle hop of radius 4 at each crossing. `bdTakeoffs` now works from the graph: a dot goes
  on a bend of one net's lines, or on its port, wherever three ways meet (the port's block counts as one), so never
  where two lines only pass through each other. Lines with no source port get no dots. A vector's slash and count go in
  the middle of the line's longest stretch with no crossing or bend. The exported SVG keeps the hops because they are
  part of the wire's path. export.js needed no change, and the acceptance test checks the export.
- **Decision (taking the most reversible option, since nobody answers questions):** in one place the level line's
  arrowhead lies over the crossing (software-factory, within 12px of the line's end, where no hop fits). There the
  upright line hops sideways instead. The rule accepts a hop on the upright line only in that case.
- **Decision:** `crossing-without-hop` and `dot-not-at-takeoff` are critical, because a reader takes them for a
  connection. That means they also gate the generated models' Blocks views. `slash-on-crossing` is major. In
  docs/layout-rules.md they are numbered 21–23, after the existing rules, so the rule numbers the doc already cites
  stay the same.
- **Decision:** while a part is being dragged, only the lines being dragged are drawn again, and they hop over the
  others. The other lines keep their old hops until the part is let go. Then everything is redrawn, and the
  acceptance test checks that redraw.
- **Acceptance tests:**
  - `test_the_control_view_draws_every_example_cleanly_as_a_block_diagram` now runs the three rules in every Blocks
    view of all 21 examples (whole, everything open, each system open, each system alone). All 21 pass.
  - `test_blocks_crossings_hop_dots_only_at_takeoffs_slashes_clear_and_a_drag_and_the_export_keep_them`
    (software-factory, everything open: 29 crossings) checks the three rules before and after a drag, and that the
    exported SVG keeps the hops. It passes.
- **Seen to fail when the code is broken (lesson 9):**
  - with no hops, `crossing-without-hop` fails;
  - with a dot drawn at each crossing, `crossing-without-hop` and `dot-not-at-takeoff` fail;
  - with the slash put on a crossing, `slash-on-crossing` fails;
  - with main's slash placement (the middle of the longest segment), `slash-on-crossing` fails in coordinator,
    image-squeeze, software-factory, the-job and ticket-factory.
- **Not checked here:**
  - Items 1 and 4 as worded: the live pages on :8793, :8796 and :8797 and the six demos in ~/ergostat-demos are not
    reachable from this container. The examples above stand in for them.
  - The screenshots named in the Problem (shots/) are not in the clone.
- **tests/test_diagram_rendering.py, run whole and serially, twice:**
  - Run 1: 199 passed, 2 failed.
  - Run 2: 200 passed, 1 failed.
  - Both runs failed `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`, on the /model
    page's "Nothing waiting." check. An earlier review records this failure on main. This branch does not touch that
    page. I could not compare it on main myself, because `git checkout main -- …` was refused here.
  - Run 1's second failure did not come back in run 2. Its name was lost to an output tail, so it is unnamed.
  - The other three browser files and the unit suite were not run here; the factory and the merge queue run them.
