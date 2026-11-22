# one-phrase-for-how-far-off: Outside Blocks, how far a goal is from its bound is said in one phrase from one function

depends-on: []

Problem (R11 piece 5): the same goal reads 'desired = 0: excess 37', 'setpoint ≤ 0 (off by 36)' and 'error −36' on three surfaces (shots/story-6-g1-home.png, infod-tf-loops.png, ixdb-job-sd-open.png). Filed Q23 makes the bound's writing uniform; the distance from it is still worded three ways. In Blocks 'e = -36' is the discipline's form and stays.
Change: one server function words the distance for every non-Blocks surface from the goal's bound kind and error: 'off by 36 tickets' (past a ≤ or ≥ bound), '28 short of 180' (below a setpoint), '12 over 80%' (above), 'within its band' (inside a band), with the unit and filed Q82's number words; the goal's state carries the phrase (`off_by_words`; it joins the goal row's fields when goal-row-one-renderer has landed). The Goals page, the side list, the Dynamics gap, the evidence's first line and attention entries print it; Blocks keeps e with its sign. No page code formats an error itself.
Definition of done:
1. On a fixture one goal's distance reads the same on the Goals page, the Dynamics side list, its gap and its evidence panel.
2. In Blocks the same goal still reads 'e = ...'.
3. A unit test covers ≤, ≥, setpoint with band, and a goal with no unit.
4. grep finds no 'excess' or 'off by' string built in pages.js, diagram.js, dynamics.js or details.js.
Files: ergostat/state.py (the phrase), ergostat/dynamics.py, ergostat/web/static/pages.js, diagram.js, dynamics.js, details.js, tests.
Acceptance tests: the unit test; a browser agreement check on the fixture.
Budget: 50 net lines.

Milestone: r11-one-word-each. Owner items: R11 piece 5. From the owner's list and the design review of 2026-11-22.
