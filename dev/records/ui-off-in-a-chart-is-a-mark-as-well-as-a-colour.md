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
