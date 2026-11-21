# rs-detach: a run's process no longer depends on the engine that started it

depends-on: [lease-race-resumed]

First of four parts of upgrades that keep runs going (owner, 2026-11-20). This part changes **no behaviour at a switch**.

## Definition of done
- A run starts in its own session, its output goes to its run log file (no pipe the engine holds), and the engine follows that file. A run record in the state folder holds pid, process start time, run id, lease and block.
- Streamed output, timeouts, stop and exit codes behave as before.
- Process start time works on macOS and Linux, and the wrapper runs under bash 3.2 and dash.

## Risks
Replacing the pipe touches **every** run: compare run-start latency and thread count with main, and report both.

## Files to touch
`ergostat/spec/engine.py`, the run/stream code it uses, `tests/test_resilience.py`.

## Acceptance tests
- `tests/test_resilience.py::test_a_run_keeps_going_when_its_engine_is_killed`
- `tests/test_resilience.py::test_a_detached_runs_output_and_exit_are_recorded_once`
- `tests/test_resilience.py::test_a_run_record_detects_a_reused_pid`

## Size budget
150 net lines of code outside `tests/` and `docs/`.
