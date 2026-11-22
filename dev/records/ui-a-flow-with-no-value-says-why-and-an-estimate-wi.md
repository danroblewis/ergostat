# ui-a-flow-with-no-value-says-why-and-an-estimate-wi: A flow with no value says why, and an estimate with no basis says so

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q79 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram Dynamics; flow panel

**The problem:** regressions, fixes, shipped and asks show a bare '–' on a live diagram; rates keep a value with nothing in flight; 'work-time 40m ± 2d' and 'Nothing says the value written is wrong' beside 0.404 ± 0.116 against a declared 2.

**The change:** A flow that did not move in the window shows '0' with 'no movement in 33m' in its panel; one that is not measured shows 'not measured'. An interval wider than ten times its estimate prints 'not enough record yet'. When the declared value lies outside the interval say 'the record so far rejects 2 but cannot yet settle a value'.

**User stories it serves:** B5, C6

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796 ?system=product no flow label is a bare '–'; the churn panel does not contain 'Nothing says the value written is wrong' while the declared value is outside the estimate ± 3σ; no panel shows an interval more than ten times its estimate.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built (round 1), about 26 net lines outside tests: `ergostat/web/static/dynamics.js`, `ergostat/web/static/equations.js`,
and one field (`recorded`) added to `/api/status` in `ergostat/web/server.py`. Acceptance test:
`tests/test_diagram_rendering.py::test_a_flow_with_no_value_says_why_and_an_estimate_with_no_basis_says_so`.

Choices made with nobody to ask (each the more reversible one):
- The wording is changed where the page draws it, not in `ergostat/numbers/` (the Files list names only `ergostat/web/`):
  the calibration table replaces "Nothing says the value written is wrong" with "the record so far rejects <declared>
  but cannot yet settle a value" when the declared value lies outside the estimate ± 3σ. The server's own text (CLI,
  the Model page's "Estimates not proposed" list) still says the old words; changing it there is a gap of its own.
- "An interval wider than ten times its estimate" is read as the whole interval (2σ) against |estimate|, the stricter
  reading, so the acceptance line holds under the other reading (σ > 10 × estimate) too.
- A flow whose rate is null (no sensor reading, no valve, no declared rate) is "not measured" on its label and in its
  panel; a rate of 0 that was not declared says "0 …: no movement in <span>", the span the shorter of the window and
  the time actually recorded (so a 33-minute record says 33m, not 24h), and "nothing recorded yet" when nothing is.
- "Rates keep a value with nothing in flight" is answered only as far as the change says (0 and how long nothing moved);
  how the snapshot averages a rate over the window is unchanged.
- The Blocks panel's identified-model intervals (`control.js` pmText) are not changed: the gap's pages are Dynamics and
  its flow panel, and the two diagrams stay separate.

Each of four breaks was seen to fail the acceptance test: the label back to '–'; the panel's zero rate without "no
movement"; the rejection wording off (3σ → 30σ); the wide-interval rule off (10 → 1000).

Not caused by this branch: `tests/test_diagram_rendering.py::test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`
fails at its last line (`"Nothing waiting." in` the /model page, drawn by `pages.js`, which this branch does not touch).
It failed alone, and still failed with every change of this branch except `dynamics.js` undone. `dynamics.js` changes
only the Dynamics label and panels, not the /model page. It was not run on main: `git checkout main -- ergostat/web`
was refused. Also refused: running the whole of `tests/test_diagram_rendering.py` in the background.

After the factory's `build` step: it failed with rc 5 because nothing ran. Its only selected file,
`tests/test_diagram_rendering.py`, is skipped without Playwright, and `server.py` has no `tests/test_server.py`.
No test had failed. The `recorded` field added to `/api/status` now has a unit check in
`tests/test_graph_cli_web.py::test_the_web_api_serves_what_the_cli_shows` (0 ≤ recorded ≤ window). It was seen to fail
(KeyError) with the field removed. That file passes (32), and ruff is clean.
