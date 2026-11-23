# eta-refused-takes-are-a-closed-gate: A block's refused takes are its gate closed, not runs: the estimates and the levelled pass take the concurrency the control loop allows

depends-on: [eta-works-out-on-the-factory-record, forward-pass-levelled-by-block-capacity]

Problem: once the estimates run on the factory record they still schedule 36 implementors at once, because block implementor's pool reads 36 (run/pools.json); all 151 gaps start within 6 minutes, and the levelled forward pass reads the same 36. That is still the owner's complaint. The factory itself held stock.gaps-building at a mean of 6.1 over the last day (1 now, 97 ready): the implement-when gate binds, not the pool. The record's attempts also misread the gate: of the implementor's 2,144 attempts 1,463 are uncounted give-backs (nack, count: false, put off 300 s, shorter than 30 s: the run refusing on drain or machine-full); merge-queue 744 of 870. eta.attempt() replays each as a run that holds a seat and adds rework.
Change: (a) etamodel._leases leaves uncounted give-backs shorter than MIN_RUN (30 s) out of a block's attempts; they become the block's refusals (a share of takes refused, and their put-offs). (b) etamodel.capacities (the one function of forward-pass-levelled-by-block-capacity) caps each block's lanes at its measured effective concurrency: the p90 of runs going at once while items waited in its states, sampled from the leases' taken/ended intervals over HISTORY, never above its capacity, with source text ('6 at once while items waited (the record, p90), under its pool of 36'); the simulation and the levelled pass therefore change together. (c) tests/eta_synthetic.py gains a gated record (pool 20, a gate admitting 4 at once, refusals put off 300 s) and the backtest table its column; each of (a) and (b) is kept only if it lowers MAE or raises p90 coverage there without worsening the four existing records beyond their run-to-run spread; the table and verdict go in docs/roadmap/overnight/eta.md (this may reverse its dropped Little's-law cap).
Definition of done:
1. On the gated synthetic record neither the simulation nor the levelled pass ever has more than the measured concurrency at once.
2. The owner's picture: on a copy of the factory record (and on the gated synthetic record in CI) no more gaps start in the first projected hour than the implementor's measured concurrency, in both the first paint and the simulated Timeline.
3. The p50 MAE on the gated record falls by at least a third against the current model.
4. Each block's source text names its measured concurrency when it binds.
5. SPEC §5a says how refusals and measured concurrency enter.
Files: ergostat/numbers/etamodel.py, ergostat/numbers/eta.py, tests/eta_synthetic.py, tests/eta_backtest.py, tests/test_eta.py, tests/test_precedence.py, docs/SPEC.md, docs/roadmap/overnight/eta.md.
Acceptance tests: test_eta.py::test_uncounted_refusals_are_not_runs, ::test_measured_concurrency_caps_a_gated_block, ::test_backtest_gated_record_improves; test_precedence.py::test_levelled_pass_uses_measured_concurrency.
Budget: 150 net lines.

Milestone: timeline-real-schedule. Owner items: 17. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. 66 net lines outside tests and docs (etamodel.py +60, eta.py +6), within the 150.

- (a) `etamodel._refusal`/`MIN_RUN`: an uncounted nack shorter than 30 s is out of a block's attempts and run curve,
  kept as `BlockIn.refusals` (each one's put-off; the item's put-off still applies); `eta.reasons` says the share
  refused and the median put-off. (b) `etamodel._measured`/`MEASURED`, called from `_capacity` (so from
  `capacities`, the one function): the time-weighted p90 of the block's runs going at once while any item was in
  its `takes.at` states over HISTORY; caps the lanes only when lower, with the source text of the definition; none
  when the block has no run on record (a record moved by hand) or nothing waited. The run parse moved into `_runs`
  so both read the same runs. (c) `eta_synthetic.gated_record`; table and verdict in docs/roadmap/overnight/eta.md.
- Backtest on the gated record (3 truths, 3 cuts): p50 MAE 847 → 409 min (×0.48), p90 coverage 0.44 → 0.93.
  (b) alone: 509 min, 0.95; (a) alone: worse (965 min, 0.22), so (a) is kept only with (b), where it lowers MAE.
  Said as a cost: with both, the share finished by their p50 falls to 0.04–0.11 (about half with (b) alone).
- The existing records: the owner's case and the steady records read identical inputs under both changes (pinned
  for one of each in `test_backtest_gated_record_improves`), so their rows stand. **Not run:** the ticket-factory
  demo record column, and done item 2 "on a copy of the factory record": no copy is in this container, and this
  session could run only `scripts/named_tests.py` (a scratch `uv run python` script and `rm`/`git clean` of it were
  refused; the untracked `.scratch_gated.py` at the root is that scratch file, not committed, to be deleted).
- Decision taken alone (reversible): the gated record's model gives the admitted run a working state (`doing`, by
  `ticket.started`), as the factory's gap kind has. Without one, precedence's levelled pass folds the run into
  `new`'s wait and draws `review` (the state the take hands on to) in dev's lane by its carry-forward, so 8 reviews
  "start" in dev's lanes in the first hour; that mapping is precedence's, outside this gap, and is left as it is.
- Known limit (done item 1): a lease held at the moment estimated is run whatever the cap (as before, "their lanes
  drawn too"), so a refusal in progress at that moment (its 2 s) is drawn as a run over the measured concurrency.
  The tests' cut has none; on the factory, with many refusals, one can show for a cut.
- Mutation checks: `MIN_RUN = 0` fails test_uncounted_refusals_are_not_runs (the backtest test still passes then,
  (b) alone clearing the third); `MEASURED = 0` fails test_measured_concurrency_caps_a_gated_block,
  test_backtest_gated_record_improves and test_levelled_pass_uses_measured_concurrency.
- Tests run (named_tests, serially): tests/test_eta.py (26 passed), tests/test_precedence.py (11),
  test_finished_states, test_lease_refused_cost, test_leased_workspaces (9), test_pool_now, test_take_order,
  test_graph_cli_web (83); ruff clean. No page changed: no browser file run. The unit suite was not run here (the
  factory runs it).

## Where it stopped

Parked by the factory (review/eta-refused-takes-are-a-closed-gate-1, 2026-11-23 09:35).

Done: (a) refusals (uncounted give-backs under 30 s) left out of attempts and the run curve, said in reasons; (b) measured concurrency (time-weighted p90 of runs while items queued) capping capacities, so the simulation and the levelled pass alike; (c) the gated synthetic record, backtest table and verdict (p50 MAE 847 to 409 min, p90 coverage 0.44 to 0.93, as the branch reports); SPEC §5a; all four acceptance tests present, with mutation checks reported. Left: done item 2 on a copy of the factory record (first paint and simulated Timeline: no more first-hour starts than the implementor's measured concurrency), and the ticket-factory demo record's backtest column showing no worsening. The implementor's container has neither record and cannot run the demo, so another fix round cannot close it.
