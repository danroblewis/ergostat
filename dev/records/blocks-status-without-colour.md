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

## Where it stopped

Built, 32 net lines (blocks.js +43 −13, style.css +2). Acceptance test:
`tests/test_diagram_rendering.py::test_a_loops_state_is_printed_on_its_error_in_its_word_bold_when_off_and_never_by_colour`
(FOUR_GOALS, one goal of each word, `?view=blocks&open=*`): items 1 to 4, for every loop. Seen to fail with the bold
rule removed (weight 400 on the off loop) and with the off loop's wires stroked red (item 2).

Choices made without an answer (each reversible):
- Only the value and the word are bold (`.bd-state.bd-off`), not the italic e: a bold e is the vector notation. The
  weight is 600, DESIGN's second weight, not 700.
- When e's subscript, value and word do not fit the stretch the label sits on (ELK puts the controller 46 px after
  the junction, so a long loop name never fit), the label drops the subscript (`e = −20 off`, as the definition
  writes it) and, if that still does not fit, goes above or below the junction. Nothing in the layout changes.
- An open loop with no error line out of its junction (its return broken: FOUR_GOALS' disk-cleaned-nightly) gets
  its label by the junction anyway, `e open`. An open loop with no junction at all has nowhere to say it.
- A state that changes while the diagram does not draws it again (no new layout), compared through `lay.states`.
- docs/DESIGN.md's block-view sentence "the loop's lines take its status colour" was stale against decision 2 and
  now says what is drawn.

Not run here: the whole browser file, which does not finish inside one 10-minute command here. Of the files I ran,
two failures are not this gap's (lesson 13), and both are in parts this change leaves alone:
- `test_the_control_view_draws_every_example_cleanly_as_a_block_diagram[autoscaler]`: `view=blocks&system=rescales`
  is never drawn because the server's graph for it has 0 nodes ("No control system here"). The graph is built on
  the server, and this change touches no Python.
- `test_blocks_crossings_hop_dots_only_at_takeoffs_slashes_clear_and_a_drag_and_the_export_keep_them`:
  `get_by_role("button", name="fit")` is not exact, so it also matches software-factory's model-fits parts by their
  aria-labels (strict mode violation). This change does not set aria-labels.
- `test_sensors_are_blocks_with_what_they_read_and_no_part_has_a_tooltip`, 21 of 22 examples: a `title` tooltip
  ("Drawn alike here with B27 …") in `view=dynamics`. That is the Dynamics view, which this change does not draw.

The factory's build step (`[suites] build`, round 1) came back rc 5. That is the selector, not this change: of the
five changed files, `scripts/affected_tests.py` picks only `tests/test_diagram_rendering.py`, a Playwright file whose
module-level `importorskip` skips the whole file when Playwright is absent. The build runs without Playwright, so
pytest collects no tests and exits 5 ("1 skipped"). Any gap whose only changed test file is a browser file gets the
same result. No code here can change that without editing a test or the factory's selector, both outside this gap
(lesson 13). The fix belongs in its own gap: for example, affected_tests.py treating "only browser files, all
skipped" as collect-only, or the build running them with Playwright. With Playwright, the acceptance test passed
after the build failure: `scripts/suite_watch.py -- uv run --with playwright==1.63.0 python scripts/named_tests.py
tests/test_diagram_rendering.py::test_a_loops_state_is_printed_on_its_error_in_its_word_bold_when_off_and_never_by_colour`
gave 1 passed, rc 0.

Round 1, after the build's second rc 5: the change now has a test the build can run without a browser,
`tests/test_style_tokens.py::test_a_blocks_loop_state_is_bold_when_off_and_never_a_colour`. It checks that
blocks.js marks the server's `off` word with `.bd-off`, that the off rule is weight 600, and that no rule naming
`.bd-state` or `.bd-off` sets a colour, fill, stroke, background or opacity. It is the stylesheet half of item 2; the
computed stroke in the browser stays in the acceptance test. It was seen to fail with `fill: var(--accent)` added to
the off rule. The selector now picks this file as well, so the build collects and runs it (12 passed here).
