# drain-survives-a-new-version: a version installed during a drain does not cancel that drain

depends-on: []

Seen in the first real drain, 2026-11-21. `step()` in `dev/bin/drain.py` treats the newest waiting upgrade as the target. When a merge lands during a drain and its version is installed but not yet approved, the draining upgrade is withdrawn in favour of it, the newest is still `installed`, and the step removes `run/drain.json` and returns "no switch approved". The drain is lost. A drain can last 45 minutes and the factory merges every 15 to 20, so on a busy factory an upgrade might never finish without someone approving each new version in time.

## Definition of done
1. While a drain is under way (`run/drain.json`, no `switch_started`), a newer version that is only `installed` neither withdraws the draining upgrade nor removes the flag. The drain goes on to switch to the version it is draining for.
2. A newer version that is already approved during the drain still takes over the drain, as today, keeping its start time.
3. After the switch, the newer version is still waiting as `installed`, with its switch request open.
4. Versions older than the one draining are withdrawn as today.

## Files to touch
`dev/bin/drain.py`, `tests/test_drain.py` (or the file that holds the drain's tests).

## Risks
- Test through the real `step()` with real upgrade items, in the order install, drain, newer install, step, not with a stand-in for the choice of target.
- lesson-3: when the order of two versions cannot be told, say so and switch neither, as today.

## Acceptance tests
- a newer installed version leaves the drain and its flag in place
- the drain then switches to the version it was draining for, and the newer one still waits
- a newer approved version takes over the drain with its start time

## Size budget
25 net lines of code outside `tests/` and `docs/`.

## Where it stopped
The build is in df484bb5: `dev/bin/drain.py` step() keeps a drain under way when the newest is only installed, and
the three acceptance tests are in tests/test_factory.py. After it, the factory's `unit` run (`-n 8`) was reported
failed, but the tail it gave ends at 77% with no failing test, no error and no summary line, so it reads as a run cut
short (killed or timed out), not as a test that failed. Run again here, one file at a time: tests/test_factory.py
(every test that uses drain.py or run/drain.json is there) had 119 passed, 2 skipped; tests/test_architecture.py
had 9 passed. Nothing else in tests/ imports drain.py or reads the dev/README.md text this branch changed. The whole
unit suite could not be run here (the command was refused), so the cause of the cut-short run is not known. Left
open: run `unit` again under the watchdog and, if a test fails, name it. No code was changed in this round.

Second report of `unit` failing: this tail has one `F` at about 60%, but no test name, no traceback and no summary
line (the output ends at 80%). The paragraph above, which said the tail held no failing test, described the first
tail only; for this run, a test did fail. Which one is still not known. Checked here: the only test files that use
drain.py or run/drain.json are tests/test_factory.py and tests/test_factory_resources.py (`cleanup.WAITING ==
drain.WAITING`). tests/test_factory.py had 119 passed, 2 skipped, alone and again under the watchdog with `-n 8 --dist
worksteal` (rc 0). tests/test_factory_resources.py had 10 passed and tests/test_code_health_coverage.py 11 passed.
ruff is clean. The whole unit suite, run alone or under suite_watch, was refused as a command here, so the failing
test could not be named. With no failing test to point at, nothing in drain.py was changed: a guessed fix would be
outside the gap (lesson-13). Left open: the factory's unit run with `-rfE` (or its full output), to name the test,
and then either fix it here if this branch caused it or report it as unrelated.

Round 2, on e8e97867 (main 313f147b merged in): the whole unit suite ran here this time, under the watchdog exactly as
[suites] unit gives it, plus `-rfE` (`uv run python scripts/suite_watch.py -- uv run python -m pytest -q -n 8 --dist
worksteal -rfE`): 2475 passed, 69 skipped, 1 xfailed in 631 s, rc 0, no failure. So the earlier `F` did not happen
again in a full run on this branch. With no traceback for it, it is still not named. Because it did not come back, it
reads as a load-dependent flake elsewhere, not as something drain.py caused (lesson-10/13), but that is not proven.
ruff is clean. Lesson-9, checked here: with `keep` switched off in step() (the code as on main), the first two
acceptance tests fail (an extra `upgrade.withdrawn`). With `keep` widened to cover an approved newer version too, the
third fails (the drain is not taken over). With the line restored, the tree is identical to the commit. No code was
changed in this round. Not run here: the four browser files and demo_check (no example was touched). Left to the
factory: its own unit and browser runs.
