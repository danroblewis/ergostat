# ui-a-one-sided-limit-is-drawn-and-named-as-a-limit: A one-sided limit is drawn and named as a limit

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q66 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram Blocks; controller panel; /loops

**The problem:** 'worked-opened ≤ 0' is drawn as 'r = 0' and called a setpoint; the error column shows 0 inside the bound with nothing saying why; a relay is 'with hysteresis' though its on and off thresholds are equal.

**The change:** Label the reference 'r ≤ 0' and call it a limit in the panel and on Loops ('limit ≤ 20', 'setpoint 0.93 ±0.01'). The relay panel says 'ideal relay' unless it has a band, and the drawn glyph matches.

**User stories it serves:** G5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791 ?view=blocks&system=making the reference label of worked-opened contains '≤'; its panel contains 'limit' and not 'setpoint'; a relay whose thresholds are equal does not contain 'hysteresis'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
