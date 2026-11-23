# ui-sensors-polled-alike-are-drawn-alike: Sensors polled alike are drawn alike

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q67 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram Blocks

**The problem:** In image-squeeze service 'bytes-per-mp, every 8 s' is 'H = 1' and 'quality, every 8 s' is 'H(s) = e^{-sT}, T = 8 s' with a sampler: one source, one period, two notations.

**The change:** Draw every polled sensor with a sampler and its period; draw the sampler in the muted stroke when T is negligible against the loop's time constant and print the ratio in the sensor's panel.

**User stories it serves:** G5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8793 ?view=blocks&system=service any two sensor blocks with the same period have the same main-label form and both have a sampler glyph.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 17:07).

Its runs failed past their attempts (a dead letter):
- attempt 8: ack
- attempt 9: nack exited 1
- attempt 10: nack exited 1
- attempt 11: nack exited 1

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 18:21).

Its runs failed past their attempts (a dead letter):
- attempt 9: nack exited 1
- attempt 10: nack exited 1
- attempt 11: nack exited 1
- attempt 12: nack a switch drains the runs under way (run/drain.json): taken again after it

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 19:08).

Its runs failed past their attempts (a dead letter):
- attempt 10: nack exited 1
- attempt 11: nack exited 1
- attempt 12: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 13: nack budget: $2995.61 spent in the last day; a session of up to $15.00 would pass the $3000 cap
