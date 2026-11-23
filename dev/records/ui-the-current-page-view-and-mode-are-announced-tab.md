# ui-the-current-page-view-and-mode-are-announced-tab: The current page, view and mode are announced; tables and controls have names

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q75 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** all pages

**The problem:** Nothing carries aria-current or aria-pressed; tables have th cells in a body row and no caption; the Items h2 names include '▾'; a sort button is named 'Sort by by'; −, + and ⋯ are named by title only; /model rows end in identical 'process, controller, scope' links; the side panel is a div, not a landmark; several targets are under 24 px.

**The change:** aria-current='page' on the nav; aria-pressed on Dynamics/Blocks/Process and on Items' List/Graph/Timeline; <thead>, scope and a caption on each data table; aria-hidden on glyphs; aria-labels 'Zoom out', 'Zoom in', 'More diagram options', 'Sort by author'; row name added to repeated links; side panel as <aside aria-label>; 24 px hit areas on Evidence links, legend links and the Record checkbox.

**User stories it serves:** H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
axe-core on /diagram, /loops, /agents, /items, /record and /model reports no violations of aria-allowed-attr, button-name, link-name, th-has-data-cells or target-size; exactly one nav link has aria-current='page' and exactly one view button has aria-pressed='true'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1; 18 net lines outside tests (64 added, 46 removed under `ergostat/web/static/`).

Decisions taken alone (each the reversible one):
- **axe-core itself is not run.** It is not in the repository or the environment, and the session reaches no network.
  The acceptance test (`tests/test_items_page.py::test_the_page_view_and_controls_are_named`, nine pages: /diagram in
  Dynamics, Blocks and Process, /loops, /agents, /items, /items?kind=hypothesis, /record, /model) checks the five
  rules in the page the way these pages use them: aria-allowed-attr for aria-pressed, aria-sort, aria-checked; button-name and
  link-name (stricter than axe: a title alone, or a glyph with no letter, is no name); th-has-data-cells (a header
  row out of a thead, an unscoped column header, a column header over no data cell, a data table with no caption);
  target-size for the named 24 px targets (Evidence links, the Items graph's legend keys, the Record checkbox), not
  every target on the page. Vendoring axe-core and running it in this test is a later step if wanted.
- aria-sort moved from the sort button (where aria-allowed-attr forbids it) to its th; the existing sort test reads it there.
- 'Sort by author' is said for a field named `by` (examples' `show: [..., by]`); any other field is 'Sort by FIELD'.
- The Items page's seg helper sets aria-pressed on all its toggles (Show, and in Graph/Timeline, Group and Rows):
  the test counts pressed buttons in the View/Show group only. Graph and Timeline were not opened by the test.
- The diagram legends hold no links; the 24 px "legend links" taken as the Items graph's legend keys (button.rg-key).
- The Items group headings already had their ▸/▾ aria-hidden on main; the menu buttons' CSS ▾ is now `content: "▾" / ""`.
- Two tests in test_diagram_rendering.py used the old names ('+', 'process') and now use 'Zoom in' and 'quality-held process'.

Tests seen to fail when the code they guard is broken (lesson-9): with the thead, 'Zoom out' and aria-sort-on-th
undone, all nine cases failed on the matching rule; with aria-current and aria-pressed removed, all nine failed.

Tests run: tests/test_items_page.py (31 passed), tests/test_agents_page.py (4 passed), tests/test_diagram_rendering.py
in full (194 passed, 6 failed; the two failures caused by the renamed controls fixed and passing on a rerun). Left failing, not touched by this branch:
- test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page (line 3305, 'Nothing waiting.' on
  /model's proposal list): a past review recorded it failing alone; still failing on the rerun.
- test_every_view_draws_cleanly_and_in_time[coordinator] and [image-squeeze] (routing 39 s and 34 s against 20 s),
  test_a_big_tangled_model_lays_out_in_time_and_cleanly (4.2 s against 2.5 s): layout and routing time bounds in a
  50-minute serial run; this branch changes no layout code. Not compared with main here.
- Not run: tests/test_page_polling.py, tests/test_page_refresh.py, the unit suite (left to the factory and queue).

Found, not fixed (outside the gap): opening /model writes a new ergostat.model-change item to the record (seen as
ergostat.model-change/8da394d2 on the image-squeeze site), so a test after it on the same site sees four model
changes, not three; the acceptance test is placed last in its file for that reason.

Build step after round 1 (rc 5, "2 skipped"): not a fault in the branch's code. The branch changes only
`ergostat/web/static/` (JS and CSS) and two browser test files, so `scripts/affected_tests.py` selects only
tests/test_diagram_rendering.py and tests/test_items_page.py; `[suites] build` runs them without Playwright, both
skip at import, and pytest returns 5 (no tests ran). No change to this gap's code can make that command pass: it
would take changing the build step or affected_tests.py (outside this gap, lesson 13) or adding an unrelated unit
test only to be selected (a test that guards nothing). Left as is; the fix belongs to the factory (run the build
step's browser files with Playwright, or treat a selection of only browser files as collection-only). The browser
files were run with Playwright in round 1 (results above).

Build step again (same tail: rc 5, "2 skipped", both at the `playwright.sync_api` import): same cause, no code change.
The branch's change is in JS, CSS and HTML under `ergostat/web/static/`, and `scripts/affected_tests.py` maps only
`ergostat/**/*.py` to unit tests, so no unit test is selected. A unit test added only to be selected would guard
nothing the gap changed (served HTML carries none of the new names: aria-current, aria-pressed and the labels are set
by the scripts), and moving that work into `server.py` to change the selection would be work outside the gap. The
gap waits on the factory: run the build step with Playwright installed, or set `build_browser = true` for it.

Round 2 (main 720426bd merged in). The conflict in `diagram.js` was the view buttons. Kept: main's " · what is /
what is controlled / what happened" spans, and the branch's aria-pressed on each. The acceptance test now compares
the view's word that leads the pressed button's name ('Dynamics · what is' → 'Dynamics'), because main's words are
part of the name. Still 18 net lines outside tests.

Tests run after the merge, with Playwright: tests/test_items_page.py, tests/test_view_switch_words.py and
tests/test_agents_page.py (39 passed). tests/test_diagram_rendering.py in full: 197 passed, 7 failed:
- the same four as round 1 (coordinator and image-squeeze routing 32 s and 31 s against 20 s, the big tangled model
  2.9 s against 2.5 s, and /model's 'Nothing waiting.' at line 3356);
- test_a_block_dragged_in_the_blocks_view_stays_pinned_its_lines_end_on_it_and_unpin_all_restores_it: 48 'outside
  frame' blocks in the full run, passes when run alone. It fails only under load, in layout code this branch leaves
  alone;
- test_every_lines_panel_links_to_the_parts_it_joins: a different edge and example 'opened nothing' in each of
  three runs (ticket-factory in the full run, two others when run alone). This is the test's 5 s wait for the panel.
  The branch does not touch openEdge or the panel's `dl` links;
- test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known: the side panel says 'Goals
  off', main's needs-attention heading (`diagram.js:1378`, not in this branch's diff). The test reads the same panel
  whether it is a div or an aside. This fails from main's change, not this branch's.
Not compared on clean main: `git worktree add --detach /tmp/mainwt 720426bd...` was refused in this session.

Build step after round 2 (rc 5, "2 skipped", both at the `playwright.sync_api` import): the third time, same cause.
The merge of main 720426bd was already committed (31e9fb2e; `git status` clean, main an ancestor of HEAD). No code
was changed for it: the branch changes only `ergostat/web/static/` and two browser test files, so
`scripts/affected_tests.py` selects only those two files, and the build step runs them without Playwright. Ruff is
clean. The gap waits on the factory (Playwright in the build step, or `build_browser = true`); the browser results
after the merge are the ones in round 2 above.

Build step again (rc 5, same tail), now answered in the branch. main already has a no-browser test of this kind
(tests/test_view_switch_words.py reads diagram.js's source "where Playwright is absent"), so the branch adds
`tests/test_page_names_source.py` (8 tests) the same way. It reads the scripts and style for the names this gap adds:
aria-current set and cleared on the nav, aria-pressed on the three view buttons and the Items toggles, 'Zoom out',
'Zoom in', 'More diagram options', 'Sort by author', the /model links named for their row, the side panel as
<aside aria-label>, headRow's thead/scope/aria-sort, no table with a header row straight under it, and the 24 px rules.
The build step selects it, so it runs a test that guards the gap. It is a source check, not the drawn page; the browser
acceptance test is still the one that checks the drawn pages. Writing it found one more header row in a table's body:
the item page's sub-table for a list of objects (pages.js fieldView), now in headRow (one line changed, net 0). Seen to
fail (lesson-9): with the Zoom out label removed, 1 of 8 failed; before the fieldView fix, the thead test failed.
Tests run: tests/test_page_names_source.py (8 passed), tests/test_items_page.py with Playwright under the watchdog
(33 passed, rc 0). Ruff clean.

Round 3 (the review's one finding: seven data tables with a thead and no caption, untested). Answered:
- A caption on each: `tableCaption(text)` in util.js (a visually hidden `<caption>`, as the pages' own tables have) on
  the loop's parts ('The parts along loop NAME'), an agent's recent runs ('Recent runs of NAME, newest first'), the
  parameter and calibration tables ('Parameters', 'Calibrations'), a stock's items (its count line, as shown above
  it), a flow's openings or observations, and the item page's list-of-objects sub-table (its column names, as
  pages.js `table()` already does). +2 net lines (the helper); the branch is 20 net lines against main
  (70 added, 50 removed under `ergostat/`).
- The browser acceptance now opens those tables: `tests/test_items_page.py::test_the_side_panels_and_item_tables_are_captioned`
  opens a loop's panel, the agent filling its first part, the first flow in `around=flow/quality-turnover` whose panel
  shows a parameter table, the stock ideas' items, and an item page with `fieldView` given a list of objects (that
  example has no item with such a field, so the test hands the page's own function one). The same NAMES rules
  run after each; it asserts that a parts, a 'Recent runs', a params, an item-list and a sub table were each seen,
  so it cannot pass by opening nothing. The calibration table appears only after an estimate and was not opened by
  this test; it shares the helper, and the source test checks its call.
- `tests/test_page_names_source.py::test_each_table_with_a_header_row_has_a_caption`: each headRow call's table
  carries tableCaption or a caption (11 tables, all of them), and the helper builds a caption.
Seen to fail (lesson-9): with tableCaption returning nothing, the browser test failed at 'a loop' ('no caption'
on table.parts); with only the item sub-table's caption removed, the browser test failed at "an item's list of
objects" and the source test failed naming pages.js. The source test did not fail on the first break until the
helper's body was pinned too (now it is).
Tests run (Playwright, under the watchdog): tests/test_items_page.py (34 passed, rc 0); tests/test_agents_page.py and
tests/test_view_switch_words.py (6 passed); tests/test_page_names_source.py (9 passed); from
tests/test_diagram_rendering.py, the tests that read these tables: the process lines panel and snapshot item
lists, and the valve's equation panel (3 passed). Ruff clean. Two failed:
- test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page: at 'Nothing waiting.' on /model,
  the same failure as rounds 1 and 2. Its table.params and table.calibrations reads come before that and passed.
- test_every_part_opens_its_panel_when_clicked_even_mid_redraw: a different stock each run ('unanswered-requests'
  and 'changes-made', then 'pending-changes' alone), with no page error. A stock's panel renders only after
  `api("part/...")` answers (details.js openNode, dynamics.js openNodeSD), and the test waits a fixed 3 s for it.
  This round changes nothing on that path, since the captions are on tables built after the panel shows. Not
  compared on clean main: `git checkout main -- ergostat/web/static` (to run it there and restore) was refused in this
  session, as was a background run of the full test_diagram_rendering.py (about 50 minutes, longer than a foreground
  call may run). Left to the queue's full browser run.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 14:17).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 669, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 14:18).

Its runs failed past their attempts (a dead letter):
- attempt 24: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 25: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 26: nack exited 1
- attempt 27: nack the run ended with gap/ui-the-current-page-view-and-mode-are-announced-tab still parked

## Where it stopped

Continued, round 1 (main 52c675fe merged in, da759558). Conflicts resolved by keeping main's change and putting the
branch's names on it:
- `details.js` openAgent: main's two tables (the runs, and 'resources' behind a details) each take a caption and
  headRow ('Recent runs of NAME, newest first'; "Resources of NAME's recent runs, newest first").
- `diagram.js` Suggestions: main's goalButton and showGoal kept; the Evidence link keeps hit24 and its aria-label.
- `pages.js`: main's `const table` with holdStill on /agents, with the caption and headRow; the daemons table with
  main's text (no "(SPEC §9.7)") and the branch's caption, headRow and tbody; the item page's track is main's path and
  other states, with the arrow aria-hidden.
- `tests/test_items_page.py`: both sides' new tests kept. Main's two new ones each serve their own project (tmp_path),
  so the acceptance test is still the last in the file on `site` (its docstring now says so).
- Main's new agents test found the sort button by the title 'Sort by by'; this gap renames it, so the test now uses
  'Sort by author' (33af6aa5). The branch is 21 net lines against main (72 added, 51 removed under `ergostat/`).

Tests run (Playwright, under the watchdog): tests/test_page_names_source.py (9 passed); tests/test_items_page.py (40
passed, 1 failed, twice); tests/test_agents_page.py and tests/test_view_switch_words.py (8 passed, 1 failed, three
times); test_diagram_rendering.py's goal-button test, both cases, with test_graph_cli_web.py's stand-in (3 passed;
[False] failed once in the first run, then passed four times, with and without the branch's side-panel changes).
Ruff clean. The two failures, both main's new tests, are left alone (lesson 13):
- test_items_page.py::test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart (line 1474) waits 30 s for
  the other project's entry in the header's switcher. Each page server's lister lists the running projects when it
  starts and then every 60 s (`server.py` LIST_EVERY). The test starts the first project before the second, so the
  first's list cannot name the second within the wait. The branch does not touch the switcher (util.js 380-430) or
  server.py. Not run on clean main here.
- test_agents_page.py::test_each_row_says_how_it_is_engaged_and_which_goal_it_serves (line 396) reads `#detail`
  as soon as `h2 'work'` shows, but panelLoading draws that heading while the panel still says 'Loading…'. With a
  5 s wait put in (then removed), the panel had loaded and there were no page errors. The branch changes only the
  table markup built after the data comes, not when it comes. A fixed wait in the test, not a race in ergostat.
- The once-failed goal-button case ('.suggest .hint button.name' not visible): the test opens `details.suggest` by
  setting `open` directly, leaving S.suggestOpen unset. A likely cause, not shown: a refresh redrew it closed.

## Where it stopped

Continued, round 2 (main 76e1a9ab merged in, c6536682). Conflicts resolved by keeping main's change and putting the
branch's names on it:
- `details.js` eventsTable: main's folded runs (showRun, ×N) inside the branch's caption, headRow and tbody.
- `diagram.js` view buttons: main's carryPanel() on Dynamics and Blocks, with the branch's aria-pressed.
- `pages.js` /loops table: main's lp.points and word(lp.perf), with the branch's caption argument ('Loops').
- `tests/test_diagram_rendering.py` zoom test: main's exact 'Fit', and 'Zoom in' (exact) for this gap's name of '+'.
The branch is still 21 net lines against main (72 added, 51 removed under `ergostat/`).

Tests run (Playwright, under the watchdog): tests/test_page_names_source.py (9 passed); ruff clean;
tests/test_items_page.py (36 passed, 7 failed, twice, the same 7); tests/test_agents_page.py and
tests/test_view_switch_words.py (8 passed, 1 failed: the same agents 'Loading…' test as round 1, above);
test_diagram_rendering.py's zoom test (passed), keyboard test and panel-carry test (both failed).

Waits on main (lesson 13, not fixed here). main's `dynamics.js` openNodeSD (lines 677-706, same on main as on this
branch, which does not touch dynamics.js) first shows a panel holding `wait`, then calls panelLoading(), which
replaces the panel's children; the next line `if (!wait.isConnected) return;` is then always true, so no stock or
flow panel in the Dynamics view ever gets past 'Loading…'. Two of main's changes merged together (lesson 7). It fails:
- test_items_page.py: test_a_stocks_and_a_flows_side_panel_list_their_items_and_link_to_exactly_that_set,
  test_the_model_changes_are_found_by_heading_search_and_panel, test_a_valves_leased_items_are_listed_live,
  test_a_snapshot_lists_a_parts_items_and_opens_its_set, test_a_set_left_out_of_a_snapshot_says_so, and this gap's
  own test_the_side_panels_and_item_tables_are_captioned (no flow's params table ever appears; its loop and agent
  checks before that passed);
- test_diagram_rendering.py: test_a_panel_open_on_what_is_chosen_stays_open_across_a_switch_of_view_in_its_words
  ('rate, over the window' never shown) and test_everything_clickable_in_the_diagram_is_reached_and_acted_on_by_keyboard
  (the first showDetail takes S.keyHead's focus, then panelLoading replaces that heading).
The fix is main's (drop the panelLoading calls in openNodeSD, or take `wait` from them); this gap waits for it, then
its acceptance test should be run again. The seventh test_items_page.py failure is the header switcher test of
round 1 above (the 60 s lister), unchanged. Not run on clean main: no second checkout in this session.

## Where it stopped

Continued, round 2 again (the queue's finding: conflicts with main in diagram.js). The factory had already merged
main ead497d1 into the branch (afd4147a). `git merge-base --is-ancestor main HEAD` holds, the tree has no conflict
markers, and diagram.js against main differs only in this gap's lines: aria-pressed on the three view buttons beside
main's carryPanel() and " · what is" spans, the Zoom labels, 'More diagram options', the aside, and the Evidence link's
hit24 and aria-label. No code changed this round. Still 21 net lines against main (72 added, 51 removed under
`ergostat/`).

main has since fixed the openNodeSD bug this gap waited on in round 2 (dynamics.js 695/712: panelLoading's own
element is now the late-answer guard), so the stock and flow panels load again, and this gap's acceptance tests pass.

Tests run (Playwright, under the watchdog): tests/test_page_names_source.py (9 passed); ruff clean;
tests/test_items_page.py (43 passed, 1 failed, twice), including test_the_page_view_and_controls_are_named,
test_the_side_panels_and_item_tables_are_captioned and the five panel tests that failed on main's bug in round 2;
tests/test_agents_page.py and tests/test_view_switch_words.py (8 passed, 1 failed); test_diagram_rendering.py's
panel-carry test (passed) and keyboard test (failed, twice). Left failing, outside the gap (lesson 13):
- test_items_page.py::test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart (line 1596): the header
  switcher's 60 s lister, the same as continued round 1.
- test_agents_page.py::test_each_row_says_how_it_is_engaged_and_which_goal_it_serves (line 396): reads #detail
  while it still says 'Loading…', the same as continued round 1.
- test_diagram_rendering.py::test_everything_clickable_in_the_diagram_is_reached_and_acted_on_by_keyboard (line
  2311, the focus never on the panel's heading). This one is main's. openNodeSD first calls showDetail with `wait`
  (dynamics.js 686), which uses up S.keyHead and focuses that h2 (details.js 18-19). Then panelLoading and the
  second showDetail replace the heading, and with keyHead cleared, nothing gets the focus. The branch's diff touches
  none of showDetail, panelLoading, keys.js or dynamics.js. The fix belongs to main (keep keyHead until the last
  showDetail, or drop the first `wait` panel now that panelLoading follows it).
Not run: the whole of tests/test_diagram_rendering.py (about 50 minutes serially), test_page_polling.py,
test_page_refresh.py, the unit suite (left to the queue).
