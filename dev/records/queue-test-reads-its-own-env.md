# queue-test-reads-its-own-env: tests of the queue's own container pass inside that container

depends-on: []

Every merge-queue run from 00:34 to 02:30 on 2026-11-22 failed `tests/test_agents.py::test_each_queue_suite_runs_in_a_container_on_the_queue_cpuset_with_no_network`, whatever the batch held. The queue gives each suite container `PYTEST_ADDOPTS=-o faulthandler_timeout=300` (`dev/bin/fac.py:479`, `suite()`), and the test's own call to `fac.suite` appends to the `PYTEST_ADDOPTS` it finds in its environment, so it sees the flag twice and its assertion at `tests/test_agents.py:326` fails. On the Mac, outside the container, it passes. The bisect sent every gap back; nothing merged for two hours. The coordinator quarantined the test to unblock the queue.

## Definition of done
1. A test of the factory's own suite and queue code reads no setting from the environment it happens to run in: `PYTEST_ADDOPTS` and every other variable the queue sets in its containers are cleared or set by the test (monkeypatch), so it passes the same inside the queue's container and outside.
2. A unit test runs that test with `PYTEST_ADDOPTS` already set, and it passes.
3. The test is released from `tests/quarantine.txt` (moved to the `# Released:` lines with this gap's name).
4. GAPS or the queue's docs say a factory test must not depend on the queue's own environment.

## Files to touch
`tests/test_agents.py` (and any sibling factory test that reads `PYTEST_ADDOPTS`), `tests/quarantine.txt`, docs.

## Acceptance tests
- the queue-container test passes with `PYTEST_ADDOPTS` set to the queue's value
- `tests/quarantine.txt` no longer holds it

## Size budget
10 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1. No code changed outside `tests/`; the only other change is 7 lines of prose in `dev/README.md`.

- Points 1 and 2: `tests/test_factory.py` now has `QUEUE_ENV` (`PYTEST_ADDOPTS`, `UV_PROJECT_ENVIRONMENT`,
  `PYTHONPYCACHEPREFIX`, `RUFF_CACHE_DIR`, `SPLIT_SHOTS`, the variables `fac.suite` and `agents.queued` set in a queue
  container). The `Factory` fixture's `env` drops them, which covers every factory test that starts the queue or
  `fac.suite` through the fixture, including `test_queue.py`'s faulthandler tests. In
  `test_each_queue_suite_runs_in_a_container...`, every `-e` name in the container's arguments must be in `QUEUE_ENV`,
  so a new setting has to be added there. That guard failed on its first run because `SPLIT_SHOTS` was missing, so it
  can fail. The acceptance test is
  `tests/test_agents.py::test_the_queue_container_test_passes_inside_the_queues_own_container`: it sets all five
  variables to the queue's values (monkeypatch) and runs the queue-container test. With the fixture's filter undone,
  it failed at `PYTEST_ADDOPTS=-o faulthandler_timeout=300`, which is the queue's failure reproduced. With the filter
  in place, it passes.
- Point 3: on this branch's base (fb39c0c0), `tests/quarantine.txt` does not list the test. The quarantine must have
  been added on the queue's main after this branch was cut, and this clone has no origin to check. Most reversible
  choice: I added only a `# Released:` line with this gap's name, and that line is a comment the parser ignores. When
  main is merged in, the coordinator's quarantine line for the test has to be deleted. If it lands as an added line
  beside this branch's Released line, the test stays quarantined.
- Point 4: `dev/README.md`, in the queue's suite-limits section, says a factory test must not depend on the queue's
  environment and points to `QUEUE_ENV`.
- Not done: origin/main was not merged in because this clone has no remote.
