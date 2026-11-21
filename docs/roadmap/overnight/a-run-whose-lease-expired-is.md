# a-run-whose-lease-expired-is: confirm the lease kill on main; SPEC §9.5 names the `cancel` signal a daemon-held run gets
depends-on: []

## The gap (as found on main)

Main already has everything the GAPS entry asks for: branch `leasekill-only` (5fa37de, merged as a09c176). **No code changes in this branch.**
- `ergostat/leases/kill.py::kill` / `_stop`: when the lease watchdog's expiry took effect and the holder is a run this engine started that is still going, `reap.stop(proc.pid, grace=g, also_group=True, also={proc.pid})` sends SIGTERM to the run's process group and every process under it, then SIGKILL after `grace()` (`ERGOSTAT_KILL_GRACE`, read at each kill; 10 s when unset, not a number, negative or ≥ 3600). It then records `ergostat.run.killed` with `run`, `item`, `fence`, `why`, `signal`, `pids` and `grace`. The run ends as any run does (`agent.failed`, note `killed: ...`, resources and cost measured), and its item is taken again.
- A run a daemon holds is sent `cancel` instead (`eng.daemons.cancel(..., killing=True)`), recorded as `ergostat.run.killed` with `signal: cancel`. SPEC §9.7 *Cancel* (around line 2348) says so.
- Tests: `tests/test_lease_kill.py` (10 tests), `tests/test_leases.py` (line 362), `tests/test_daemons.py` (line 285).

What is still wrong: SPEC §9.5 *Fencing* (around line 2143) lists `signal` as "TERM or KILL" only. That claim is narrower than the code, which also records `cancel` (lesson-8).

## Definition of done

1. **SPEC §9.5 *Fencing*.** The sentence that lists the fields of `ergostat.run.killed` says `signal` is `TERM` or `KILL`, or `cancel` for a run a daemon holds. It links §9.7 (*Cancel*) for what happens to that daemon. No other sentence in SPEC changes.
2. **`docs/GAPS.md`.** The entry for this gap stays "done, 5fa37de, `leasekill-only`" and is not reworded. Every file it names or implies exists on main: `ergostat/leases/kill.py`, `tests/test_lease_kill.py`, and SPEC §9.5 *Fencing*.
3. **No file outside `docs/SPEC.md` and this definition file changes.** `git diff --stat main...` shows only those.
4. **The existing tests pass on the branch, unchanged.** The acceptance tests below, then the unit suite and the four browser files, rc 0, no page test skipped for want of a port. Ruff is clean. origin/main is merged in and the suites are run again (lesson-7). Any failure in a test this branch did not touch is reported by name, not fixed here (lesson-13).

## Files to touch

- `docs/SPEC.md` (§9.5 *Fencing*, one sentence)
- `docs/roadmap/overnight/a-run-whose-lease-expired-is.md` (this definition)

## Risks

- **lesson-8 (a claim wider than the code):** the new SPEC wording could claim more than the code does, for example that a daemon's run is signalled, or that `cancel` is followed by a SIGKILL of the run itself. It must say only what `kill.py` records (`signal: cancel`) and leave the rest to §9.7. Guard: `tests/test_daemons.py`, the test at line 285, asserts `signal == "cancel"` for a daemon-held run, and `tests/test_lease_kill.py::test_an_expired_run_is_killed_with_its_children` asserts `signal == "TERM"` for an ordinary run.
- **lesson-13 (staying inside the gap):** a lease-timing test may fail under load. `tests/test_leases.py` and the parked `leaserenew` gap in GAPS (around line 224) are known places for this. Such a failure is reported, not fixed in this branch.
- **lesson-9 (a test that can't fail):** no new tests are added. The reviewer can check that the existing guards can fail: with `_stop`'s `reap.stop` call removed, `test_an_expired_run_is_killed_with_its_children` fails (its children stay alive). With `grace()` returning a negative value unchecked, `test_the_grace_is_read_at_each_kill_with_a_safe_fallback` fails. The implementor reports whether they ran these mutations.

## Acceptance tests

- `tests/test_lease_kill.py::test_an_expired_run_is_killed_with_its_children`: TERM to the tree, including a child in its own session; `ergostat.run.killed` with item, fence, why and pids.
- `tests/test_lease_kill.py::test_a_run_that_ignores_term_is_killed_after_the_grace`: `signal: KILL` after the grace.
- `tests/test_lease_kill.py::test_a_renewing_run_is_not_killed`
- `tests/test_lease_kill.py::test_the_killed_runs_item_returns_and_its_cost_is_recorded`: the item is taken again and done; `agent.failed` has resources and cpu; the lease is not ended twice.
- `tests/test_lease_kill.py::test_a_run_this_engine_did_not_start_is_not_signalled`
- `tests/test_lease_kill.py::test_the_grace_is_read_at_each_kill_with_a_safe_fallback`
- `tests/test_lease_kill.py::test_an_expiry_judged_before_a_renewal_landed_is_refused`
- `tests/test_lease_kill.py::test_a_renewal_recorded_between_the_look_and_the_expiry_is_not_killed`: the competing write lands in the gap (lesson-1).
- `tests/test_daemons.py`: the test asserting `signal == "cancel"` for a daemon-held run (around line 285). This is the guard for the new SPEC sentence.
- The unit suite and the four browser files, rc 0, no page test skipped; ruff clean; run again after merging origin/main.

## Size budget

0 net lines outside `tests/` and `docs/`. Any code change is an overrun and needs a written reason.

## Notes from the plan review (answer each)

- lesson-9: running the mutations is optional ('reports whether they ran'). Make it required, and add the mutation that guards the only change in this branch: make kill.py record something other than `cancel` for a daemon-held run (or skip the record) and show the test_daemons.py guard fails. Report each mutation's result.
- Name the test_daemons.py guard by its function name, not 'around line 285', and find the §9.5 sentence by its text, not by line number, so both still hold after origin/main is merged in.
- lesson-6/lesson-8: the new sentence leaves the daemon case to §9.7. Check that §9.7 *Cancel* actually says what `cancel(..., killing=True)` stops (the daemon's step or its child processes) and that a test backs it. If §9.7 claims more than a test shows, report that as a finding for its own gap; don't fix it here (lesson-13).
