# dynamics-off-status-on-the-part: Dynamics: a goal's gap prints the goal's one word, and an off goal's gap and loop marker take the off colour, never the accent

depends-on: [dynamics-every-goal-drawn, goal-row-one-renderer]

Problem (R5 piece 8): in Dynamics nothing on the drawing says which goal is off; the reader matches names from the side list to parts. Once every goal's gap is drawn (dynamics-every-goal-drawn) the gap is the place to say it. The accent already means selection and trace (docs/DESIGN.md's colour rules, settled in diagram-line-tones), so an off goal must not use it, or a traced loop and an off goal would be the same colour.
Change: the gap auxiliary of a goal that is not holding prints the goal's `word` through goalWord (goal-row-one-renderer; no mapping of status in dynamics.js): 'off' with how far ('off by 36', the one phrase of one-phrase-for-how-far-off when present) in --bad, the marker of the goal's balancing loop in --bad too; 'no feedback' for an open goal; the neutral words (approaching, in grace) in the neutral token when they exist; holding goals stay in ink with no word. Not colour alone: the word is always printed. The gap -> flow link stays full ink. Values update with the values poll without a re-layout. The legend and the Guide frame explain the mark.
Definition of done:
1. On a fixture with off and holding goals, open=*: each off goal's gap node has the 'off' text and computes to --bad; holding goals' gaps do not.
2. The word on each gap equals that goal's `word` in /api/loops.
3. A lit (selected) loop's stroke and an off gap's stroke compute to different colours, in both themes.
4. A goal turning off between polls is marked without a re-layout (layout counter unchanged).
Files: ergostat/web/static/dynamics.js, style.css, ergostat/guide.py, tests/test_diagram_rendering.py.
Acceptance tests: a browser test for 1-4 on the fixture.
Budget: 40 net lines.

Milestone: r5-dynamics-tells-the-story. Owner items: R5 piece 8 (first half). From the owner's list and the design review of 2026-11-22.
