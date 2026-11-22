# eta-calibration-said-on-the-timeline: The Timeline says how well past estimates held: 'last week, 8 in 10 gaps finished by their p90'

depends-on: [eta-works-out-on-the-factory-record]

Problem: a Gantt is believed only if its past forecasts held. tests/eta_backtest.py measures coverage, MAE and bias by replaying past cuts of the record, but only in tests; the page gives no reason to trust 'expected Tue 14:10' and no warning when estimates are poor (e.g. coverage 0.4 on a kind whose runs changed). Needs estimates that run on the record.
Change: move the backtest's core (read at a cut with truth, simulate, score) from tests/eta_backtest.py into ergostat/numbers/etacheck.py (the test imports it). The eta worker (ergostat/web/eta_api.py) runs it at most once an hour per kind asked, on 4 cuts over the last 7 days, runs=100, within its own budget and off the request path, cached beside the estimates. merge() adds eta.calibration[kind] = {coverage, items, mae, since}. The Timeline note adds one clause per kind: 'last week's estimates: 8 in 10 gaps finished by their p90 (41 gaps)'; fewer than 10 items: 'too few finished last week to check'; coverage under 0.7: the clause in the warning ink. SPEC §5a says this.
Definition of done:
1. The calibration is worked out by the worker, never on a request: no /api/items-graph request takes longer when it is stale.
2. One clause per kind on the Timeline; warned when poor.
3. The tests use the same code path.
Files: new ergostat/numbers/etacheck.py, tests/eta_backtest.py, ergostat/web/eta_api.py, ergostat/web/static/relations.js, docs/SPEC.md, tests/test_eta.py.
Acceptance tests: on tests/test_eta.py's owners_record calibration coverage lies in [0.8, 1.0] and the note contains 'finished by their p90'; a record with 3 finished items says 'too few finished last week to check'.
Budget: 80 net lines (moved lines not counted).

Milestone: timeline-real-schedule. Owner items: 17. From the owner's list and the design review of 2026-11-22.
