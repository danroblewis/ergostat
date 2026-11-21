# implementor-browser-suite: the implementor environment can run the four browser files
depends-on: []

## Definition of done
The implementor session environment (container or worktree) has Playwright and its browser installed, so the four browser files the house rules require (unit suite plus four browser files with rc 0 and no page test skipped) run there through the shared slot script and under scripts/suite_watch.py. A missing browser is a stop with a clear message before the round starts, not a skip. Seen as: gap/light-theme-the-repeats-toward-the-paper-are-low-in-contrast parked after three rounds that could not run the browser tests, breaks or screenshots for want of Playwright.

## Acceptance tests
- tests/test_agents.py::test_implementor_environment_has_a_browser (fails when Playwright or its browser is missing from the implementor image)
- tests/test_agents.py::test_missing_browser_stops_the_round_rather_than_skipping

## Size budget
40 net lines outside tests and docs.
