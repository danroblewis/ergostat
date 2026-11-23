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
