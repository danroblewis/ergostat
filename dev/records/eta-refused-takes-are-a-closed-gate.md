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
