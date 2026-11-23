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

Round 2: main (bea24a23) merged in. The only conflict was in `tests/test_diagram_rendering.py`, where main had added
two tests at the end of the file, just where this branch's acceptance test sits. Both sides were kept (c32deef1). No
code was changed. Ruff is clean. With Playwright under the watchdog:
- the acceptance test passes (rc 0);
- main's `test_the_diagram_has_one_caption_naming_its_type_the_models_purpose_and_its_verdict` passes;
- main's `test_needs_attention_is_three_headed_groups_in_a_fixed_order` fails twice: the 30 s wait for three
  `.side h3.att-head` headings and 'loops off' times out (line 4281). With its loop narrowed for a moment to the home
  page alone (`/`, which never draws the Blocks view or calls `blocksLegend`), it fails the same way, so the failure is
  not in this branch's change. The probe edit was undone and never committed. This branch changes only `bdBody`'s
  subsystem letter, the frame title and `blocksLegend` in `blocks.js`, and none of these reach the side list. I tried to
  run that test on a clean main checkout (`git worktree add --detach /tmp/mainwt main -q && cd /tmp/mainwt && ...`),
  but the command was refused. Comparing with main is left to the factory's rerun on clean main (lesson 13).

After the third `build` failure (rc 5, the browser file skipped for want of Playwright): the merge of main
(c32deef1) was already committed, with no conflict markers left. The branch now pins the legend's 'p×m: outputs ×
inputs (disturbances counted)' with a unit test,
`tests/test_blockdiagram.py::test_a_subsystems_m_counts_every_input_from_outside_it_a_disturbance_included`. For each
closed top-level subsystem in every example, it checks that m equals the number of distinct signals crossing into the
system's frame once the system is opened, and that in some example a disturbance from outside is one of them. That
claim had no non-browser test (lesson 8), and the build step's selection now includes a file that runs without
Playwright. No code outside `tests/` changed. To show it can fail: with disturbance wires into subsystem boxes skipped
for a moment in `blockdiagram.fold`, it failed (coordinator's observer: m 2, not 3). The edit was then undone.
- p is not pinned this way. In image-squeeze, rollout reads 5×3, but 4 distinct signals leave it: p counts each
  port's width, and from reading `fold` (one vector port per destination box), most likely a signal sent to two
  subsystems in two vectors is counted twice; that cause was not checked by a run. "outputs" in the legend holds as
  the wires drawn, not as the distinct signals. Changing how p is counted is outside this gap, so it is left as it
  is and noted here.
- Tests run: `tests/test_blockdiagram.py` (68 passed) and ruff (clean). Refused: `uv run python scripts/affected_tests.py
  -- uv run python -m pytest -q` (run to check the build's selection gives rc 0 without Playwright), and a scratch probe
  written under /tmp. The browser file was not run again this round: the change since round 1 is this unit test alone.

Round 3: main (2f08c24e) merged in (3b299fa1), with conflicts in `blocks.js` and `tests/test_diagram_rendering.py`.
Main had landed blocks-subsystems-classified-c-p in the meantime. Q is gone: a system is now C_name, P_name or a
named block, with the same fn and p×m on the closed block and the open frame. Main's legend has a row defining C_name,
P_name, the named block and "p × m, its p outputs by its m inputs, disturbances counted". How each conflict was
resolved:
- Legend: main's version taken whole. The branch's Q row is dropped, since main's row covers this gap's legend
  acceptance ('×', 'outputs', 'inputs', the letter drawn defined).
- Frame title: main's version, plus this gap's rule. A C or P frame no longer prints its name after the letter,
  because the name is already the letter's subscript. Main drew 'Cfactory factory 1×3'; now it is 'Cfactory 1×3'. A
  named frame still prints its name once, and a cascade's title is unchanged.
- One typeface: kept, because main still makes a closed box's fn bold when p or m > 1 (`blockdiagram.py`, fold), and
  the frame's fn is not. So on main, factory is drawn bold and upright closed but italic when opened. The `bdBody` line
  draws a subsystem's letter unbolded, so it is italic 400 at both levels. Only its comment changed (it named Q). The
  side panel's MathML still sets a vector system's letter bold, as before.
- Tests: both sides kept. The acceptance test now reads C, P or a named block's upright name: the letter drawn must be
  C or P, defined in the legend as `C_name` or `P_name`, or named and defined by 'its name alone'.
- The round-2 unit test `test_a_subsystems_m_counts_every_input_from_outside_it_a_disturbance_included` is removed.
  Main's m also counts disturbances that arise inside a system (on purpose: see its record), so the test's count of
  only the crossing signals no longer holds (alert-triage's alerts: m 2, 1 crossing). Main's own
  `test_every_system_has_the_same_letter_and_p_by_m_closed_and_open` pins m. `tests/test_blockdiagram.py` is now the
  same as main's.
- Net code outside tests: 1 line (`blocks.js`, +3 −2).

Tests run: ruff is clean. `tests/test_blockdiagram.py`: 95 passed. With Playwright under the watchdog, rc 0, 4
passed: the acceptance test, main's `test_a_system_is_drawn_c_p_or_named_with_the_same_p_by_m_closed_and_open`, and
`test_the_requests_group_opens_by_saying_what_a_person_may_do` [waiting, none]. To show the acceptance test can fail
(lesson 9), each fix was undone for a moment. Always printing the frame name failed it ('Cfactoryfactory1×3'), and
dropping `bold: false` failed it ({italic 400, normal 700}). Both edits were undone. Refused: the whole browser file
in the background (`uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python
scripts/named_tests.py tests/test_diagram_rendering.py > /tmp/dr.log 2>&1`), so it was not run this round. That is
left to the merge queue.
