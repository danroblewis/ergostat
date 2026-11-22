# ui-a-flow-with-no-value-says-why-and-an-estimate-wi: A flow with no value says why, and an estimate with no basis says so

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q79 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram Dynamics; flow panel

**The problem:** regressions, fixes, shipped and asks show a bare '–' on a live diagram; rates keep a value with nothing in flight; 'work-time 40m ± 2d' and 'Nothing says the value written is wrong' beside 0.404 ± 0.116 against a declared 2.

**The change:** A flow that did not move in the window shows '0' with 'no movement in 33m' in its panel; one that is not measured shows 'not measured'. An interval wider than ten times its estimate prints 'not enough record yet'. When the declared value lies outside the interval say 'the record so far rejects 2 but cannot yet settle a value'.

**User stories it serves:** B5, C6

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796 ?system=product no flow label is a bare '–'; the churn panel does not contain 'Nothing says the value written is wrong' while the declared value is outside the estimate ± 3σ; no panel shows an interval more than ten times its estimate.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
