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
