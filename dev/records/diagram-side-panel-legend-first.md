# diagram-side-panel-legend-first: The Diagram's default side panel: what waits for you, then the legend of what is drawn; the rest folded with counts

depends-on: []

Problem: with nothing selected the right panel (ergostat/web/static/diagram.js:1332-1406, renderSide) lists 'Not running' and charts, Needs attention (1347), Suggestions (1363-1374, open whenever a goal is off), the charts drawn last (1375), the loop list (dynamics.js:421 sdLoopList or diagram.js:1378-1388, 18-39 rows), The model, and only then 'How to read it' (1405). legendBox (diagram.js:1309-1314) writes localStorage ergostat.legend=closed on first render, so from the second visit the legend is a closed details under about 30 rows: off screen at 1440x900 on :8796 (shots/plan-notation-sf-dyn-open.png) and under 26 attention entries and 35 loop rows on :8797 (plan-notation-big-home.png). blocksLegend (blocks.js:1099) lists every symbol whether drawn or not. The owner: 'Most are useless: make it the explanation of symbols, or at least that first.' The owner's complaint is about broken loops, suggestions, charts and loop lists, not about requests: approving or denying is the one thing a person does here (decision 7, R3), so what waits must not fall below a 30-row legend.
Change: in the default state of every view (Dynamics, Blocks, Process), at every width, the panel is ordered: (1) 'Waiting for you' only when something waits: one line per request, and above 3 one line 'N wait for you' that opens them (filed Q42's group, Q43's header link kept); (2) legendBox(view), titled with the diagram's type and open unless the reader closed it in this browser (it then stays closed); the first-visit 'closed' write goes; the Blocks legend lists only symbols drawn, as sdLegend (dynamics.js:468) does; (3) goals off (the rest of Needs attention, as filed Q42 groups it); (4) Suggestions, the loop list and The model, each a closed details with its count in the summary. The 'charted last' fallback (1375) is removed: charts appear only while parts are chosen. A selected part's panel is unchanged.
Definition of done:
1. On a fixture with no request waiting, in all three views, with fresh localStorage and after a reload, the first heading in #side is 'How to read it' and its details is open.
2. With requests waiting the first heading in #side is 'Waiting for you' and the legend is the second; at 1440x900 both are on screen.
3. Closing the legend survives a reload; reopening too.
4. Suggestions, the loop list and The model are closed details whose summaries carry counts.
5. With nothing selected no chart svg is in #side.
6. Each Blocks legend row's symbol is present in the svg.
Files: ergostat/web/static/diagram.js, dynamics.js (sdLoopList in details), blocks.js (drawn-when filter), process.js (pmSide), tests/test_diagram_rendering.py (line 1970 checks the text after the legend), docs/SPEC.md (side panel paragraph).
Acceptance tests: a browser test per view asserting 1-6 on a served fixture (one with and one without waiting requests).
Budget: 80 net lines.

Milestone: diagram-notation. Owner items: 9. From the owner's list and the design review of 2026-11-22.
