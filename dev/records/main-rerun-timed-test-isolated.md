# main-rerun-timed-test-isolated: main's own failing test made order-proof
depends-on: []

## Definition of done
- tests/test_agents.py::test_a_rerun_is_timed_by_the_suite_that_failed passes on main in the unit suite (-n as the queue runs it, inside the queue's suite container) and alone. It is failing on two or more main commits (af4bc34a9e4c, ead497d1f4bc and since 11-23 09:57), so gap/safe-stalls-heal-themselves is held.
- The cause is found and named in the record: the test puts fac and agents into sys.modules with setdefault (tests/test_agents.py:226-228), so it keeps whatever fac/agents module an earlier test in the same worker left there, stubbed or monkeypatched (e.g. agents.fac.git at :395). Or the cause is onmain.room itself (dev/bin/onmain.py:31-34, LEAST=60) or the container's clock. Fix that cause. Do not only raise numbers or quarantine the test (lesson-10).
- If the cause is module leakage, the test loads onmain with its own fresh fac and agents (monkeypatch.setitem on sys.modules, undone after the test). It passes no matter which tests ran before it in the worker.
- room() is unchanged unless it is the cause. If it is, SPEC and the agent guide say what changed.

## Acceptance tests
- tests/test_agents.py::test_a_rerun_is_timed_by_the_suite_that_failed passes after a stand-in fac/agents module (lacking or patching what onmain uses) is put into sys.modules first: a new test tests/test_agents.py::test_room_holds_after_another_test_left_a_stub_fac. That new test fails on main as it is now.
- The full unit suite passes on the branch with rc 0, ruff is clean, and origin/main is merged in.

## Size budget
30 net lines outside tests and docs (expected near 0).
