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
