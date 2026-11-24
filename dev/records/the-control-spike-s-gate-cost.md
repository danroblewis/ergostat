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
