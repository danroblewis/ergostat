# state-times: how long each gap spends in each state and in the build-review loop, measured and held by goals

depends-on: []

Branch `state-times`, from main. Asked by the owner: track the time to completion of each step (especially the testing
and merge gates, and the implementor), the time a gap spends in the implementor/reviewer feedback loop and how many
times it goes round, and how long each gap stays in each state, so each can carry a goal (a setpoint) and the factory's
delivery time can be driven down (toward 30 or 15 minutes a change).

Today's measures (dev/model/measures.yaml, dev/bin/measure.py) are medians over merged gaps only: survivorship bias, and
no time per state.

## Definition of done

From the record alone (the gap's state changes and the lease, review and queue events), for every gap whatever its end
(merged, parked, dead, or still open): the time it spent in each state, summed over its visits, and the number of
visits; the build-review loop as one span (from the first time it is taken to build until approved, parked or dead),
its rounds (how many times it went round) and the time inside it; and the gates on their own: the implementor's fast
suites, the review, the queue's suites (unit, browser, demo) and the push wait. These are written on each gap
(`time_in`, `loop_rounds`, `loop_hours`) and shown on its item page; the factory model gets a measure per state and
per gate (median and p90 over gaps that left that state in the window, not only merged ones), and a goal on each the
owner can set (`hold:`), starting from today's values as their setpoints; and `dev/bin/status.py` prints the per-state
table. Waiting states (open, ready, fix, approved, queued) are reported apart from working states, since time waiting
is the cheapest to remove. SPEC or the factory README says how each is counted.

## Acceptance tests

- `tests/test_factory_times.py::test_time_in_each_state_sums_visits_for_any_end`: a gap through fix twice and parked.
- `tests/test_factory_times.py::test_the_build_review_loop_counts_rounds_and_its_span`.
- `tests/test_factory_times.py::test_gate_times_from_the_lease_and_queue_events`.
- `tests/test_factory_times.py::test_a_measure_per_state_counts_gaps_that_left_it_not_only_merged_ones`: median and p90.
- `tests/test_factory_times.py::test_status_prints_the_per_state_table`.

## Size budget

400 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1: `dev/bin/times.py` (the `timer` block, every 10 minutes: `gap.timed` with `time_in`, `loop_rounds`,
`loop_hours`, `loop_ended` and `gates` on each gap whose record grew, at most 50 a run), the measures in
`dev/bin/measure.py` (`in-STATE-hours`, `loop-hours`, `loop-rounds`, `gate-GATE-minutes`, each median and `-p90`),
`dev/model/times.yaml` (an auxiliary and a goal on each, the system `times`), the table in `dev/bin/status.py`, and how
each is counted in dev/README.md (*Time in each state*). About 320 net lines, all in `dev/` and `ergostat.yaml`.

Decisions taken alone (each reversible), and what is left:

- **The setpoints are not today's values yet.** This clone has no instance record to read them from. The holds in
  `dev/model/times.yaml` are first guesses; `python3 dev/bin/times.py setpoints`, run once in the instance's folder,
  sets each to its reading over the last 14 days (tested on a fixture). That run is the step left.
- `built` is reported with the waiting states (it waits for the reviewer), besides the five the definition names.
- A gap carries its closed visits only: the visit it is in now counts once it ends, so `gap.timed` is not rewritten
  every pass. `status.py` shows the open visits apart (how many gaps are in each state now, and the oldest).
- The loop ends at the first approval, park or dead letter after the last build, so a queue send-back that is rebuilt
  stays inside one loop; its rounds are its builds.
- `gap.timed` is an event with no state, like `gap.reverted`; the goals are not wired into `factory-off`, so they do
  not ask the coordinator for gaps until the owner chooses to.

Round 2, answering review/state-times-1, every finding:

- **The bookmark (blocking, lesson-1).** It is no longer `timed_n` in the record: `run/times.json` (gap id -> events
  read) moves on every read, whether or not `gap.timed` is written, so an event that changes no timing
  (`gap.dependencies`, a late `lease.ended`, one that lands between the read and the write) is read once. Gaps never
  read come first in the run's 50 slots. An unreadable bookmark counts as none: every gap is read again, and only a
  changed timing is written. Test: `test_an_event_that_changes_no_timing_is_read_once` (fails with the old rule).
- **Waiting and working (lesson-8).** Split by what each state waits on: waiting is open, replan, planned, split,
  ready, fix, built, approved, queue-failed (for triage) and dead (for a park); working is leased (a run holds the gap:
  the planner's, plan review's and triage's whole run), building, in-review and queued. The definition names `queued`
  as waiting, but here `gap.queued` is said when the queue's run starts, so the state holds its lock, merge and suites;
  the wait for the queue is `approved`. Moving one name between the two tuples in `times.py` reverses it.
- **The fast gate (lesson-8).** `implement.py` now records `fast_seconds`, the ruff and unit seconds of every try in a
  round; the gate sums those. Builds recorded before this have only their last try (`suites_fast`); the README says so.
- **The setpoints (not blocking).** Still first guesses: there is still no instance record in this clone. The step
  left is the same: `python3 dev/bin/times.py setpoints` once in the instance's folder.
