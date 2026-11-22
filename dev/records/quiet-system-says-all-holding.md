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
