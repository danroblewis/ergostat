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

## Where it stopped

Built (round 1), +10 net lines outside tests (28 added, 18 removed).

- Blocks: a one-sided goal's reference is drawn `r ≤ 0` (its fn value is the goal's hold, `≤ 0`; a two-sided one stays
  `= 0.93`), its MathML is `r ≤ 0`, and its panel says "a limit: r ≤ 0 … the error e = r − y counts only past it: 0
  inside the limit", with a `limit` row instead of `holds`. A two-sided reference says "a setpoint". These words are
  made in `ergostat/blockdiagram.py`, not in a file under `ergostat/web/`, so that file had to change too.
- The relay (an `onoff`/compare/alarm/timer block) says "an ideal relay" and is drawn with one step (`M2,18 H14 V5 H26`)
  when it switches on and off at one threshold. It says "a relay with hysteresis", keeps its two-step loop and its
  "releases at" row when it has a band: an `until` different from the hold, or a goal tolerance (the status turns off
  past hold + tolerance and holds again only within the hold).
- Controller panel and Loops: `holdText` (util.js) writes "limit ≤ 20" or "setpoint 0.93 ±0.01". The loop panel's
  "holds" row reads "worked, limit ≤ 0", and its error row reads "0: within its limit (e counts only past it)". The Loops
  column header "setpoint" is now "r", because each cell names itself. A limit's zero error shows ", within", and the
  cell's title explains it.
- Choices made without asking (the most reversible ones): "its panel" in the acceptance check is read as the reference
  input's panel. The controller panel's fixed explanation ("compares … with the setpoint r") is left as it is.
  Identified external on-off laws (numbers/extlaw.py) still report the hysteresis measured from the record: they are
  estimates, outside this gap.
- Tests: `tests/test_diagram_rendering.py::test_a_one_sided_limit_is_drawn_and_named_as_a_limit` (new, on
  ticket-factory `view=blocks&system=making`, plus the controller panel and /loops) passes. Three breaks were each seen
  to fail it: the Loops cell back to `op(...)`, the ideal-relay glyph back to the hysteresis loop, and the fn value back
  to `= 0`. In `tests/test_blockdiagram.py::test_a_reference_is_a_value_and_the_relay_says_its_threshold`, the old
  assertion (`= 0`, no `≤`) was the behaviour this gap reverses and has been rewritten. It now also checks
  software-factory's ideal relay and file-queue's banded relay, and the file passes (67).
- The whole of `tests/test_diagram_rendering.py`, serial under the watchdog, ended rc 1: 196 passed, 5 failed. Four of
  the failures are already reported as failing on other branches' reviews: routing time for coordinator and
  image-squeeze, `test_a_big_tangled_model_lays_out_in_time_and_cleanly`, and the equation test's 'Nothing waiting.'.
  The fifth, `test_a_valve_turns_upright_when_its_pipe_runs_up` (image-squeeze's Dynamics view, system=lab, valve pipe
  attachment), also fails when run alone. It draws only the Dynamics view, which reads none of the changed code. I
  could not show that it fails on main as well: putting main's `ergostat/` in the tree to rerun it was refused in this
  session, so the merge queue should confirm it on main. Not run here: the unit suite and the other three browser
  files (left to the factory).
