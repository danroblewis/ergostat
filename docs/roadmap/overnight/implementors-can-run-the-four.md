# implementor-browser-suite: the implementor environment can run the four browser files
depends-on: []

## Definition of done
The implementor session environment (container or worktree) has Playwright and its browser installed, so the four browser files the house rules require (unit suite plus four browser files with rc 0 and no page test skipped) run there through the shared slot script and under scripts/suite_watch.py. A missing browser is a stop with a clear message before the round starts, not a skip. Seen as: gap/light-theme-the-repeats-toward-the-paper-are-low-in-contrast parked after three rounds that could not run the browser tests, breaks or screenshots for want of Playwright.

## Acceptance tests
- tests/test_agents.py::test_implementor_environment_has_a_browser (fails when Playwright or its browser is missing from the implementor image)
- tests/test_agents.py::test_missing_browser_stops_the_round_rather_than_skipping

## Size budget
40 net lines outside tests and docs.

## Where it stopped
Round 1, built; what was found, decided alone, and not run.

- **What was missing.** The agent image already had Playwright 1.63.0 and Chromium (it is built `FROM` the dev
  image, which installs both into /opt/ms-playwright and caches the package for `uv run --with` offline). What was
  missing was permission and wiring. The session was allowed only `uv run python -m pytest`, so the browser files hit
  `importorskip` and skipped (seen in this session: `SKIPPED ... No module named 'playwright'`). Also, the round's
  fast suites ran ruff and unit only.
- **Built (all in dev/; 0 net lines outside tests, docs and dev):** the implementor may run
  `uv run python scripts/suite_watch.py -- uv run [--with playwright==1.63.0] python -m pytest ...`
  (dev/bin/agents.py TOOLS). `[suites] browser_ready` (dev/factory.toml) launches Chromium once. Before the session,
  implement.py runs it in a suite container of the agent image, through the suite slot (`agents.browser_ready`). If
  it fails, or the setting is missing, `Refused` stops the round: the gap is given back uncounted, with "no browser:
  ... rebuild ...", and no session starts. The round's fast suites are now ruff, unit and browser (dev/bin/onmain.py
  FAST). A browser test skipped fails them, as in the queue. A failing browser test is triaged like a unit test,
  rerun alone and on main with `[suites] rerun`.
- **Decided alone (reversible):**
  - Adding the browser files to the implementor's per-round fast suites (about 6 more minutes a round, inside the
    slot). This is how "run there through the shared slot script" is met. Undo: one tuple, `onmain.FAST`.
  - The stop is an uncounted give-back retried after an hour, the same as a missing session token. It is not a park:
    the gap is not at fault.
  - The session's own runs of the browser files are under suite_watch inside its container's hard limits, not through
    the host's slot, which cannot be reached from inside the container. The factory's runs after the session go
    through the slot.
  - No build-time launch check was added to dev/agent/Dockerfile (Docker could not be run here to prove it builds);
    the round's check covers it at run time.
- **Broken on purpose (lesson 9), each seen failing:**
  - `browser_ready` never raising
  - a skip not counted as a failure
  - the session's browser command removed from TOOLS
  - `PLAYWRIGHT_BROWSERS_PATH` pointed at an empty folder (the real launch fails)
- **Not run by the implementor:** the four browser files themselves, and the whole unit suite under suite_watch. This
  session was started with the old permission list, so the browser command was refused here; the change takes effect
  from the next session. Run: tests/test_agents.py (2 passed; the first really launched Chromium here) and
  tests/test_factory*.py (115 passed, 2 skipped: the Docker-only tests, as on main). Ruff is clean. The branch was made
  from main this round; the clone has no remote, so origin/main could not be fetched again.

Round 2, fixed; every finding of both reviews answered.

- **Blocking (review 2), manage.py on_main:** reapprove of a fast-suite failure now runs the tests on main with the
  failed suite's own rerun, `onmain.AGAIN[fast['failed']]` (a browser test: `rerun`, with Playwright; else `alone`),
  and logs under that suite's name. Test: tests/test_factory_manager.py::
  test_reapprove_runs_a_browser_failure_on_main_with_playwright (with `alone` passed again, it fails: reapproved).
- **Review 1, skips under `rerun`:** agents.suites counts skips for `rerun` too, so a browser test that skips when run
  again alone is no flake and no pass on main. Test: tests/test_agents.py::
  test_a_browser_failure_that_skips_alone_is_not_a_flake (with `rerun` not counted, it fails: flake.seen).
- **Review 1, room():** the rerun's estimate is the failed suite's seconds (browser or unit), not always the unit
  suite's. Test: tests/test_agents.py::test_a_rerun_is_timed_by_the_suite_that_failed (with the unit suite only, it fails).
- **Review 1, not run:** still not run here, and not by choice. This session refused
  `uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python -m pytest ...` again. The likely
  reason: the session's permissions come from the running factory's agents.py (main's), not this branch's, so the
  new TOOLS line takes effect only once merged. The four browser files and the whole unit suite under suite_watch are
  owed to the factory's fast suites and the queue. Run here: tests/test_agents.py (4 passed),
  tests/test_factory.py (57 passed, 2 skipped: Docker-only, as on main), tests/test_factory_{resources,sessions,
  knowledge,manager}.py (81 passed). Ruff is clean on ergostat, tests, scripts and dev/bin. origin/main could not be
  fetched again (no remote in the clone).

Round 3, fixed; main (278666f7) merged in first.

- **Merge of main:** the only conflict was implement.py's docstring. It keeps main's stray-file step and the branch's
  browser files. Main's new `fast_seconds` (times.py's gate `fast`) now sums every suite in `onmain.FAST`, browser
  included, not only ruff and unit. dev/README.md says the same.
- **Blocking (review 2), skips under `rerun` not seen without -rs:** `[suites] rerun` now has `-rs`. agents.suites
  also reads pytest's own summary (`N skipped`), taking the larger of the two counts, so a skip still fails even if
  a command has no `-rs`. The fake reruns in test_a_browser_failure_that_skips_alone_is_not_a_flake and the manager's
  reapprove test now print only `1 skipped in 0.01s`, which is what the real command prints without -rs.
  test_implementor_environment_has_a_browser asserts that the real factory.toml's browser and rerun both carry ` -rs `
  and that rerun pins Playwright. Broken on purpose, and each failure seen: the summary regex disabled (the flake test
  fails with flake.seen) and `-rs` taken out of rerun (the environment test fails).
- **Not run here:** the four browser files and the whole unit suite under suite_watch, for the same reason as
  round 2. Run here: tests/test_agents.py (4 passed), tests/test_factory_manager.py (19 passed),
  tests/test_factory.py with tests/test_factory_times.py (73 passed, 2 skipped: Docker-only, as on main). Ruff is
  clean on ergostat, tests, scripts and dev/bin.
