# diagram-frames-corners: System frames drawn as corner marks joined by a hairline; a closed system's outline light unless a goal in it is off

depends-on: []

Problem: the owner: 'technical diagrams draw only the corners as short lines, or corners with a lighter connecting line'. Dynamics open sectors are 4% grey slabs with 16 px round corners and no outline (ergostat/web/static/diagram.js:652-675, 676-731, styled inline by hueOf at 655; style.css:519 removes any stroke); tints add up when nested (shots/plan-notation-sf-dyn-open.png) and the edge is lost on a large canvas (plan-notation-job-openall-dyn.png). Blocks frames are full 1 px muted rectangles (blocks.js:778-800, style.css:478-481), near the wires' 1.2 px, and read as one more wire (plan-notation-sf-blocks-open.png); Process frames are --line-strong rectangles (style.css:390). A closed module is a 1.4 px ink box, the heaviest mark at the top level (plan-notation-sf-home.png). SPEC.md:3777 ('a light tint'), DESIGN.md:151 and tests/test_diagram_rendering.py:1972-1973 pin today's form.
Change: one frame grammar for an open system in all three views (defaults, no owner question: corners joined by a hairline; the tint comes off Dynamics' open sectors): no fill; a hairline rectangle in a new token --frame (contrast at least 1.6:1) with square corners, plus one path.frame-corners of L marks (12-14 px arms, 1.2-1.4 px, token --frame-mark; 8 px for a nested frame). Keep the rect element (colours.js:79 and interact.js:104 select it for rings and the cross-pane mark). The name sits at the top left on the top edge with a gap behind the text. Variants: modelling (filed Q13) dashed hairline with solid corners; a cascade's inner-loop frame in Blocks dotted. A closed system's outline uses --frame-mark at 1.2 px; with an off goal (filed Q27) it is full ink at 2 px. Drag grip, toggle, Open and Into keep their hit areas; blocks.js:453's rule keeping lines off frame edges stays. Legends (side panel and export) draw the new frame glyph; the Guide frame that shows an opened system is updated. Update SPEC.md:3777 ('framed by its corners'), DESIGN.md:151, docs/layout-rules.md.
Definition of done:
1. In both themes on :8791 (factory, modelling open), :8796 (product, factory open) and :8797 (api open) no open frame rect has a non-transparent fill; each has a path.frame-corners and a rect stroke computing to --frame.
2. On a fixture, a closed system with no off goal has a lighter, thinner outline than one with an off goal.
3. modelling's hairline has a stroke-dasharray and its corners do not.
4. Dragging a frame by its name, collapsing it, the correspondence rings and the cross-pane hull mark still work.
5. The layout corpus's line-overlap-with-frame counts do not rise; tests/test_diagram_rendering.py passes with lines 1972-1973 rewritten.
Files: ergostat/web/static/diagram.js, dynamics.js, blocks.js, process.js, colours.js, export.js, style.css, ergostat/guide.py, tests/layout_geometry.js, tests/test_diagram_rendering.py, docs/SPEC.md, docs/DESIGN.md, docs/layout-rules.md.
Acceptance tests: computed-style checks per view on the three demos in both themes; the dasharray check on :8796/ and :8797/.
Budget: 110 net lines (minus the tint rules removed).

Milestone: diagram-notation. Owner items: 8 (boxes around system groups). From the owner's list and the design review of 2026-11-22.
