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

Tests run: the acceptance test passes, and ruff is clean. The whole of `tests/test_diagram_rendering.py` ran serially
under the watchdog: 197 passed, 4 failed, rc 1, none skipped. None of the four failures draws the Blocks view:
- `test_every_view_draws_cleanly_and_in_time[coordinator]` and `[image-squeeze]`: the Dynamics view with `open=*` took
  longer to route than the time limit allows (44 s and 38 s; the limit is 20 s).
- `test_a_big_tangled_model_lays_out_in_time_and_cleanly`: `open=*` took 3324 ms to draw (the limit is 2500 ms).
- `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`: a `view=dynamics` page and /model's
  list of proposals. An earlier review (ui-open-frames…-1) recorded this one failing too.
This change touches only the Blocks drawing (`bdBody` for subsystems, frame titles) and `blocksLegend`, which these
four never reach. I did not run them on clean main to compare: that is left to the factory's rerun on main. I did not
run the other three browser files or the unit suite: they are left to the merge queue, as the brief says.

After the factory's `build` step: it failed with rc 5, and no test failed. `scripts/affected_tests.py` picks only
`tests/test_diagram_rendering.py` (the one test file the branch changes; `blocks.js` has no `tests/test_<module>.py`).
The build step runs that file without Playwright, so pytest skips the module at import (`could not import
'playwright.sync_api'`) and reports that no tests ran. No code was changed for this, because nothing in the branch's
code fails. The fault is in how the build step handles a branch whose only test file is a browser file, and that fix
belongs in its own gap. One option is for affected_tests to fall back to `--collect-only` or the unit suite when every
selected file is a browser file. Another is for the build step to install Playwright. This gap waits for that fix, or
for the factory to run this file with Playwright, as `[suites] build_browser` does.

The `build` step ran again and failed the same way: rc 5, `1 skipped` (`could not import 'playwright.sync_api'`), no
test failed. Again no code was changed. Nothing in the branch fails, and getting rc 0 would mean either changing
`scripts/affected_tests.py` (outside this gap, lesson 13) or adding a unit test only to give the build step something
to collect, which would test nothing the change touches (lesson 9). Bash was refused in this session (`git -C /work
status --short`, and a `git log`/`sed` read before it), so this note could not be committed and no test was run.
