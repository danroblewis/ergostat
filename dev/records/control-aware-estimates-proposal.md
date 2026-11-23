# control-aware-estimates-proposal: Proposal: completion estimates that run the control model and the stocks and flows together with the items (docs/proposals/control-aware-estimates.md)

depends-on: [eta-works-out-on-the-factory-record, eta-refused-takes-are-a-closed-gate]

Problem: the owner: 'We have a system dynamics model and a control model; a small simulation should give a real estimate of what finishes when and in what order.' ergostat/numbers/eta.py simulates items against block capacities read once at now; it knows nothing of the gates that start the blocks (the factory's implement-when: busy < min(pool, busy+room), machine-full, the AI budget goal, intake open; instance dev/model/building.yaml) or of the stocks those gates read changing over the horizon. On the factory those set throughput: pool 36 (run/pools.json) but stock.gaps-building averaged 6.1 over a day and is 1 now with 97 ready, because block.machine-full = 1. The Timeline itself says 'Not modelled: a goal that switches a block off'. numbers/closedloop.py already runs the control structure ahead on a shadow of the engine (Shadow, start_of) and is used by etamodel.gated_off only for 'off now'. It needs the estimates running on the factory record to measure anything, and the measured-concurrency model of eta-refused-takes-are-a-closed-gate as the baseline its validation bar compares against.
Change: write docs/proposals/control-aware-estimates.md settling:
1. Which control parts run inside the item simulation (expr gates evaluated through Shadow at each event or a fixed step; goals over item counts), with inputs that are item counts taken from the simulation's own state.
2. How every other input is had: kept at its newest reading, projected (simulate.project / closedloop), or driven by the items (AI spend per run, headroom per running session); the rule and how each is said in an item's why. This is the owner's one question here: keep what binds the factory's concurrency as it reads now, or project it. Default until answered: kept as it reads now, and a gap waiting on a parked gap is not scheduled.
3. Pools read from stocks that change (pool: {now: stock.X}).
4. Time coupling and the cost bound on the factory record (414 open items, 10 blocks, 200 runs); where it runs: a worker, never the web request path.
5. Whether the closed-loop risk's uncertain parameters enter the Monte Carlo.
6. One model: whether the goals' forecast (R6, goal-forecast-proposal) and the items' estimates become one projection so the Dynamics flow rate agrees with the Timeline.
7. What the Timeline and Lanes show: starts staggered by the gate, a gate's closed spans, a why naming the gate.
8. The validation bar: an ablation (Flags.control in eta.ABLATIONS) run by tests/eta_backtest.py on the factory record at past cuts (MAE of p50, p90 coverage, gaps merged in the next 24 h predicted against actual) against today's model and against the measured-concurrency model; candidate methods: stationary availability, a capacity schedule from a closed-loop projection, two-way coupling; how the record is snapshotted for a test without shipping the live record (the gated record of perf-factory-size-fixture is the CI stand-in).
9. The build split: confirm or amend control-aware-completion-estimates, with budgets.
Definition of done:
1. The proposal exists with each of the nine settled, the backtest bar as numbers and the table reproducible by a command it names.
2. A spike's measured cost of evaluating the factory's gates per event on the copied record is recorded.
3. If coupling does not improve coverage or MAE over the measured-concurrency model it recommends not coupling and says why.
4. The owner's question is asked in one sentence.
Files: docs/proposals/control-aware-estimates.md; a throwaway spike under dev/ or tests/, not shipped; at most the ablation flag stub in ergostat/numbers/eta.py and tests/eta_backtest.py.
Acceptance tests: the proposal review passes; the timing and backtest tables are in the file.
Budget: documentation; measurement code at most 150 lines.

Milestone: timeline-real-schedule. Owner items: 17 (feeds 18's Gantt panel). From the owner's list and the design review of 2026-11-22.
