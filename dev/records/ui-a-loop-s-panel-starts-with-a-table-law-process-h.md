# ui-a-loop-s-panel-starts-with-a-table-law-process-h: A loop's panel starts with a table: law, process, held-out fit, performance

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q69 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** controller and process panels (Blocks)

**The problem:** The law follows prose and the performance figures; the process line is near the bottom; the fit reads 'Fit: 0% of the record held out, of the 0% its noise allows' and 'follows −128% held out' with the measure undefined; the quality-held panel ends with a paragraph about small-images; the matrix is cut at the panel's edge.

**The change:** First: a table of law / process model with ±σ (or 'not identified: needs a step of u') / fit on held-out data ('NRMSE fit, 100% is perfect, below 0 is worse than the mean') for estimation and validation / time off / settling / saturation. Then the charts, then prose, with the step-test paragraph behind 'how it is sized'. Only this loop's text. The matrix scrolls sideways inside the panel; each <math> has alttext.

**User stories it serves:** G7

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8793 clicking C_tuner: the panel's first table precedes any <p> and has rows named law, process, held-out fit, time off, settling, saturation; the panel does not contain 'small-images'; the fit row names its measure; no math element's right edge exceeds the panel's.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1, built. About 40 net lines outside tests and docs, in `ergostat/web/static/{control.js,blocks.js,style.css}`. SPEC §(loop control) and MODEL-TOOLS (identification, Where) each have a sentence on the table.

What was built:
- `loopTable` (control.js) sits first in a controller's (C) panel and in a process block's (P) panel, one table for each of the block's loops that has one process. Its rows are law, process (K, τ, θ each ± σ, or "not identified: needs a step of u"), held-out fit ("estimation X%, validation Y% (NRMSE fit, 100% is perfect, below 0 is worse than the mean)", no longer clamped at 0), time off, settling and saturation. A row with nothing to show reads "–".
- A controller's scope charts and its closed-loop section follow the table. The block's words (what it computes, in the model) come after them.
- The process panel's "fit" row in the identification list names NRMSE too.
- A step test's reason (its sizing) is behind a "how it is sized" disclosure.
- Only this loop's text: a process block leaves out its loops with no one process (`why`) when it has others. On image-squeeze the service process lost the small-images paragraph this way. A process with only such loops still shows them.
- Each `<math>` gets `alttext`, its own text. `.bd-math` already scrolled sideways (`overflow-x: auto`). It now has an always-drawn thin WebKit scrollbar, because overlay scrollbars hide on macOS, which is the likely reason the matrix looked cut.

Choices made without anyone to ask (each the more reversible one):
- **Where 'small-images' came from.** C_tuner's own loops in the unrun example are only quality-held, so its panel never had 'small-images' here. The small-images paragraph was in the service process panel, so that is where it was removed. The running demo on :8793 was not looked at. Text from its record (for example a step-test reason naming small-images) may differ.
- **Controllers keep every loop.** I first filtered a controller's loops to "the loops it holds" and then dropped the filter. The tuner's only loop is its own, so for it the filter changed nothing. For a block whose loops have no one process (the researcher), it would have blanked the scope.
- **"follows −128% held out" is unchanged.** It is a `why` reason written in `ergostat/control/ident.py`, outside the files this gap may touch. The table above it now names the measure, but the sentence itself does not. Changing it is a one-line follow-up in its own gap.
- **"No math right edge past the panel's" already held.** The `<math>` box is as wide as `.bd-math`, which scrolls. So the test also narrows the panel to 300 px and checks that each wider `<math>` sits in a box that scrolls sideways inside the panel.
- **No on-screen check of the scrollbar.** Its look on macOS was not checked (no mac here, and headless Chromium hides scrollbars).

Tests:
- New: `tests/test_diagram_rendering.py::test_a_loops_controller_panel_starts_with_its_table_and_its_math_stays_inside` passes. It was seen to fail under five breaks:
  - the table moved after the prose
  - the fit row without its measure
  - the process panel showing every loop (small-images back)
  - no alttext
  - no sideways scroll on `.bd-math`
- `tests/test_diagram_rendering.py`, whole file, serially under the watchdog: 200 passed, 1 failed. The failure is `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`, and it failed again when rerun alone. Its failing assertion is the Model page's "Nothing waiting." after a calibration is accepted. That comes from `pages.js` and the numbers API, which this branch does not touch. My attempt to run it on main's page code (`git checkout main -- ergostat/web/static`) was refused, so it is not proven to fail on main. Reported, not fixed (lesson 13).
- Not run: `test_items_page.py`, `test_page_polling.py`, `test_page_refresh.py` (they don't cover these panels) and the unit suite. Ruff is clean. There is no remote, so there was no origin/main to merge; `main` is the branch's base.
