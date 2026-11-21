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

## Where it stopped
Built (round 1), 59 net lines in `ergostat/calls/client.py`, `ergostat/calls/ops.py` and `ergostat/leases/acts.py`.
The decisions taken alone, each the most reversible one:
- **The setting** is an environment variable, `ERGOSTAT_CALL_RETRY` (seconds; default 120, at most 3600; unreadable
  means the default), not a model setting: the client reads no model. Only a run's call (`ERGOSTAT_SOCKET` set)
  retries; a command from a shell does what it did at once. Past the bound a call does what it does today with no
  engine (the command falls back to writing the record itself).
- **Retried** on: no socket, a refused connection, a connection reset or closed before a whole answer. A refusal, an
  `elsewhere` answer and a read timeout are not retried.
- **The key** (`"call"`, one per call, the same on every try) becomes the id of each event it records without one
  (the record already drops an id seen before), and the id of a renew's or nack's event. For `act`: a run with an item
  already finds its held action by action and arguments, so the key is used only when there is no `--key` and no
  item. `leases/acts.py` (outside the files named) takes an `id` for this: two lines.
- An `act` asked again after a restart waits its `wait` again from then.
- One more test beyond the four: `test_a_lease_call_asked_again_is_recorded_once`.

After the factory's unit run stalled (its output stopped at 18%, no failure printed): not reproduced here. Every
file whose runs call ergostat (`test_calls`, `test_leases`, `test_lease_kill`, `test_spec_engine`,
`test_program_actions`, `test_triggers2`/`3`, `test_resilience`, `test_gated_actions`, `test_daemons`,
`test_daemons_restart`) and every file with a `serial` test (a long one holds the whole parallel run back) passed alone
in its usual time; the whole suite was not run here. The likeliest cause, guarded against: an `ERGOSTAT_SOCKET`
inherited from an engine whose socket this machine can't reach (another machine's or container's path), so each
call waited the whole bound where it used to fall back at once. A call no longer tries again when the socket's folder
does not exist: an engine restarting keeps its state folder (or the short-path folder in the temporary directory),
so only a socket that can come back is waited for (`test_a_call_past_the_bound_fails`, checked to fail without it).

After the factory's second unit run stalled (its output stopped at 3%, no failure printed; not reproduced here, and the
whole suite was not run here): with every retry traced, the files run alone showed one call waiting on an engine
that had stopped for good (a daemon's `act` in `test_ticket_factory_daemons`, which was killed after 2 s). The earlier
guard, "the socket's folder exists", also falls short: every engine whose state path is long puts its socket in the
one shared `/tmp/ergostat-UID/`. So a run's socket inherited from an engine elsewhere (the factory's, which runs these
suites as a block) still waited the whole 2 minutes on each call. Now a call tries again only while the run's own state
folder (`ERGOSTAT_STATE_DIR` when the socket is its own, else the socket's folder) is here. Once the socket has been
removed (a clean stop) it waits `GONE` = 10 s at most for the socket to come back. A killed engine leaves its socket
behind, so its run gets the whole bound. This is my own call and the most reversible one: a restart (close, then exec)
that takes more than 10 s to listen again falls back as with no engine, as it does today. `test_a_call_past_the_bound_fails`
covers both rules and fails with either one removed (checked). Net lines outside tests and docs: about 74 of 100.
