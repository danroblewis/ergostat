# perf-goals-page-asks-once: The Goals (Loops) page asks for all goals' performance in one answer and stops fetching the whole graph for sparklines

depends-on: []

Problem: opening Loops on the factory sends one /api/loop-control?goal= per goal (ergostat/web/static/pages.js:45-51; also review.js:304): 60-97 at once. Each is an identification serialised by control_api.WORKING (ergostat/web/control_api.py:14-33), so they finish between 0.2 and 9.4 s, each holding one of the 24 workers; the header's status (4.8 s) and the next page's HTML (4.6 s for /items) wait behind them. Every 30 s the page also fetches graph?open=* (2.4 MB) only to draw each stock's sparkline (pages.js:30-36). Live.keep (ergostat/web/server.py:128-132) clears the whole answer cache above 16 entries, so the burst flushes its own results and the numbers, models and fit entries.
Change: (1) /api/loops?perf=1 carries each goal's performance word from one per-goal background cache (a small module, ergostat/web/goal_work.py: a table keyed (goal, what, window) with an age, filled goal by goal within a stated time budget; 5 minutes' life for the performance word); a goal not done says 'being worked out'. The cache is the one place per-goal background work is kept: forecast-on-first-paint-window-horizon adds its entries to it instead of starting a second worker. It runs on its own thread here and moves to the snapshot thread's after_snapshot hook when perf-answers-never-wait-for-a-snapshot has landed (whichever lands second does the two-line move). (2) the loops answer carries each goal's stock points (the snapshot holds them), so the page no longer asks for the graph. (3) Live.keep becomes an LRU of 256 entries. (4) the single loop-control for an opened goal's panel stays; review.js's fan-out reads the same summary. The row's columns are not redesigned here (goal-row-one-renderer does that on this answer).
Definition of done:
1. Opening the page sends at most 4 API requests (status, loops, projects, one more), none of them graph and none per goal (browser test on a demo).
2. The performance column fills within a few polls and matches loop-control per goal.
3. Unit test: of 40 cache entries the most recently used are kept; nothing younger than its lifetime is dropped under 256 entries.
4. The per-goal work never exceeds its budget per pass (unit test with a slow identification).
Files: ergostat/web/static/pages.js (pageLoops), ergostat/web/static/review.js, ergostat/web/server.py (loops, keep), new ergostat/web/goal_work.py, ergostat/web/control_api.py, tests.
Acceptance tests: the request-count browser test; the LRU unit test; on a copy of the factory state the page shows its table in under 3 s and a second tab loads /items HTML in under 0.5 s meanwhile. Note: keep internal names (pageLoops) so goals-page-replaces-loops-page applies either way.
Budget: 130 net lines outside tests.

Milestone: pages-answer-fast. Owner items: 2. From the owner's list and the design review of 2026-11-22.
