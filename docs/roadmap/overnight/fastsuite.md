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
