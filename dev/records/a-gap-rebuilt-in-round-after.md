# stuck-building-reads-the-current-build: a rebuilt gap is not stuck while its current build is young
depends-on: []

## Definition of done
1. watch.stuck() judges a gap in `building` by the build it is in now (visit_start of its current visit, a lease taken and given back counting as the same visit), not by the sum of every building visit in state-times (hours_in, dev/bin/watch.py:106-111). Rounds of rebuilding are bounded by the kill rule (build hours, fix rounds), not by this trigger.
2. Other states keep today's reading (closed visits plus the current one), so gap/timed in test_a_gap_stuck_in_its_state_from_its_moves_and_from_state_times still triggers.
3. A gap whose current build has run past its threshold is still a trigger, with that build's hours in its why.
4. dev/README.md (The pipeline manager) says which states read the current visit and which the sum.

Why: on 11-24 00:02 three gaps were raised stuck building at 5.1-6.8h while their current builds were about 3, 56 and 75 minutes old (blocks-model-health-on-the-blocks: 6.11h of closed building visits plus 3 min), spending a manager session on live work.

## Acceptance tests
- tests/test_factory_manager.py::test_a_gap_rebuilt_in_rounds_is_not_stuck_while_its_build_is_young (time_in building 6h over 7 visits, current build 10 min: no trigger; fails today)
- tests/test_factory_manager.py::test_a_build_past_its_threshold_is_stuck_by_that_build (current build 6h, threshold 5h: one trigger reading 6.0h)
- tests/test_factory_manager.py::test_a_gap_stuck_in_its_state_from_its_moves_and_from_state_times still passes

## Size budget
20 net lines outside tests and docs.
