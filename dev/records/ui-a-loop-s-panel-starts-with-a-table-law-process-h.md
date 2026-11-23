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

Round 1, after the factory's `build` step:
- `build` failed with rc 5, but no test failed in it. `scripts/affected_tests.py` picked `tests/test_diagram_rendering.py`, the only test file the branch changed. The build step runs without Playwright, so the whole module skipped at import (line 38) and pytest found nothing to run, which is rc 5 ("1 skipped in 0.84s"). The branch's page code was not exercised at all, and changing it cannot make this step pass.
- No code changed in this round. Making it pass would mean changing `scripts/affected_tests.py` or the build step (treat rc 5 as a pass when only browser files are picked, or install Playwright). That is outside this gap's files (lesson 13), so it belongs in its own gap. The other options were adding an unrelated unit test or weakening the module skip. Both would only hide the problem, so neither was done.
- Bash was refused for every command this round (`git log …`, `git -C /work status --short`). So this note is written but not committed, and no test or ruff was run this round.

Round 1, after the second `build` failure (the same rc 5, "1 skipped"):
- Same cause as before. I read `scripts/affected_tests.py` again: it hands pytest only the changed test files, and here that is `tests/test_diagram_rendering.py`. That file skips at import without Playwright, so every branch whose only changed test file is a browser file gets rc 5. No page code can change that, so I changed no code.
- What is left is outside this gap, in its own gap. Either `affected_tests.py` adds `--with playwright` or treats rc 5 as a pass when it picks only browser files, or `[suites] build` runs with Playwright.
- `git log`/`git diff` ran this round. A later command (`uv run ruff check …` and the named page test with `--offline`) was refused, so neither ruff nor the test was run again.

Round 2:
- What changed: `tests/test_graph_cli_web.py::test_the_loop_answer_carries_what_the_panels_first_table_shows`, a unit test the build can run without Playwright. This follows main's precedent (ab17bb6e, the agents gap with the same rc 5). The build's affected set now has a file pytest collects, so it no longer finds nothing (rc 5). It pins this change's contract rather than something unrelated:
  - `loopTable`'s six row names, in order.
  - The NRMSE measure on the fit row, and "not identified: needs a step of u".
  - The fit in `identRows` is no longer clamped at 0.
  - The image-squeeze `quality-held` answer from `loop.analyse` has every field the rows read: the controller's says/law/block (the tuner), identified, and performance with excursions (count, settling) and saturation.
- Seen to fail under two breaks of `control.js`: the "time off" row renamed, and `Math.max(0, …)` put back on the `identRows` fit. Both were restored, and there is no diff under `ergostat/` this round.
- I first had the clamp check cover all of control.js from `identRows` on. That failed on a `Math.max(0, …)` held-out figure further down (the other form's fit, a line this gap did not write), so the check now covers only `identRows`. That other clamp is left as it is, outside the gap.
- No code outside tests changed this round. The net lines outside tests and docs are still about 40.
- Run: `tests/test_graph_cli_web.py`, whole file, 33 passed. The browser acceptance test, with Playwright under the watchdog, 1 passed (rc 0). Ruff is clean. Not run: the unit suite and the four browser files (left to the merge queue, as the brief says). The earlier `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page` failure, reported in round 1, was not run again.

Round 3 (answering the round-2 review's two blocking findings and its two non-blocking ones):
- Blocking, `control.js` "From X instead" clamp: the line now reads "NRMSE fit N% held out (NRMSE fit, 100% is perfect, below 0 is worse than the mean)", using `pcFit` and `FIT`, with no clamp. A −128% fit now reads −128%. The unit test now also checks all of `processSection` for a clamped fit and for this wording.
- Blocking, a controller's tables took every loop in `n.loops`: `blocks.js` now filters the tables (not the scope) with `own`, the same test `controlBox` uses (`d.controller?.block === block || d.controllers?.includes(block)`). The unit test pins the filter's text. The browser acceptance test now checks that the tuner's panel has exactly one table per loop the tuner holds. Caveat: I have not checked whether any loop in image-squeeze only passes through the tuner's path. If none does, that browser check cannot fail under the break, and only the unit test's source check guards it (lesson 9).
- Non-blocking, "follows −128% held out": unchanged. It is written in `ergostat/control/ident.py`, outside the gap's files. It is a follow-up gap of its own.
- Non-blocking, the unit test pins source text, not behaviour: unchanged in kind. The browser test is the behavioural check. The unit test is there so the build step without Playwright has something to collect.
- About 1 net line more outside tests and docs. The total is still about 41, within the 60 budget.
- Every Bash command was refused this round, so none of this round's work was run or committed:
  - `python3 - <<'EOF' …` (the edit script)
  - `git -C /work diff --stat`
  - Not run: ruff, `tests/test_graph_cli_web.py`, and the browser acceptance test. No break was seen to fail the new checks.
  - The edits are in the working tree, uncommitted.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 17:07).

Stopped on its last attempt by RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 678, in session
    out = agents.session(cfg, role, brief, work, keep=kept)
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 204, in session
    egress(cfg)
    ~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 117, in egress
    _egress(cfg)
    ~~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 124, in _egress
    docker("network", "create", "--internal", NET)
    ~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 106, in docker
    raise RuntimeError(f"docker {args[0]}: {r.stderr.strip()[-300:]}")
RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 17:07).

Its runs failed past their attempts (a dead letter):
- attempt 11: nack queue: the push of e7edd3ff1dfd (gap/ui-a-loop-is-called-r-or-b-only-when-every-link-has) is requested
- attempt 12: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 13: nack exited 1
- attempt 14: nack the run ended with gap/ui-a-loop-s-panel-starts-with-a-table-law-process-h still parked

## Where it stopped

Round 4 (after the Docker park; the gap itself was not at fault):
- Merged main (52c675fee6d7). The only conflict was in `tests/test_graph_cli_web.py`, where main's new test (`test_the_side_panels_charts_say_being_worked_out_never_a_bare_ellipsis`) and this branch's test sat in the same place. Both are kept, unchanged.
- Round 3's edits (the `own` filter in `blocks.js`, the unclamped "From X instead" fit in `control.js`, and the unit test's checks for both) were already committed. This round changed no code.
- Round 3 said no break was seen to fail its new checks. This round checked, one break at a time, each reverted afterwards:
  - `held.filter(own).map(loopTable)` → `held.map(loopTable)`: the unit test fails (the filter check). The browser acceptance test still passes, as round 3 suspected: in image-squeeze no loop only passes through the tuner, so only the unit test's source check guards the filter (lesson 9, stated, not hidden).
  - the processSection fit put back as `Math.max(0, Math.round(o.fit_val * 100))%`: the unit test fails (the clamp check).
- Run after the merge: ruff clean; `tests/test_graph_cli_web.py` 41 passed; with Playwright under the watchdog, the acceptance test and main's `test_no_panel_shows_a_leftover_ellipsis` 2 passed (rc 0). Not run: the unit suite and the four browser files (left to the merge queue).
- Still unchanged and outside the gap: "follows −128% held out" in `ergostat/control/ident.py` (its own follow-up gap).

## Where it stopped

Round 5 (answering the review's two blocking findings):
- Blocking, one loop's failed answer blanked every loop (`blocks.js`, `Promise.all`): each loop's `loopControl` now has its own `.catch`, which marks that loop `failed`. A failed loop gets no table, and its `controlBox` (process panel) or scope and controller box (controller panel) shows its own error, as before this branch. The other loops keep their tables and sections.
- Blocking, the process panel's charts came after its words: `procs` (the identification: validation chart, step response, Bode) now sits right after the tables in `top`, before "What it computes", "In the model" and the items section. The definition's order (table, then charts, then prose) now holds for both panels, as SPEC says, so the definition, record and SPEC were not narrowed.
- Tests: the browser acceptance test now checks the order on proc:service (every `p.what` and `h3` outside the identification follows it). It also makes one of proc:service's loops answer 500, opens the panel again, and checks that the failed loop's box names the error, another loop's box has its sections, and at least one table is left. The unit test pins both changes in `blocks.js`'s source.
- Both breaks were seen to fail the browser test, one at a time, each reverted afterwards: the per-loop `.catch` removed (the wait for the failed loop's error and another loop's sections times out), and `procs` moved back after the items section (the order check fails).
- About 1 net line less outside tests and docs this round (5 added, 6 removed). The total is still about 40, within the 60 budget.
- Run: ruff clean; `tests/test_graph_cli_web.py` 41 passed; with Playwright under the watchdog, the acceptance test and `test_no_panel_shows_a_leftover_ellipsis` 2 passed (rc 0). Not run: the unit suite and the four browser files (left to the merge queue).
- Still outside the gap and unchanged: "follows −128% held out" in `ergostat/control/ident.py`, a follow-up gap of its own.

## Where it stopped

Round 6 (the factory's merge of main, ead497d1f4bc):
- Resolved the conflict in `tests/test_graph_cli_web.py`. Main's new test (`test_every_page_header_links_to_the_diagrams_waiting_for_you_heading`) and this branch's test were in the same place. Both are kept as they were. The merge is committed.
- After the merge the browser acceptance test failed: its `get_by_role("button", name="fit")` now matched six elements. Main brought in a `model-fits` loop, whose blocks have "fit" in their names. The test now clicks `name="Fit", exact=True`, like every other test in the file. No page code changed this round.
- Run: ruff clean; `tests/test_graph_cli_web.py` 43 passed; with Playwright under the watchdog, the acceptance test and `test_no_panel_shows_a_leftover_ellipsis` 2 passed (rc 0). Not run: the unit suite and the four browser files (left to the merge queue).
- Still outside the gap and unchanged: "follows −128% held out" in `ergostat/control/ident.py`, a follow-up gap of its own.

## Where it stopped

Round 7 (answering the merge queue's finding):
- `tests/test_style_tokens.py::test_no_literal_colour_size_radius_or_spacing_outside_the_tokens` failed on this branch's `.bd-math::-webkit-scrollbar-thumb { border-radius: 3px; }`, which is a literal radius. It now uses the `--radius` token (4px). On a 6px bar the two look the same. The line count does not change.
- The scrollbar's `height: 6px` stays. The token test does not count height as spacing, and no token fits a scrollbar's thickness.
- Run: `tests/test_style_tokens.py` failed 1 of 10 before the fix and passed 10 of 10 after it. Ruff is clean. With Playwright under the watchdog, the acceptance test passed (rc 0). Not run: the unit suite and the four browser files (left to the merge queue).
- Still outside the gap and unchanged: "follows −128% held out" in `ergostat/control/ident.py`, a follow-up gap of its own.

## Where it stopped

Round 8 (the factory's merge of main, 1c790d38b71a):
- Resolved the conflict in `tests/test_graph_cli_web.py`. Main's new test (`test_a_process_view_with_no_kinds_is_answered_empty_and_the_page_says_so_over_the_canvas`) and this branch's test were in the same place. Both are kept whole, as they were. The merge is committed (c21f61b5). No page code changed this round.
- Refused this round: a `python3 - <<'EOF'` edit script for the resolution (done with the editor instead), and a `cat >> … <<'EOF'` append to this file followed by `git add`/`git commit` (this note was written with the editor; it may be uncommitted if the next commit is refused too).
- Run: ruff clean; `tests/test_graph_cli_web.py` 45 passed; with Playwright under the watchdog, the acceptance test passed (rc 0). Not run: the unit suite and the four browser files (left to the merge queue).
- Still outside the gap and unchanged: "follows −128% held out" in `ergostat/control/ident.py`, a follow-up gap of its own.
