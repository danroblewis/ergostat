# ui-the-blocks-legend-defines-every-symbol-and-a-nam: The Blocks legend defines every symbol, and a name is printed once

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q68 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram Blocks 'How to read it'; subsystem blocks

**The problem:** 'Q' and the '3×1' dimensions are never defined; Q is bold on one level and italic on another; an opened subsystem reads 'Q_service  service'.

**The change:** The legend adds the subsystem symbol in use and 'p×m: outputs × inputs (disturbances counted)'. One typeface for the letter at every level. Drop the repeated plain name beside the symbol.

**User stories it serves:** G6

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796 ?view=blocks the legend contains '×' with the words 'outputs' and 'inputs' and defines the subsystem letter shown; no block contains its system's name twice; the letter's font-style and weight are the same at top level and inside.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built in round 1: 7 net lines in `ergostat/web/static/blocks.js`; the acceptance test is
`tests/test_diagram_rendering.py::test_the_blocks_legend_defines_the_subsystem_letter_and_its_size_and_a_name_is_printed_once`
(software-factory served; `view=blocks` and `view=blocks&open=factory`). Each of the three changes was undone in turn
and the test failed each time: on the style ({italic 400, normal 700}), on the name ('Qfactoryfactory'), and on the
legend (no '×').

Choices made with nobody to ask, the reversible way:
- One typeface: the subsystem letter Q is drawn italic at normal weight everywhere, closed or open, as the frame already
  drew it. Before this, a closed subsystem with more than one input or output drew Q bold and upright. A process
  block's bold P (several stocks) and bold vector signals are unchanged, and so is the side panel's MathML definition,
  which still sets Q bold for a vector system. Only the drawing changes, in one line of `bdBody`.
- The name printed once: an open system's frame title is now Q with the name as its subscript and no plain name after
  it. A cascade's 'inner loop of …' title is unchanged.
- The legend: a new row, shown when a subsystem block or frame is drawn, takes its letter from the graph and defines it,
  with (s) or without, and 'p×m: outputs × inputs (disturbances counted)'. The first row no longer mentions Q, since
  the new row covers it. 'Disturbances counted' holds because every wire into a subsystem box becomes one of its input
  ports (`blockdiagram.py`, `box_port`), a disturbance's included.
