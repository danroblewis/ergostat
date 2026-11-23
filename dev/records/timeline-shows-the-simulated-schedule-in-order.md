# timeline-shows-the-simulated-schedule-in-order: Timeline: rows in projected order, items not scheduled set apart with reasons, each block's capacity named

depends-on: [eta-works-out-on-the-factory-record]

Problem: the owner asks 'what finishes when and in what order'. Even with estimates, relTimeline's el.draw (ergostat/web/static/relations.js:222) orders rows by `segments[0][1] ?? es ?? first`: an open item's segments start at its creation, so rows follow creation order and the ranked backlog is scattered instead of a waterfall. Items the simulation leaves out (parked, or waiting on parked; the unscheduled flag from eta-works-out-on-the-factory-record) get no explanation, and nothing says which capacity the simulation used (the note at relations.js:362-366).
Change (no new page, panel or control): with estimates, unfinished rows are ordered by eta.start (p50), then eta.p50, then id; finished rows stay above as what happened. Unscheduled items go in a group at the end under 'Not scheduled (N)', each row showing its why ('parked', 'waits on gap/x, which is parked') and no bar ahead. The word 'held' is not used (it is a goal's word). The legend's per-kind sentence (filed Q60's form, times through filed Q34's formatter) adds the count: 'last of 40 gaps expected Tue 24 Nov 14:10, by Wed 09:00 at worst (9 in 10); 3 not scheduled'. The note names each block's simulated capacity and source: 'implementor 9 at once (pool stock.implementor-pool now), reviewer 6' (eta_api.merge passes capacity sources). Before the estimates are worked out the note says 'Working out the schedule: a simulation of N unfinished <kind> at each block's capacity' and any bars drawn from the forward pass are labelled as such. The item page's estimate line says 'not scheduled: <why>'. SPEC §5a Timeline row updated.
Definition of done:
1. Unfinished rows are in projected-start order: the projected bars' left edges are non-decreasing down the rows.
2. Unscheduled items are grouped last with reasons; no reader text on the Timeline contains 'held'.
3. The legend gives a clock time with its date and the count not scheduled.
4. The note names each block's capacity and source.
5. With the eta stubbed to None the note contains 'Working out the schedule'.
Files: ergostat/web/static/relations.js, ergostat/web/eta_api.py, ergostat/web/static/pages.js (item page line), docs/SPEC.md, tests/test_items_page.py.
Acceptance tests: browser on a fixture of 30 items with a 3-wide pool and ranks opposite to creation order (edges non-decreasing, at most 3 bars overlap at any x); a paused item and its dependent under 'Not scheduled (2)'; live check GET only on :8798/items?kind=gap&view=timeline: a staircase, not all at now. Rebase onto filed Q59/Q60 if they landed.
Budget: 90 net lines.

Milestone: timeline-real-schedule. Owner items: 17. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1: all five done items, with the acceptance test
`tests/test_items_page.py::test_the_timeline_shows_the_simulated_schedule_in_order` (30 gaps, a pool of 3, ranks
opposite to filing order) and a unit test, `tests/test_eta.py::test_the_take_order_holds_from_the_start_and_the_parked_are_not_scheduled`.
62 net lines outside tests and docs (budget 90).

Decisions taken alone (each the most reversible):
- The dependency eta-works-out-on-the-factory-record is not on main: no `unscheduled` flag exists. It is worked out
  here, in `ergostat/numbers/eta.py` (`unscheduled()`, outside the Files list): parked (a paused state), or kept in its
  kind's first state, or out of an `unblocked` block's queue, by a predecessor that is not scheduled. Those items are
  left out of their kind's last finish (else one parked gap makes every kind's finish "beyond the horizon"). If that
  gap lands with its own flag, this function should give way to it.
- Also in eta.py: at the start of a run every item was taken as it was queued, so the oldest were taken before the
  better-ranked were queued and the projected schedule followed filing order, not `order:`. Items are now all queued
  before the first take. Without this, done item 1 fails on the fixture.
- Rows are ordered by the left edge of the row's first bar ahead (the levelled run's), then eta.start, eta.p50, id:
  eta.start is a median over runs and need not agree with the one run drawn, and done item 1 is about the bars.
- The legend keeps Q60's landed form ("last gap (x) expected ..."), with "; N not scheduled" appended and the expected
  time always with its date; Q34's formatter is not on main, so the existing rgClock is used.
- The lanes note said "leases held over a lowered pool"; reworded, so no Timeline text says "held".

Not done: the live check (GET on :8798/items?kind=gap&view=timeline) - the command `curl -s -o /dev/null -w
"%{http_code}\n" --max-time 3 "http://127.0.0.1:8798/items?kind=gap&view=timeline"` was refused in this session.
Noted, not fixed (outside the gap): on a record where items have moved from the block's state to a paused one, the
simulation sends that share of items to it after their runs, so they become never-finishing in some runs.

Round 2: main (73d266e7, with eta-works-out-on-the-factory-record) merged in and the review's finding answered.
`eta.unscheduled()` is gone; main's flag (`etamodel._unscheduled`, items left out of the runs) is used, and its
reasons ("paused in parked", "waits on gap/p1, which is parked"). The merged `_work` folds that reason into a longer
`why` ("not scheduled: ...; <reasons' words>"), so it now also keeps the bare reason as the estimate's `said`. The
Timeline row and the item page read `said`, never `unscheduled` (now `True`), so neither prints "not scheduled: true".
The 'Working out the schedule' note is folded into main's note after main's 'simulation failed' text (eta_error).
Main's test_eta check of its old pending wording now checks 'Working out the schedule: a simulation of'. SPEC §5a
Timeline row now points to main's rule. 43 net lines in ergostat/ against main (budget 90). Ran: ruff (clean),
tests/test_eta.py (20 passed), tests/test_items_page.py under Playwright and the watchdog (26 passed, rc 0).
Not run: the break-to-fail check (the acceptance test run with the row reading `why` instead of `said`); the command
using `sed -i` to make the break was refused. The live check on :8798 was not tried again.

Round 3: main (a08e4b3e) merged in; it conflicted in SPEC, eta_api.py and relations.js. Main had swapped the forward
pass for the levelled projection, added milestone frames (summary rows), put a time zone after any date in rgClock, and
added calibration to the note. All kept. The branch's parts on top of them: the projected-start order (one `key` used
for frames and loose rows too, the unscheduled taken out of frames and put under "Not scheduled (N)" at the end), the
capacity and source note, and "Working out the schedule: ..." in place of main's "No estimates yet: the simulation is
being worked out." while pending. The bars drawn before the estimates are titled "the levelled projection, median
times, until the simulation is worked out". rgClock got a fourth argument, `day`, so the legend's expected time always
gives its date (main's rule gives it only when not today). The acceptance test now checks the bar title's new words and
allows the zone after a date. 44 net lines in ergostat/ against main (budget 90).
Ran: ruff (clean); tests/test_eta.py (24 passed); tests/test_items_page.py under Playwright and the watchdog twice. Run
1: 3 failed. The acceptance test failed on the zone after the date (regex fixed, then passed). The Timeline
`left_open_change_nothing` test passed alone and in run 2, so it is a load flake: the test waits a fixed 1.5 s, and
estimates that come later redraw the Timeline, as they do on main. Run 2: 68 passed, 1 failed.
`test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` fails alone too, waiting for the other project
in the header's `#project` switcher. This branch does not touch the header or the project list, so it is left alone
(not run on clean main here). Still not run: the break-to-fail check and the live check on :8798.
