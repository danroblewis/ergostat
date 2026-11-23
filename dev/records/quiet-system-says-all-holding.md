# quiet-system-says-all-holding: A quiet system says so: 'all goals holding, nothing being worked'

depends-on: [goal-state-says-its-system-and-upkeep]

Problem (R7 piece 8): when no goal of a system is off the page shows nothing about it: an empty attention group and rows without emphasis. A reader cannot tell 'healthy' from 'not loaded' or 'not measured' (shots/story-2-c4-located-worked.png). Needs each goal's system (goal-state-says-its-system-and-upkeep).
Change: one server function per system returns its quiet sentence: 'all N goals holding, nothing being worked' when none is off, open or unknown and no item is taken in it; 'all N goals holding, 3 items being worked' when leases are out; nothing otherwise. It is printed on the Goals page's system group heading (filed Q16's grouping), in the system's panel on the diagram, and on the closed box's title row when dynamics-box-goal-rows has landed (the box then folds its holding rows under the sentence). Unknown goals are never called holding.
Definition of done:
1. On a fixture whose system has 14 goals holding, its group on /goals and its panel read 'all 14 goals holding' with the count being worked from the leases.
2. A system with one unknown goal does not show the sentence.
3. The sentence disappears within one poll of a goal going off.
4. The count equals /api/loops filtered by system.
Files: ergostat/state.py or ergostat/web/server.py (the sentence), ergostat/web/static/pages.js, details.js, dynamics.js, tests.
Acceptance tests: a unit test of the sentence for quiet, being-worked, unknown and off fixtures; a browser check on the fixture.
Budget: 50 net lines.

Milestone: r7-evidence-is-a-runbook. Owner items: R7 piece 8. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built in round 1, 33 net lines. Two of the places the definition names to print the sentence do not exist on main, and
nobody could be asked, so I took the most reversible option each time:

- **No /goals page with system groups (filed Q16 has not landed).** The page is still the Loops page (one table, no
  groups). The sentence is printed there as one line per quiet system above the table (`.quiet-line[data-system]`,
  "shop: all 14 goals holding, 3 items being worked"), read from `/api/systems`' new `quiet`. When Q16's grouping
  lands, that line moves onto its group's heading and the line above the table goes. That is a few lines in pages.js.
- **dynamics-box-goal-rows has not landed**, so nothing is printed on a closed box's title row and no rows are folded
  under it. The graph's system nodes already carry `quiet` (a poll value, graph_poll.VALUES), ready for that gap.
- The sentence is `state.quiet(project, snap, system)`. Only a status of exactly `holding` counts, so off, open, stale and
  unknown goals all stop it, and so does a system with no goal. N is the goals in `snap["loops"]` (what /api/loops
  serves) whose `system` equals the system. Goals of a system nested inside it are not counted, as in point 4. The
  count being worked is the items in state `leased` with `lease.block` one of the system's blocks that take items.
  The valve panel counts its leases the same way (item_sets.leased_by).
- The panel is the system panel of both the Control and the Dynamics views. The panel is drawn once when opened, so
  `quietRefresh` (details.js) sets its line again from each graph answer. That needs one line in diagram.js, a file the
  definition does not list.
- Point 3 is checked at the page's own pace (a poll every 2.5 s). The server keeps a snapshot 1.5 s
  (web/server.py `Live.snapshot`), so a page sped up by ERGOSTAT_POLL_SPEED can be answered from a snapshot made
  before the reading. At the real pace, the sentence goes with the answer in flight or the next one.
- SPEC §8 has a "A quiet system" paragraph.
- Acceptance tests: `tests/test_quiet_system.py` (quiet, being worked with leases and one given back, unknown, off), and
  `tests/test_page_refresh.py::test_a_quiet_system_says_so_on_the_loops_page_and_in_its_panel_until_a_goal_goes_off`
  on the same 14-goal fixture. The unit test failed when unknown was let through and when the leases were not counted.
  The browser test failed when `quietRefresh` did nothing.
- Suites run here: test_quiet_system.py (4 passed), test_page_refresh.py (9 passed), test_page_polling.py (17
  passed), test_graph_cli_web.py, test_dynamics_view.py and test_goal_upkeep.py (47 passed), and ruff (clean).
  test_diagram_rendering.py failed twice (6, then 9 of 204), and the failures are not this branch's:
  - Failing on main too, with main's `ergostat/` restored into this tree and the same tests run:
    test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known (the side list's
    "Goals off" headline matches its words check), test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page
    (the Model page lacks "Nothing waiting."), test_every_part_opens_its_panel_when_clicked_even_mid_redraw (a stock's
    panel not open within 3 s), and test_every_lines_panel_links_to_the_parts_it_joins[alert-triage, coordinator,
    ticket-factory].
  - Time bounds missed under load, not run again: test_every_view_draws_cleanly_and_in_time[coordinator,
    image-squeeze] (routing 27-30 s against 20 s), and test_a_big_tangled_model_lays_out_in_time_and_cleanly (drawing
    2.8 s against 2.5 s).

## Where it stopped

Parked by the factory (implementor, 2026-11-22 17:04).

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

Parked by the factory (dead-letters, 2026-11-22 17:04).

Its runs failed past their attempts (a dead letter):
- attempt 4: nack queue: the push of e7edd3ff1dfd (gap/ui-a-loop-is-called-r-or-b-only-when-every-link-has) is requested
- attempt 5: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 6: nack exited 1
- attempt 7: nack the run ended with gap/quiet-system-says-all-holding still parked

## Where it stopped

Round 2 (2026-11-23): the factory's merge of main (bf6dbebf) conflicted in diagram.js and pages.js. Both were resolved
by keeping main's lines and the branch's: in `show()`, main's caption lines plus the branch's `quietRefresh(g)` call.
On the Loops page, main's "Loading…" box plus the branch's `qbox` of quiet lines. Committed as b055f008. Nothing else
changed: the build is round 1's.

- Run after the merge: ruff (clean), tests/test_quiet_system.py (4 passed), tests/test_page_refresh.py (9 passed,
  1 failed, twice).
- The failure is `test_other_pages_left_open_change_nothing[diagram?view=process&by=events]`: 6 mutations in 3
  refreshes, each a DIV's `class` and an H1's `title`. These are written on every graph answer by two lines main
  brought into `show()` in diagram.js: `shell.classList.remove("opening")` and `caption.title = caption.textContent`,
  which write the attribute even when it is unchanged. The branch's `quietRefresh` writes only to
  `#detail [data-quiet]`, and no panel is open in that test. So the failure is main's, not this branch's (lesson 13):
  it is left alone. It was not run on main itself here, because `git worktree add /tmp/mainwt main` was refused.
