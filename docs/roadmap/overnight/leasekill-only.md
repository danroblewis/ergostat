# leasekill-only: a run whose lease expired is killed

Branch `leasekill-only`, from main at 448f546. Gap (`docs/GAPS.md`): *Should a run whose lease expired be killed?*
(the owner decided yes, 2026-11-18). Split from `leasekill`: the warm processes (`takes: {warm: N}`) failed their
gate twice and are parked on branch `warm` (its definition file says where they stopped); this branch carries only
the lease kill for ordinary runs, as reviewed sound.

## Definition of done

When the engine's lease watchdog expires a lease (`ergostat.lease.expired`), reads the lease again and finds that the
expiry took (not renewed meanwhile), and its holder is a run this engine started that is still going, it stops the
run's process tree: SIGTERM to the run's process group and every descendant (`library/reap.py`), then SIGKILL after a
grace (`ERGOSTAT_KILL_GRACE`, read at each kill, 10 s when unset or not a number) to whatever is left, skipping the
KILL pass once the tree is gone, and records `ergostat.run.killed` (about the block; `run`, `item`, `fence`, `why`,
`signal`: TERM or KILL, `pids`, `grace`). The run ends as it does today: `agent.failed` with its note (killed: its
lease expired), its resources and cost measured as for any run; its lease is not ended again; its item is back where
the expiry put it and taken again. A run whose lease is renewed is never killed. Runs this engine did not start are
not signalled. SPEC §9.5 (*Fencing*), the dispatcher's docstring, an agent guide line and GAPS say so.

## Acceptance tests

- `tests/test_lease_kill.py::test_an_expired_run_is_killed_with_its_children`
- `tests/test_lease_kill.py::test_a_run_that_ignores_term_is_killed_after_the_grace`
- `tests/test_lease_kill.py::test_a_renewing_run_is_not_killed`
- `tests/test_lease_kill.py::test_the_killed_runs_item_returns_and_its_cost_is_recorded`
- `tests/test_lease_kill.py::test_a_run_this_engine_did_not_start_is_not_signalled`
- `tests/test_lease_kill.py::test_the_grace_is_read_at_each_kill_with_a_safe_fallback`
- `tests/test_streamed_output.py::test_a_fenced_runs_later_lines_are_refused_at_once` (still refused, while stopping)
- the four suites, rc 0, no page test skipped.

## Size budget

600 net non-test lines (outside `tests/` and `docs/`); expected about 60.
