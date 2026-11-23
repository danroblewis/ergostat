# ui-off-in-a-chart-is-a-mark-as-well-as-a-colour: 'Off' in a chart is a mark as well as a colour

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q76 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** loop evidence scope charts; /item lifecycle; /agents tier arrows

**The problem:** Off periods in the y/u/e charts are a pale pink (light) or maroon (dark) band keyed only by the text 'Red: off'; tier arrows and count arrows are 1.6:1.

**The change:** Hatch the off bands and label them 'off' on the time axis; the key is a hatched swatch labelled 'off'. Raise arrows and Guide dot borders to at least 3:1.

**User stories it serves:** H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
The scope's off bands have a pattern fill; the legend contains a swatch element with the same pattern and the word 'off', and no text 'Red: off'; computed contrast of tier arrows against the background ≥ 3:1 in both themes.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1. 33 net lines of code (charts.js +32, style.css +1).

- One `offHatch()` in `charts.js` makes the off fill: `--bad` stripes over `--bad-wash`. It draws the y, u and e bands and also fills the key's swatch (`canvas.off-key`, next to the word "off"), so the swatch and the bands share one pattern. "Red: off" is gone. The e chart, which carries the time axis, labels each off stretch wide enough to hold the word "off" at its foot.
- Arrows: the only arrows found at 1.6:1 are `.arrow` (the /item lifecycle track and the /items kind states). They now use `--muted`, as do the Guide dots' borders. The /agents ladder line has had no tier arrows since 8ba06f6b; its "most general → most specific" text was already `--muted` (5.2:1). So "tier arrows" was read as `.arrow`. This is the reversible reading: one CSS line.
- Test: `tests/test_diagram_rendering.py::test_off_in_the_scope_is_hatched_labelled_and_keyed_and_the_arrows_read_in_both_themes`, run in light and dark. I broke each part on its own and saw the test fail each time: the bands back to the plain wash, the "off" label removed, the key back to "Red: off", `.arrow` back to `--line-strong` (1.63:1), and the dot borders back to `--line-strong`. Light failed first in the last two breaks, so dark was not seen to fail alone.
- Not run: the whole of `tests/test_diagram_rendering.py`. Serially it ran past the 10-minute foreground cap and was stopped, and a background run was refused. Run and passing: the new test plus `test_charts_draw_beside_the_model_with_one_cursor_and_in_a_snapshot`, `test_the_guide_draws_every_frame_live_and_in_a_snapshot` and `test_an_items_page_shows_each_fields_history_and_a_session_folded_from_its_transcript`; all of `tests/test_items_page.py` (21 passed); ruff. No screenshot was looked at: the file tools could not read `/tmp`.

### After the factory's build step (round 1)

The `build` step failed with rc 5, and the cause is not this branch's code. `affected_tests` picked `tests/test_diagram_rendering.py` because `charts.js` changed, but it ran that file without Playwright. The file skips at module level (line 38, `could not import 'playwright.sync_api'`), so pytest collected nothing: "1 skipped", rc 5. No test failed. The code has nothing to fix for this. The step needs to run that file with `--with playwright==1.63.0`, or count an import skip as "not run" rather than as a failure. That fix is in the factory's build step, outside this gap (lesson 13), so it is not made here. I could not rerun anything this session because every shell command was refused, including the commit of this note.

### After the factory's build step, again (round 1)

The build step's only test file was `tests/test_diagram_rendering.py`, which skips as a whole without Playwright, so pytest ran nothing (rc 5). The arrow and Guide-dot contrast part of the acceptance is a stylesheet fact, so it now also has a unit test that needs no browser: `tests/test_style_tokens.py::test_the_arrows_and_guide_dot_borders_stand_3_to_1_on_the_paper_in_both_themes`. It reads the `.arrow` colour token and the `.g-dot` border token and checks each against `--bg` in the light and dark token blocks. The build step now selects this file too, so it runs real tests. I broke each part on its own and saw the test fail: `.arrow` back to `--line-strong` (light 1.63, dark 1.75), and the `.g-dot` border back to `--line-strong` (the same ratios). `tests/test_style_tokens.py`: 6 passed. Ruff is clean. No code outside `tests/` changed in this step. The browser test still runs only where Playwright is present.

### Round 2: main merged (ead497d1)

The merge conflicted in three files. All three are resolved, keeping both sides:

- `style.css`: main moved the Guide dot into a 24px target and now draws the 12px dot as `.g-dot::before`, bordered with `--line-strong` (1.63:1). The branch kept main's structure and changed only that border to `--muted`. The `.arrow` line is unchanged. Net code is still 33 lines (charts.js +32, style.css +1).
- `tests/test_style_tokens.py`: main's three new tests are kept. The branch's contrast test now reads the `.g-dot::before` border.
- `tests/test_diagram_rendering.py`: main's `off_for`, `goal_named` and suggestion tests are kept beside the branch's test. The branch's test now reads the dot's computed border from `::before`.

Break check: I set `.g-dot::before` back to `--line-strong`, and both tests failed. The unit test reported light 1.63 and dark 1.75. The browser test failed on light (1.63). I then restored the line.

Run after the merge: ruff clean. `tests/test_style_tokens.py`: 11 passed. With Playwright under the watchdog, these passed: `test_off_in_the_scope_is_hatched_labelled_and_keyed_and_the_arrows_read_in_both_themes` and `test_the_guide_draws_every_frame_live_and_in_a_snapshot`. `tests/test_items_page.py` had 32 passed and 1 failed.

The failure is `tests/test_items_page.py::test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`. It times out at line 1453 and fails the same way alone. That line waits for the other project's entry in the header's `#project` switcher. This branch does not touch that test, the header or the switcher (its diff is `charts.js`, two lines of `style.css` and tests), so I think it is unrelated. It is reported, not fixed (lesson 13). I could not run it on clean main: `git worktree add --detach /tmp/mainwt main` was refused.
