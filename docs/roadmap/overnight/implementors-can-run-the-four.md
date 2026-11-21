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
