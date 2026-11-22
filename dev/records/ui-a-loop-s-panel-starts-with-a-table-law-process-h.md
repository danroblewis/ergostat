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
