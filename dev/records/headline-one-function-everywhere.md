# headline-one-function-everywhere: The page and the CLI never count goals themselves: header, switcher, side list, Goals page and `ergostat status` print the server's one count

depends-on: [goal-state-says-its-system-and-upkeep]

Problem (R6 piece 8): the header counts goals with status off in the browser (ergostat/web/static/util.js:364); the side list's group and the Goals page each count their own rows; `ergostat status` prints its own summary (cli/running.py:360-362). The numbers disagree at the same moment (shots/story-1-b3-loops.png, pm-job-loops-4s.png). goal-state-says-its-system-and-upkeep makes the one server function (state.goals_off) and uses it in /api/status and projects._row; this gap is the cleanup that makes every other surface print it and nothing else.
Change: the loops answer's summary and the CLI's status and projects lines call state.goals_off. The page never counts: the header (with filed Q14's layout), the switcher, the side list's group heading and the Goals page's heading print the numbers they were given. A test fails when page code filters goals by status to make a count. Later fields of the count (in_grace, from queue-goal-grace-in-words) are added to the one function and reach every surface through it.
Definition of done:
1. On a fixture with a system goal, an upkeep goal and an open goal off, at one moment the header, the switcher entry (seen from another project), the side list group's count and the Goals page heading show the same numbers as /api/status goals_off.
2. `ergostat status` and `ergostat projects` print the same numbers.
3. grep finds no `status === 'off'` count in util.js, pages.js or diagram.js outside row styling.
4. A snapshot file shows the counts it was saved with.
Files: ergostat/web/server.py (loops summary), ergostat/cli/status.py, ergostat/cli/running.py, ergostat/web/static/util.js, pages.js, diagram.js, tests/test_graph_cli_web.py, a browser test.
Acceptance tests: the agreement test on the fixture; the grep test.
Budget: 50 net lines.

Milestone: r6-off-tells-the-truth. Owner items: R6 piece 8 (with the owner's decision on the headline). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. Every item of the definition is done. Nobody could be asked, so each choice below is the most reversible one:

- "The loops answer's summary": `/api/loops` stays a map of goal name to state (pages.js, details.js, loadtest.py and
  scale_bench.py read it that way; a `summary` key would be read as a goal). The Loops page's heading ("Loops · goals off N ·
  model upkeep M") prints the status answer's `goals_off`, the same state.goals_off call the header reads, so the two
  cannot differ. The only server.py change is `controlled_off` in /api/status, so the Blocks caption's "N off" is the
  one function's count of the controlled goals (the caption also counted in the browser, and the grep test covers it).
- One wording for the CLI, `state.goals_said`: `ergostat` prints it as a line under its first line (and `goals_off` in
  `--json`); `ergostat projects` prints it in its LOOPS column, from a new `goals` field of the row (the same call).
  The projects column used to count off and open together as "N off"; it now gives them separately, as the header does.
- A status without `goals_off` (an older snapshot) shows "?" off. It never makes a count of its own and never shows 0.
- The side list's group still chooses its rows by `a.state === "off"`. That is row grouping, allowed by name in the grep
  test, as is the `.some` that opens the suggestions. Only its heading's number changed.
- tests/test_diagram_rendering.py: the side-list test waited for "loops off" in the header (Q14 had already changed it
  to "goals off") and compared the heading with its own rows. Both checks now read the server's count. The caption
  test now reads `goals_off.system` and `controlled_off`.

Acceptance tests: tests/test_items_page.py::test_every_surface_prints_the_servers_one_count_of_goals_off (header,
side list heading, Loops heading, switcher seen from another project, a snapshot file; items 1 and 4),
tests/test_graph_cli_web.py::test_status_and_projects_print_the_one_count_api_status_gives (item 2) and
::test_no_page_code_counts_goals_by_their_status (item 3, an allowlist of lines). Seen to fail: with the side heading
put back to counting its rows (10 against 8 · model upkeep 2), and with a Loops heading that counts `status === "off"`
rows (the grep test).

## Where it stopped

Parked by the factory (implementor, 2026-11-22 14:15).

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

Parked by the factory (dead-letters, 2026-11-22 14:15).

Its runs failed past their attempts (a dead letter):
- attempt 17: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 18: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 19: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 20: nack the run ended with gap/headline-one-function-everywhere still parked

## Where it stopped

Round 1, continued: main (52c675fe) merged in. The conflicts in projects.py, diagram.js, pages.js and util.js are resolved
keeping both sides: main's third value from `_row`, its row classes and the Loops page's "Loading…", plus this branch's
`goals` field and its headings that print the server's count.

Main's switcher (`projects.running()`) now lists only projects whose engine holds `run.pid`, and `ergostat web` never
takes it, so a project served only by `ergostat web` is counted as stopped and never offered. The acceptance test's
switcher step therefore had nothing to find. The test now holds the observed project's `run.pid` itself, as an engine
would, before the second server makes its first list. It does not start a real engine, because the engine's sensors
move the fixture (a run showed system 0, modelling 1). Seen to fail with the switcher's number broken (10 against 9).

Left, on main and not this gap's to fix: tests/test_items_page.py::test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart
times out at line 1331 for the same reason (it serves both projects with `ergostat web`). The branch does not change
that test, the lister, `projects.running` or `refreshProjects`. Running it on a clean worktree of main was refused here
(`git worktree add --detach /tmp/main-check main`), so the claim that it fails on main rests on reading the code.

## Where it stopped

Round 2: the review's one finding is answered. The diagram's caption counted every goal, upkeep goals included, but
its "N off" counted only the system's goals, so upkeep goals that were off dropped out of it ('3 off' became '1 off'
over the same total). The caption now says what the header says. Its total is the system's goals (Dynamics: those
with no `upkeep`; Blocks: the controlled ones with no `upkeep`), its off comes from the one function, and
"· model upkeep N" is shown apart. In `/api/status`, `controlled_off` is now the whole `state.goals_off` answer for
the controlled goals (it was only the `system` number), so the Blocks caption shows upkeep the same way. SPEC §8 says
so. Why this choice: it is the reviewer's first suggested fix and matches the header, the side list and the Loops
heading, so every surface prints one form, and nothing is removed.

Test: tests/test_items_page.py::test_every_surface_prints_the_servers_one_count_of_goals_off now reads both captions
on its fixture, where both modelling goals are off and both are controlled. It counts the expected total from the
loops' `upkeep` field, not from the server's count: "10 goals, N off · model upkeep 2" and "… control loops, N off ·
model upkeep 2". Seen to fail with the upkeep figure dropped ("10 goals, 9 off") and with the total counting upkeep
goals again ("12 goals, 9 off · model upkeep 2"). The caption test in tests/test_diagram_rendering.py now expects the
new form.

## Where it stopped

Round 3: main (7cb97857) merged in. The one conflict, in pages.js's Loops page, is resolved keeping main's removal of
the browser's `perf`/`pts` caches and this branch's heading that prints the server's goals-off count. No other change.

## Where it stopped

Round 4: main (ead497d1) merged in. The one conflict, in diagram.js's side list, is resolved keeping main's
`id: "waiting"` and `tabindex` on the "Waiting for you" heading (its one-step link target) and this branch's "Goals off"
heading that prints the server's count (`goalsOffText()`) instead of main's `count(off)` of its rows. No other change.

After the merge, tests/test_diagram_rendering.py gave 27 failed and 255 passed. All of these failures are in code the
branch does not touch. The branch's only changes to the page are the caption's count, the side list's "Goals off"
heading and the Loops page heading.
`test_every_part_opens_its_panel_when_clicked_even_mid_redraw` and
`test_a_goal_name_opens_its_evidence_and_rings_its_stock_or_its_summing_junction[False]` passed when run again. These
fail again when run alone: `test_sensors_are_blocks_with_what_they_read_and_no_part_has_a_tooltip[*]` (20 examples: a
`<title>` "Drawn alike here with …" from dynamics.js:467, a file this branch does not change);
`test_every_view_draws_cleanly_and_in_time[ticket-factory]` (satellite-far 15 against a ceiling of 14, layout);
`test_parts_chosen_with_a_box_move_together_pinned_and_with_no_new_layout` (stock did not move);
`test_everything_clickable_in_the_diagram_is_reached_and_acted_on_by_keyboard` (focus not on the detail heading);
`test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known` (the loop list);
`test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page` (the Model page has no "Nothing
waiting."). They are left alone (lesson 13). No clean worktree of main could be made here, so the claim that they fail
on main too rests on the diff, not on a run. The acceptance tests and ruff pass.

## Where it stopped

Round 5: main (5411f137) merged in. The conflict in diagram.js's side list is resolved keeping main's new layout
(the "Waiting for you" heading and rows only when something waits, folded past 3, the legend box, the `key`s on each
part) and this branch's "Goals off" heading that prints the server's count (`goalsOffText()`) instead of main's
`count(off)`. In tests/test_items_page.py both sides are kept: this branch's acceptance test comes before main's
milestone tests, which main wants last in the file. Main now shows "Waiting for you" only when something waits, so
the acceptance test no longer waits for three headings or reads `heads[1]`. It finds the one heading that starts with
"Goals off". Seen to fail with the heading put back to `count(off)`.

Runs: the acceptance tests pass, as do
tests/test_diagram_rendering.py::test_needs_attention_is_three_headed_groups_in_a_fixed_order and ruff.
tests/test_items_page.py ran whole three times. Each time,
test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart failed: it timed out at its switcher wait
(line 1647). This is the main-side failure described in round 1 (it serves both projects with `ergostat web`, which
never holds `run.pid`), and the branch does not change that test. The first run had one more failure. It passed on
both later runs, and its name was not captured. tests/test_diagram_rendering.py was not run whole this round.

## Where it stopped

Round 6: main (e43046dc) merged in. Three conflicts, each resolved by keeping both sides:
- ergostat/state.py: main's new `quiet()` and this branch's `goals_said()`.
- pages.js's Loops page: main's quiet-systems box and this branch's heading that prints the server's goals-off count.
- tests/test_items_page.py: this branch's acceptance test and main's items-overview tests.
No other change. Main's quiet line is chosen by the server (`state.quiet`), so the page still makes no count of its own.

Runs: ruff is clean. These pass: the two acceptance tests in tests/test_graph_cli_web.py,
tests/test_items_page.py::test_every_surface_prints_the_servers_one_count_of_goals_off (under the watchdog), and
main's tests/test_page_refresh.py::test_a_quiet_system_says_so_on_the_loops_page_and_in_its_panel_until_a_goal_goes_off.
tests/test_page_refresh.py::test_other_pages_left_open_change_nothing[diagram?view=process&by=events] failed on both
of its two runs (32 mutations, then 6). They come from an H1 `title` and a DIV `class`. Those are set on every refresh
by main's own lines in diagram.js `show()` (`shell.classList.remove("opening")` and `caption.title = …`). This branch
changes neither line. On the process view its caption code is skipped, and its side heading changes only a SPAN's text.
It is left alone (lesson 13). A run with main's diagram.js put back was refused here, so this rests on reading the
code, not on a run.

## Where it stopped

Round 7: main (7a905955) merged in. Two conflicts, both where main's goal-row-one-renderer replaced `status === "off"`
with `goalWord(l) === "off"` in a count this branch had already removed (the Dynamics/Blocks caption and the header's
fallback for a status without `goals_off`). Both are resolved to this branch's form, which prints the server's count
and makes none of its own. Main's other changes are kept. The header's tooltip line now reads `goalWord(l) === "off"`.
It lists the names of the goals off and counts nothing, so the grep test's allowlist now has it in place of the old
`status` form.

The review's finding is answered. Under `--system X`, `ergostat status` now counts the narrowed map,
`st.goals_off({"loops": loops})`, the same way server.py does for `controlled_off`. Its goals line and its --json
`goals_off` both use it, so `goals_off` agrees with `loops`. Test:
tests/test_graph_cli_web.py::test_status_of_one_system_counts_only_that_systems_goals (`--system shop` on the fixture
with its shop, modelling and upkeep systems: 1 off, 1 open, no upkeep, where the whole project has 9 off and upkeep 2).
Seen to fail with the old `st.goals_off(snap)` (9 against 1).

Runs: ruff is clean. tests/test_graph_cli_web.py passed whole (50 passed), and so did
tests/test_items_page.py::test_every_surface_prints_the_servers_one_count_of_goals_off under the watchdog.
tests/test_diagram_rendering.py was started whole under the watchdog, but it was stopped at the 600 s limit on
background commands before it ended, so it has no result. A restart with a longer limit was refused here
(`uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python scripts/named_tests.py
tests/test_diagram_rendering.py > /tmp/diagram-r7.log 2>&1`). tests/test_page_refresh.py and the whole of
tests/test_items_page.py were not run this round.
