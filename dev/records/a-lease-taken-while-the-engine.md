## Entry

section: Done recently

- **A lease taken while the engine closes outlives the close** (done on `factory/a-lease-taken-while-the-engine`;
  found by `tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth`; SPEC §9.5,
  `docs/roadmap/overnight/a-lease-taken-while-the-engine.md`): `Dispatcher.take` checks the engine's own stop and
  counts the take in `Engine.running` under the lock `close()` sets the stop under, and gives back uncounted a take
  whose write raced the stop, starting no run; a process `run_block` starts once this engine is stopping is killed
  (keyed on its own stop, not `runner.STOPPING`); `close()` gives back every lease it still holds before
  `ergostat.stopped`, each ended once (`finish` reads and writes under `Dispatcher.lock`). Left as it was:
  `runner.kill_all()` still kills every engine's runs already in `runner.LIVE`, and `STOPPING` stays set after one
  engine closes. Six window tests in `tests/test_leases.py`, beside main's own for the same race.
