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

## Where it stopped

Built, round 1. Choices taken with nobody to ask (each the more reversible one):
- The clause's words are made in Python (`etacheck.said`), carried as a fifth key `said` beside {coverage, items,
  mae, since}, so tests/test_eta.py can check the note's text; relations.js only draws it and picks the ink.
- The kind is named in each clause by its name plus "s" ("8 in 10 tickets"); the share is rounded down.
- "Per kind asked" is one calibration per (model, kinds asked) worked out together, since the kinds share capacity in
  the simulation; it is stamped when begun, so it runs at most once an hour; a failed one keeps the last one worked out.
- The worker does the calibration only when no estimate waits, so the estimates are never held up behind it.
- Cuts: 7, 5¼, 3½ and 1¾ days before now; 5 s of runs per cut (`etacheck.BUDGET`).
- A page test was added to tests/test_items_page.py (outside the Files list) for done item 2: the clauses are drawn by
  item and by lanes, and only the poor one is in the warning ink. style.css has one selector changed so the note is
  still hidden when empty.
Overrun reason: about 100 net lines against 80: the per-kind split of the score (the tally kept per kind as well as in total), the worker's own calibration queue run when idle and its hourly stamp, and the clause's words in Python so the acceptance test can read them.
