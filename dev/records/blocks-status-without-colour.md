# blocks-status-without-colour: Blocks: a loop's state is printed on its error signal in the goal's one word and in bold when not holding, never by colour

depends-on: [goal-row-one-renderer]

Problem (R4 piece 7): Blocks is monochrome by decision 2, and today nothing on the drawing says which control loop is off; status is read from the side list (shots/story-7-h1-blocks.png, ceb-tf-modelling-blocks-fit.png).
Change: on each loop the error signal's label at the summing junction's output prints e's value and, when the goal is not holding, the goal's `word` from the server (goal-row-one-renderer: today off, open, unknown; later approaching, in grace and the rest, with no change here) through goalWord: 'e = -36 off' in bold for off; regular weight for the neutral words; an open loop reads 'open' on its broken return; a holding loop prints e's value alone. blocks.js adds the class and text (edge labels near blocks.js:821) and never maps status itself. The legend gains one row. No colour is added: by the colour rules (docs/DESIGN.md, settled in diagram-line-tones) the accent means selection or trace in both views and Blocks has no status colour.
Definition of done:
1. On a fixture with an off loop, in ?view=blocks&open=* its e label is bold and ends in 'off', and its value equals /api/loops' error; the word shown equals that goal's `word` in /api/loops for every loop.
2. The computed stroke colour of an off loop's wires equals a holding loop's.
3. The text is at least 11 px and does not collide with a wire (layout rules).
4. The legend row is present.
Files: ergostat/web/static/blocks.js, style.css, tests/test_diagram_rendering.py.
Acceptance tests: a browser test for 1-2 on the fixture.
Budget: 40 net lines.

Milestone: r4-blocks-textbook. Owner items: R4 piece 7. From the owner's list and the design review of 2026-11-22.
