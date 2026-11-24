# control-spike-passes-on-main: tests/test_control_spike.py::test_gate_cost_per_event fails on main whenever it is named
depends-on: []

The spike (5981d76e, gap/control-aware-estimates-proposal) runs only when its file is named (the _named_only fixture), but the main-broken check reruns failed tests by name, so it does run there. It failed on main b9341591 and fa51005d (intervention/main-broken-b9341591cb70, -fa51005d0951) and holds gap/forecast-promise-proposal in fix. When named it runs eta.simulate(runs=200, budget=120) over the factory-size fixture (220 s alone, says its record), so under load or a suite limit it fails for reasons that have nothing to do with the code it measures.

## Definition of done
1. Say why it fails on main (an assert, a timeout, a fixture missing in the container), with the traceback from a named run on main.
2. Either it passes on main by name within the suite limits, with N and the simulate budget cut so that a named run takes under 60 s, or the spike leaves tests/ and goes to scripts/ (run the same way, and the proposal's docs say where). Either way, no gate can name it and see it fail on main.
3. No ergostat/ code changes.

## Acceptance tests
- `uv run python scripts/named_tests.py tests/test_control_spike.py` passes on the branch in under 60 s (or the file is gone and scripts/control_spike.py runs and writes /tmp/control-spike-*.json).
- tests/test_control_spike.py::test_gate_cost_per_event is not reported failing on main by the main-broken check.

## Size budget
40 net lines

## Where it stopped

Built (round 1). 0 net lines outside tests/, docs/ and dev/; no ergostat/ change.

1. Why it fails on main: not a timeout or a missing fixture, but an AttributeError, the same on every named run. A
   named run on main (this branch at 86009b51 before its change: main plus this record), `uv run python
   scripts/named_tests.py tests/test_control_spike.py::test_gate_cost_per_event`, failed in 34 s:

       tests/test_control_spike.py:64:            sh.step(1_800_000_000.0 + 60 * k)
       ergostat/numbers/closedloop.py:187: in step    self.goals(now, out=events)
       ergostat/spec/engine.py:353:   held = self.per.get(name) if g.per else None
       E           AttributeError: 'Shadow' object has no attribute 'per'

   `closedloop.Shadow` borrows `Engine.goals`, which since goals held per item (SPEC §8, `per:`) reads `self.per`.
   Shadow never sets it, and the factory's own ergostat.yaml now has such a goal. That is an ergostat bug: any Shadow
   (closed-loop what-ifs) on a model with a `per:` goal raises the same way. Done item 3 rules out fixing it here, so it
   needs its own gap (set `per = {}` in `Shadow.__init__`, or work the per-item goals out, with a test).
2. Kept in tests/ (the smaller and more reversible option, and moving the file to scripts/ would count all of its
   lines against the budget). The spike sets `sh.per = {}` (none held, as the engine's is before its first pass) and
   cuts N 5000→500, the gate-cost simulate to runs=20, budget=2, the backtest to 1 seed and its `_score` simulate to
   runs=20, budget=2. Each old value is noted beside it, and the proposal's "What was measured" says the tables were
   taken with those values.
3. Timing, on this container, unloaded: the whole file passes named in 58.2 s (59.6 s and 67.2 s at earlier cuts), and
   test_gate_cost_per_event alone in about 50 s. About 30 s of that is building the factory-size record
   (scripts/factory_fixture.py), which cannot be cut without changing what is measured. Neither test asserts on time,
   so load can only make a named run slower, not fail it, unless a gate's whole-run limit is under about a minute. The
   margin under 60 s is thin: on a loaded machine the file named alone may take longer than 60 s.
4. Not run: the main-broken check itself (acceptance test 2). The reason it reported the test, the AttributeError, is
   gone: the named run passes.
