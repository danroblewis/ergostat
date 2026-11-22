# ui-no-leftover-in-a-panel: No leftover '…' in a panel

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q04 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side panel (system panel, stock panel, loop panel)

**The problem:** The system panel shows a lone '…' under its title; the loop panel shows 'When it drives the behaviour …' for good; both read as a stuck load.

**The change:** Show the description, or nothing. While a value is being worked out say 'being worked out'; when it cannot be, say why ('no loop is dominant in this window').

**User stories it serves:** A4, G4

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
After 10 s on :8796, clicking the product box, the users stock and marker R2: no element in the side panel has text equal to '…' or ending in ' …'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built. The '…' came from the placeholder of the four side-panel charts in `ergostat/web/static/charts.js`
(`causesStrip`: stock and flow panels; `moduleCharts`: the system panel; `loopDominance`: the feedback loop panel;
`loopScope`: a goal's loop panel). Each now says "being worked out" (one `working()` helper) until its answer
replaces it. The loop panel's "When it drives the behaviour" used to go blank when `/api/dominance` failed or the model
could not be read; it now says why it is not worked out. Its other cases already said why (not scored, a score of 0
throughout, no loop named as dominant at a stock). 9 net lines in `charts.js`.

Choice made alone (the most reversible): `loopScope` (a goal's loop panel, in Blocks too) is changed with the
others because it uses the same placeholder. Truncation ellipses inside drawn labels (`dynamics.js`, `diagram.js`) are
not panel text and are left alone.

Test: `tests/test_diagram_rendering.py::test_no_panel_shows_a_leftover_ellipsis` (software-factory served from a copy
with its model not run, so no port 8796 is needed; 10 s on the page, then the product box, the users stock and marker
R2, each panel checked every 250 ms for 6 s). Before the fix it failed with the product panel's lone '…' at every
look. `test_a_closed_systems_panel_charts_its_measures` now also counts "being worked out" as not answered.

Runs (in the container, serial, under the watchdog): ruff clean; the new test and the closed-system test pass; the
whole `tests/test_diagram_rendering.py` ran rc 1, 196 passed and 5 failed (52 min). Run again alone:
`test_pages_are_ordinary_links_opened_in_new_tabs_reloaded_and_walked_back` passes, so it failed under load only. The
other four fail alone too, and none reads the side panel's charts this branch changes: `test_every_view_draws_cleanly_and_in_time[coordinator]`
and `[image-squeeze]` (routing open=* 24.9 s and 25.5 s, bound 20 s), `test_a_big_tangled_model_lays_out_in_time_and_cleanly`
(2779 ms, bound 2500 ms): layout time bounds, layout code untouched; `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`
(the /model page lacks "Nothing waiting." after an accept: the Model page, untouched). Not verified on main: `git
checkout -q main` was refused in this session, so the factory's rerun on clean main must settle them. Not run here:
the unit suite, the other three browser files (no page they draw uses these charts), and a merge of main (the clone is
main as of the branch, so there is nothing newer to merge).
