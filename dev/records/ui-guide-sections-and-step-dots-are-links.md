# ui-guide-sections-and-step-dots-are-links: Guide sections and step dots are links

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q08 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /guide

**The problem:** Section names ('Control: what we control', 'Yours') do nothing; dots are 12 px targets named only by title, with the current step shown only by fill.

**The change:** Section names jump to their first frame. Dots get a 24 px hit area, aria-label 'Step n of 13' and aria-current='step'.

**User stories it serves:** A3, H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
Clicking 'Control: what we control' changes ?frame to that section's first frame; each dot's clickable box is at least 24x24; exactly one dot has aria-current='step'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built (fdf7b844). The change is 11 net lines of code, in `ergostat/web/static/guide.js` and `style.css`.

- **Section names** are now `<a class="g-part" href="/guide?frame=k">` links (through `routeUrl`, so a snapshot gets
  `#/guide?frame=k`). A plain click calls `show(k)` in place, which sets `?frame=k` the same way the dots and arrows do.
  A link was the more reversible choice than a button: middle-click and new-tab work, and it needs no new handler.
- **Dots** are now 24x24 buttons with the 12 px dot drawn inside them by `::before`, so the look is unchanged. Each has
  `aria-label="Step n of 13"`, and `show()` puts `aria-current="step"` on the current dot only. The gap between dots
  in `.g-steps` went from 4 px to 0, because the hit areas already space them.
- **The acceptance test** is `check_guide_steps` in `tests/test_diagram_rendering.py`. It runs inside
  `test_the_guide_draws_every_frame_live_and_in_a_snapshot`, both on the live server and on the offline snapshot. It
  clicks 'Control: what we control' and expects `?frame=` to be that section's first frame (read from
  `ergostat.guide.frames()`). It also checks that all 13 dots are at least 24x24, that their labels are 'Step 1 of 13'
  to 'Step 13 of 13', and that exactly one dot, the current one, has `aria-current='step'`. It passes.
- **Breaks (lesson 9)**, each seen to fail the test, then put back:
  - the link's click not calling `show` (times out waiting for the frame);
  - dots at 12 px (the 12x12 boxes are reported);
  - `aria-current` set on every dot (`[0..12] != [7]`).
- **Runs:**
  - `ruff check ergostat tests scripts` is clean.
  - `tests/test_guide.py`: 6 passed.
- **Full `tests/test_diagram_rendering.py` (serial, under the watchdog): 196 passed, 4 failed, rc 1.** The four
  failing tests:
  - `test_every_view_draws_cleanly_and_in_time[coordinator]`: routing open=* 44 s, bound 20 s.
  - `test_every_view_draws_cleanly_and_in_time[image-squeeze]`: routing open=* 46 s.
  - `test_a_big_tangled_model_lays_out_in_time_and_cleanly`: open=* drawn in 3.7 s, bound 2.5 s.
  - `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`: 'Nothing waiting.' is missing
    from /model after accepting, at line 3325.

  Three of them, run again alone, still fail: coordinator (routing 25 s), the big tangled model, and the equation test.
  So load does not explain them. image-squeeze was not run again. I believe they are unrelated to this gap: none of
  them opens /guide, `guide.js` runs only on /guide, and the CSS changed only `.g-*` rules. But I could not show it on
  main: `git checkout -q main && ...` was refused in this session. Running these four tests on clean main is left to
  the factory (lesson 13). Nothing was changed for them here.
- `origin/main` is absent from the clone and local `main` is this branch's base, so there was nothing to merge.

Round 1, after the build step failed: the `build` step (`scripts/affected_tests.py`) picked
`tests/test_diagram_rendering.py`, the test file this branch changed, and ran it without Playwright. The file skips
as a whole at line 38 (`could not import 'playwright.sync_api'`), so pytest ran nothing and exited rc 5. No test
failed, and no ergostat code is at fault. That file is a browser file and needs `uv run --with playwright==1.63.0`,
as the four browser files do in the merge queue.

- **Nothing changed in the code.** The fix belongs in the factory's build step: either run a changed browser file
  with Playwright, or leave it out of the fast set. That is `scripts/affected_tests.py` or `[suites] build` in
  `dev/factory.toml`, which are outside this gap (lesson 13), so it needs a gap of its own.
- **The other option was to move the acceptance test out of the browser file.** The definition of done asks for it in
  the existing browser files, so I did not take it.
- **Reversibility:** this way no code or test changes. With Playwright, the test passes, as noted above.
