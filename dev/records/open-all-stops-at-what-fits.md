# open-all-stops-at-what-fits: 'Open all' on a model that will not fit opens to the system boxes and says 'Into' for the rest

depends-on: []

Problem (R8 piece 6): 'Open all' on big shows about one system on screen and takes the longest layout the page can ask for (shots/story-7-h2-open-all.png, ixd-big-open-all-fit.png); on the-job in Blocks it left a blank canvas after 10 s (plan-notation-job-openall-blocks-fit.png). The reader asked to see everything and gets less.
Change: before opening, the page estimates the open drawing's size from the graph (parts and lines per system, already in the top-level answer). When everything open would exceed what fits at an 11 px text floor by more than a set factor (or the line count exceeds the routing bound), 'Open all' opens one level: nested systems stay closed boxes (each with whatever its box shows), and a line on the canvas says 'Opened to the first level: N systems stay closed. Use Into to open one.' with each closed box keeping its Into control. The ⋯ menu's wording says what it will do ('Open all (first level)'). A model that fits opens fully as today.
Definition of done:
1. On :8797 'Open all' leaves nested systems closed, shows the sentence with the right count, and reaches attached lines within 3 s.
2. On :8791 (fits) it opens everything as before.
3. On :8792 ?view=blocks it never leaves a blank canvas.
4. The address records what was opened (open= lists them), so a reload shows the same.
Files: ergostat/web/static/diagram.js (the menu action and estimate), style.css, tests/test_diagram_rendering.py.
Acceptance tests: a browser test for 1-3.
Budget: 60 net lines.

Milestone: r8-open-fit-large. Owner items: R8 piece 6. From the owner's list and the design review of 2026-11-22.
