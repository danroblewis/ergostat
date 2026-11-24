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

## Where it stopped

Round 1: written. docs/proposals/control-aware-estimates.md settles the nine. Its tables come from the spike
tests/test_control_spike.py (121 lines of code; it runs only when named:
`uv run python scripts/named_tests.py tests/test_control_spike.py`, 220 s here). It changes no code: no Flags.control
stub was added, because the proposal recommends against coupling and a flag that does nothing would claim more
than the code does.

- Done 1: the nine are settled, the bar is given as numbers (§8), and the reproducing command is named.
- Done 2, **narrowed**: the gate's cost (378 µs a Shadow pass, 26 µs the two take gates alone) was measured on the
  factory's own model, and the events per run (37,019) on the factory-size fixture, the CI stand-in. No copy of the
  factory record is in this container, so nothing was measured on the copied record. The build's §8.3 runs the
  backtest on such a copy, by the coordinator.
- Done 3: on the gated record, two-way coupling equals measured concurrency estimate for estimate (MAE 409 min,
  coverage 0.93), and stationary availability gets 820 min and 0.50. The proposal recommends not coupling, says why,
  and amends the build to the gate's admission limit worked out once at now.
- Done 4: the owner's question is one sentence at the end.
- Decisions taken alone (reversible): the machine's headroom is moved by one per session while the limit at now is
  searched for, because with it held the factory's gate is closed for every count. The build gap's flag ships off
  until its bar passes.
- Found, outside this gap (not fixed): on the factory-size fixture, today's model makes 147 runs in 121 s, so within
  eta.BUDGET (5 s) it makes about 6 runs, fewer than FEW, and no p90 is said.
- Tests run: tests/test_control_spike.py (2 passed, by named_tests). ruff is clean. No page or shipped code changed,
  so no other suite was run here.
