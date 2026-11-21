# a-wait-says-its-dependency: a ready gap held by a dependency that is neither finished nor parked says so
depends-on: []

## Definition of done
dev/bin/deps.py plan() sets blocked_reason only for dependencies that are parked or dead (dev/bin/deps.py:140-142). A ready gap held by a dependency in any other unfinished state, or by one whose branch is already merged into main under another gap, waits with an empty blocked_reason (gap/upkeep-watched-loops waited 21.6h on gap/upkeep-index-files-continued this way). With this gap: every unfinished dependency is named in blocked_reason with its state. A dependency whose branch is an ancestor of main is named as 'landed, not closed' so the coordinator can close it. The situation the manager is raised with shows the reason.

## Acceptance tests
- tests/test_deps.py::test_a_gap_waiting_on_an_unfinished_dependency_names_it_and_its_state
- tests/test_deps.py::test_a_dependency_whose_branch_is_on_main_is_said_landed_not_closed

## Size budget
40 net lines
