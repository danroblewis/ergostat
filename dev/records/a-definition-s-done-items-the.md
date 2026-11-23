# plan-routes-unbuildable-done-items: a definition of done whose items need what the implementor's container cannot do (a server on a port, screenshots looked at by a person, CORR_SHOTS-style env on a command, Docker --sandbox or macOS, input files not in the repository) is marked at plan time, and those items become a measure-runs request or an owner need before the gap is built
depends-on: []
## Definition of done
1. dev/bin/plan.py classifies each done item against an allowlist of what an implementor session can run (pytest under suite_watch, ruff, demo_check, git); any item outside it is marked `needs: owner|measure` in the definition with the reason.
2. A gap whose definition has such an item is not leased to an implementor until that item is either a measure-runs request that the gap's tests can satisfy, or an owner need answered (needs park before building, not after a review).
3. The velocity record counts the parks caused by such items (`env-parks`) beside first-pass-yield.
4. SPEC and dev/README (The pipeline manager) say so.
## Acceptance tests
- tests/test_plan.py::test_a_done_item_needing_a_port_server_is_marked_needs_measure
- tests/test_plan.py::test_a_done_item_needing_files_outside_the_repo_is_a_needs_park_before_building
- tests/test_plan.py::test_a_plain_pytest_done_item_is_not_marked
- tests/test_measure.py::test_env_parks_are_counted_and_left_out_of_first_pass_failures_they_caused
Each is broken (classifier returns buildable for all) and seen to fail.
## Size budget
180 net lines outside tests and docs.
