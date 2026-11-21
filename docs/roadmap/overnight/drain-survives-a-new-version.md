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
