# eta-works-out-on-the-factory-record: The completion estimates are worked out on the factory's record: no KeyError, items that cannot move never run a simulation to the horizon, and a failure is said

depends-on: []

Problem: on the live factory the Items Timeline stacks every gap at now because it never gets estimates. ~/.ergostat/ergostat-factory-678f59af/run.log has 6,443 lines `eta: KeyError: 'how'` and no successful run. The failure is ergostat/numbers/etamodel.py:292 (`elif r['how'] == 'ack':`), reached for an open run (taken, not ended) on an item whose own events moved it on after the take. web/eta_api.py _work (83-95) swallows the exception and caches None (retried no sooner than EVERY = 30 s), and relations.js then silently draws precedence.cpm's unlevelled forward pass (103 of 112 gaps start now). With that line fixed a run still takes 8.5 s: eta._Run.go loops `while self.heap and self.open > 0`, and paused items (43 parked gaps), items waiting on them (55 in all), items at a block commanded off and kinds with no finished state never finish, so with arrivals every run goes to the 90-day horizon (synthetic: 60 items 200 runs in 0.1 s; one paused item gives 53 runs in 5.1 s and p50 None). tests/test_eta.py has no paused case.
Words: 'holding' is a goal's word only (docs/vocabulary.md). An item the simulation leaves out is 'not scheduled', never 'held'.
Change: (a) etamodel.py:292 reads `elif r['end'] is not None and r['how'] == 'ack':` and an open run counts as going. (b) etamodel.read marks an item unscheduled when it is in a paused state, when its precedence predecessors reach an unscheduled item, when every block that takes from its state is off, or when its kind has no finished state; such items are not counted in _Run.open, not entered, and returned as {unscheduled: true, why: 'paused in parked' | 'waits on gap/x, which is parked' | 'waits for B, switched off'} with p50/p90 None; kinds[k] gains unscheduled (a count) and its p50/p90 cover movable items only. (c) eta_api._work keeps {error: '<type>: <message>'} instead of None and merge passes eta_error and unscheduled/why through. (d) relations.js note: with no estimates it says 'the simulation is being worked out' or 'failed: <error>'.
Definition of done:
1. etamodel.read on a record with an open run on an item moved past its take by its own events returns and counts the run as going.
2. One paused item with arrivals on: 200 runs in under 1 s, kind p50 not None, unscheduled == 1.
3. An item waiting on a paused item, and an item only at off blocks, are unscheduled with a reason naming the cause.
4. A simulation that raises is said on the Timeline with its error.
5. The four backtest records' table in docs/roadmap/overnight/eta.md is rerun and unchanged.
6. SPEC §5a Completion estimates says such items are left out of the run and counted.
Files: ergostat/numbers/etamodel.py, ergostat/numbers/eta.py, ergostat/web/eta_api.py, ergostat/web/static/relations.js, tests/test_eta.py, docs/SPEC.md.
Acceptance tests: test_eta.py::test_an_open_run_on_an_item_moved_on_by_its_own_events, ::test_paused_item_does_not_hold_the_run, ::test_waiting_on_a_paused_item_is_unscheduled, ::test_off_block_items_unscheduled, ::test_a_failed_simulation_is_said. After deploy (GET only): :8798/api/items-graph?kinds=gap has eta.runs >= 20 and run.log gains no 'eta: KeyError'.
Budget: 110 net lines including tests.

Milestone: timeline-real-schedule. Owner items: 17 (also 2: a failed simulation is cached and tried again every 30 s, eta_api.py:14, 78, each try costing seconds). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built (a) to (d) as written. The why texts: "paused in S", "waits for B, switched off" (blocks joined by "and"),
"has no finished state (K)", and "waits on X, which ..." naming the cause however far ("waits on t/1, which waits on
t/0, which is parked"). An item at off blocks that holds a lease is still scheduled, because its run ends. `reasons()`
is unchanged (the Items list and item page keep its words), but `_work` does not let its why replace an unscheduled
item's own. kinds[k].open now counts the movable items only, and kinds[k].unscheduled the rest. A failure is now
cached like an answer, so it is tried again when the record changes (at most every 30 s) or after 120 s. The Timeline
says "the simulation is being worked out" only when the answer is of now (within 5 s) and some item is open, so a
moment travelled to says nothing.

Each acceptance test was seen to fail with its fix undone: the KeyError came back; 12 runs instead of 200; one block
of two off was marked; no propagation; None for the error.

Not done:
- DoD 5, the table rerun: not run. Running a script outside `scripts/named_tests.py` was refused in this session
  (`uv run python /tmp/bt/table.py ...`, and before that `git archive HEAD | tar -x -C /tmp/base` to keep a base copy).
  So the claim is narrower: on those records no item is unscheduled, which the owner's case now asserts
  (`test_the_owners_case_100_tickets_6_leases`). In that case the run takes the same path and draws the same random
  numbers as before, and `test_backtest_p90_coverage_on_a_synthetic_record` passes. The steady records use the same
  model. The ticket-factory record has a finished state and no paused message, but no test checked it. The table still
  needs rerunning on a host.
- The JS note is checked only by its text in `test_a_failed_simulation_is_said`, not drawn in a browser.
  `tests/test_items_page.py` passes (21, none skipped).
- After deploy (GET :8798 and run.log): not run here, since this clone has no live factory.

Overrun reason: 139 net lines against 110 (34 in code, 105 in tests). Each of the five acceptance tests needs its own
record or inputs, and two also check the record-read path through `read` (the paused and gated models), which the
budget did not count.
