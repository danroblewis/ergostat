# fastsuite: the suites in a fraction of the time, nothing lost

Branch `fastsuite`, from main at 2ed2f16. Size: test infrastructure.

## The gap

Every branch and every merge in the queue runs the unit suite (`uv run python -m pytest -q`, about 11 minutes
serial) and the four Playwright files (`tests/test_diagram_rendering.py`, `test_page_polling.py`,
`test_items_page.py`, `test_page_refresh.py`, about 20 minutes). They are the bottleneck for every agent and for
the merge queue.

## Done when

Both suites run in parallel with pytest-xdist (a dev dependency), with the same tests collected and none weakened:
no time bound raised, no assertion loosened, no test skipped or deselected. Tests that cannot share the machine
(shared state, fixed paths, timing that only holds unloaded) are kept whole and run in a serial group
(`xdist_group`), each with its reason. The worker count is capped so that a full parallel run of either suite stays
safely under the machine limits (1,500 threads, 6 GB total), measured by a watchdog that samples the run's whole
process tree (pytest workers, the engines and page servers they start, the browsers) and kills it past the limits.
The unit suite passes five consecutive full parallel runs, and the browser suite passes in parallel with no
skips. `CLAUDE.md` (working here) and the overnight plan's gate text give the new standard commands, and the old
serial ones as the fallback.

## Acceptance

- `uv run python -m pytest -q -n <N>`: green five times in a row, same number of tests as serial.
- `uv run --with playwright==1.63.0 python -m pytest -n <M> tests/test_diagram_rendering.py
  tests/test_page_polling.py tests/test_items_page.py tests/test_page_refresh.py`: green, no skips.
- `scripts/suite_watch.py` around each: peak threads and RSS recorded below, under the limits.
- Report: serial and parallel wall time for both suites, peak threads and memory, the five runs, the serialised
  tests and why, and the machine's load while measured.

## Size budget

300 net lines of code outside `tests/` and `docs/` (the watchdog script, pyproject).

## Where it stopped

Done. Measured on the 28-core, 256 GB Mac Studio while other agents ran their suites (load average 3 to 14; each
figure says its load). Peak threads and RSS are the run's whole process tree as `scripts/suite_watch.py` samples it
(RSS summed over processes, so Chromium's shared pages count more than once: an overestimate).

| Suite | Serial | Parallel | Peak threads | Peak RSS | Largest worker |
|---|---|---|---|---|---|
| unit (1,457 passed, 12 skipped) | 703 s (load 3-5) | 136 s, `-n 8 --dist worksteal` (load 9-13) | 351 | 2.2 GB | 1.1 GB |
| browser (193 passed, no skips) | 1,250 s (load 4-7) | 329-334 s, `-n 4 --dist worksteal` (load 7-12) | 651 | 4.1 GB | 1.3 GB |

The serial runs peaked at 218 threads and 1.1 GB (unit), 222 threads and 1.7 GB (browser). The unit suite's floor
is `test_reload_soak` (122 s on its own), started first; more workers do not help it (`-n 12` was no faster). The
browser suite at `-n 4` is near its ideal (1,250 / 4); at 5 or more its summed RSS nears 6 GB. Run the two suites
one after the other, never together (together: about 1,000 threads and 6.3 GB).

Unit: five consecutive full parallel runs green on the final code (135, 137, 137, 137, 137 s), and five before the
rebase onto c4472b6 (126 s each, before the serial tests waited their turn).

Serialised (`@pytest.mark.serial`, run alone inside the parallel run, bounds unchanged):
- `tests/test_watchdog.py` (its stall is 1 s: a pass slowed past it by the load is taken as a stall, and the loop
  restarted twice);
- `tests/test_notify.py::test_a_run_costs_one_thread` (30 runs of 1 s must all start within that second).

Fixed instead of serialised (races the parallel run exposed):
- `runner.STOPPING`, process-wide, left set by an engine closed in the test before on the same worker: cleared before
  every test (conftest).
- `ergostat run` built its file watcher after its first runs started, so an edit made in that moment was never taken
  (`test_ergostat_run_takes_an_edit_in_place_and_stop_still_kills`); main fixed the same on `carried` meanwhile, and
  the rebase kept main's.
- The Process view's `since`/`until` were structure, so a page polling it got the whole graph whenever its poll fell
  past the one-second cache; now values (`graph_poll.TOP_VALUES`), and the test polls seconds later.
- `test_calls` read the probe's JSON while it was half written.
- Five tests asked for fixed ports (8798, 8796, 18781, 18791, 18792); now free ones from the system.
- A failing page test left its page open (a run with many failures grew past 6 GB on modelling-core): the conftest
  closes a page test's contexts whatever its outcome (`test_a_failing_page_test_releases_its_pages`), and the
  watchdog kills a single worker's tree past 2 GB.

Size: 120 net lines outside `tests/` and `docs/` (`scripts/suite_watch.py` 113, `graph_poll.py` 1, pyproject 1,
and the lock file).
