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
