# evidence-panel-reads-as-a-runbook: A goal's evidence opens with its four lines, then the charts, then parts and prose; the remedy comes from its suggestion

depends-on: [goal-row-one-renderer]

Problem (R7 piece 7): the evidence panel is the best thing in the product (y with r, u and e on one time axis, crossings, decisions) and every reviewer said to keep it, but it answers an SRE's questions in a modeller's order and words: parts and prose first, 'Not worked out: it has no one process', the remedy elsewhere under Suggestions (shots/story-2-c1-evidence.png, story-2-c5-evidence.png, sreb-job-loop-panel.png).
Change: reorder openLoop's panel (ergostat/web/static/details.js:140 onward, control.js): (1) four lines first, each one sentence: what is wanted and where it is now (the goal's word through goalWord, bound written per filed Q23, the distance in the one phrase of one-phrase-for-how-far-off when landed); how long off against how long it usually takes (filed Q29); what acts on it and whether it was commanded, ran and moved (filed Q28's line); what to expect (the forecast sentence when present); (2) the remedy line: the suggestion for this goal from the snapshot's hints (ergostat/state.py:524-589), shown only when it has a verdict (filed Q80's rule), with its Evidence link; (3) the charts; (4) parts, the control-loop table (filed Q69) and the prose, with 'Not worked out: it has no one process' reworded to what a reader can do. The lines are built by functions the quick fixes own, in whatever order they land: this gap only orders and adds the remedy and expectation lines.
Definition of done:
1. On a fixture an off goal's panel has, before any chart, four one-sentence lines and (when a suggestion with a verdict exists) one remedy line.
2. The charts follow; parts and prose come last.
3. The remedy text equals the Suggestions entry for that goal; the first line's word equals /api/loops' word.
4. No sentence in the first screen of the panel contains 'Not worked out'.
5. At 390 px the four lines fit without horizontal scroll.
Files: ergostat/web/static/details.js, control.js, style.css, tests/test_diagram_rendering.py.
Acceptance tests: a browser test of the panel's order and the remedy line on the fixture.
Budget: 90 net lines.

Milestone: r7-evidence-is-a-runbook. Owner items: R7 piece 7 (pieces 1-6 are filed Q26, Q28-Q31, Q33, Q34, Q36). From the owner's list and the design review of 2026-11-22.
