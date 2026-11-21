# rs-calls: a run's calls to ergostat survive the engine restarting

depends-on: [rs-detach]

## Definition of done
- A run's calls (events, renew, nack, gated actions) retry with backoff across an engine restart, up to a bound (a setting, default 2 minutes), then fail as they do today.
- Each call carries an idempotency key, so a call in flight when the engine stopped is recorded once, a parked gated action included.

## Files to touch
The CLI's socket client, the engine's call handler, `tests/test_calls.py`.

## Acceptance tests
- `tests/test_calls.py::test_a_call_reconnects_across_a_restart`
- `tests/test_calls.py::test_a_call_in_flight_at_the_stop_is_recorded_once`
- `tests/test_calls.py::test_a_gated_action_in_flight_at_the_stop_is_asked_once`
- `tests/test_calls.py::test_a_call_past_the_bound_fails`

## Size budget
100 net lines of code outside `tests/` and `docs/`.
