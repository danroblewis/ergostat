# switch-drain: an approved switch drains the runs under way instead of killing them, and older switch requests are withdrawn

depends-on: []

Today `switch-instance` stops the engine at once (live.py switch), which kills every session under way (9 implementors
at a time now), so the coordinator holds switches for a quiet moment that never comes. And each green merge asks its own
switch: older ones stay waiting in the inbox after a newer version supersedes them.

## Definition of done

- **When it switches** (owner: "daily or something, or when load is low enough"): an approved, newest switch waits for
  a **quiet moment** - at most `[upgrade] quiet_runs` (default 1) AI runs under way - or, at the latest, the **daily
  window** (`[upgrade] daily_at`, default 04:00 local), whichever comes first; then it drains as below. The
  coordinator may approve switches standing (an approval policy for `switch-instance` of the newest version), so
  upgrades run without a person once the health check and revert have proven themselves.
- An approved switch first **drains**: the AI blocks take no new item (a drain flag the dispatch reads), the runs under
  way finish or reach a bound (`[upgrade] drain_minutes`, default 45), then the switch runs as today (health check,
  revert). Runs still going at the bound are stopped as today, and each is given back uncounted (not a failure of its gap).
- A switch asked for a version older than one waiting, or than the one running, is **withdrawn** from the inbox
  (its action closed, saying which version supersedes it); only the newest waits.
- The drain and the switch are drawn in the model (a drain state, its time measured with a goal) and shown by `status.py`.

## Acceptance tests

- `tests/test_factory.py::test_a_switch_waits_for_the_runs_under_way`
- `tests/test_factory.py::test_a_drain_past_its_bound_gives_the_runs_back_uncounted`
- `tests/test_factory.py::test_an_older_switch_request_is_withdrawn`
- `tests/test_factory.py::test_a_switch_waits_for_a_quiet_moment_or_the_daily_window`

## Size budget

200 net lines of code outside `tests/` and `docs/`.
