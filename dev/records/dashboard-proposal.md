# dashboard-proposal: Proposal: the Dashboard page, its panels, where a dashboard is kept, and its load budget (docs/proposals/dashboard.md)

depends-on: []

Problem: the owner asks for a Dashboard page of configurable panels ('the dashboard is an analysis'); the request overrides 'no new pages' for this page. Nine of the eleven panel kinds are already drawn, each wired into one page: item lists (itemsets.js:22 itemsSection over /api/items, server.py:607-660), counts over time (flowChart charts.js:621 inside pageItems, pages.js:655-710), cycle time (charts.js:665), a stock with replay, projection and fan (lineChart charts.js:192, causesStrip :275, /api/series?replay=1&fan=1), goal scope (charts.js:530), Items Graph and Gantt (relations.js:157, 222), the diagram (global state S, embedded today only as an iframe, split.js:1-40). Nothing stores an arrangement. Design questions a builder cannot settle: storage without breaking decision 7 (people do not edit configuration through the page, and the owner's rule that people never write config: the Supervisor does) and the load budget: every /api head builds a snapshot per (window, at) (server.py:151-176), a fanned projection took 3.5 s on :8796, and the live factory answered nothing in 60 s (owner item 2).
Change: write docs/proposals/dashboard.md (read SPEC §4a show:, docs/proposals/charts.md and parity/11-translating-both-ways.md §C first). It settles:
1. The panel format: JSON-shaped, parameters exactly those the existing APIs and addresses take; title, size, optional note; each panel links to the full view with the same parameters.
2. The v1 panel kinds, each mapped to its endpoint and component file:line or marked new: note, goals, items (kind or filter), states over time, cycle time, chart (one or several series, optional projection), xy (phase plot), heatmap, goal scope, items graph, timeline, diagram. Recognised chart forms only, each cited.
3. The analysis rule: every panel shows the model's reading beside the measure (replay, projection, bound crossing, balance, estimate).
4. The home page: '/' stays the folded diagram (decision 1: the diagram with everything folded away is the control panel); the Dashboard is an analysis page and is never the first answer to 'is it healthy'. Its goals panel is the shared goal row (goalRow, goalrow.js) and its counts come from state.goals_off; every panel that prints a goal's state prints the server's `word`.
5. Storage, with reasons (the one owner question of this cluster): the reader's draft in the address and localStorage (nothing written); shared named dashboards under a top-level dashboards: key, compiled and checked like systems.*.show (compile.py:908-913, 1588); how a draft is kept (an owner-made ergostat.model-change of kind display accepted like a what-if, numbers_api.post, or written by the Supervisor) and whether a display-only change skips the judge's replay. The page never shows YAML for a person to paste: sharing a draft is 'Copy link'.
6. The load budget: one window per dashboard, one batched read on the shared snapshot with a per-panel time limit and partial answers, replay/fan panels lazy and slowly polled, a cap on diagram panels (ELK cost), a target (10 panels on :8796 first paint under 1 s) measured against the factory-size fixture.
7. Layout and editing: grid at desktop, one column at phone width, Loading and empty states; adding, moving, resizing and removing a panel by keyboard with focus returned (story H5).
8. The default when none is declared; its place in the nav; snapshot and export (R10); windows longer than 7d (main.js:6). Whether the Goals page folds into it is left to goals-page-keep-or-fold-decision.
9. The follow-on gaps: confirm or amend dashboard-page-v1, dashboard-declaration-and-api, dashboard-xy-and-heatmap-panels, dashboard-diagram-panel, dashboard-add-and-edit-draft, dashboard-keep-display-proposal.
Definition of done:
1. The proposal answers 1-9 with a worked example for software-factory and ticket-factory.
2. Every panel kind names the file and function it reuses.
3. The request budget is stated with measurements.
4. The owner's one-sentence question is listed (kept in the address and browser, declared in the model, or both; one window for all panels).
5. One line in docs/DECISIONS.md records the owner's override for this page.
Files: docs/proposals/dashboard.md, docs/DECISIONS.md.
Acceptance tests: review only: no open TODO on storage, fetch, editing or default.
Budget: 250-400 lines of prose, no code.

Milestone: dashboard. Owner items: 18. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Done: docs/proposals/dashboard.md answers 1-9, with worked examples for software-factory and ticket-factory and the
owner's one question; docs/DECISIONS.md has the override line. Every file:line cited was checked against main.
Not done here: new timings. The request budget cites the recorded ones (owner item 2; docs/proposals/scale.md,
The web UI), because the command that copied the examples to /tmp to time them was refused in this session. The
10-panel target is measured first by dashboard-page-v1, against a factory-size fixture it makes (none is on main).
Found: goalrow.js, state.goals_off and the server's `word` are not on main, so dashboard-page-v1 waits for the gap
that lands them (the proposal says so in sections 4 and 9).

Round 2 (review/dashboard-proposal-1, both findings answered in section 6):
- Blocking, rule 2: the late pool is now 2 threads with at most 16 jobs waiting (hard maxima in code); beyond that a
  panel is refused as "busy" with a Try again button and no automatic retry. A waiting job not asked for in 6 s is
  dropped, a running one stops at its next step when unwanted or past 10 s (what stops is said plainly: Python
  threads cannot be killed). Kept results are keyed by the moment key (window, at, model mtime, a per-snapshot seq
  compared for equality), kept 30 s, and handed only to a retry naming the same key. Eager panels run one after
  another on the request thread against one 0.8 s batch deadline (snapshot included), not 2 s each, which is
  consistent with the 1 s first-paint target. Sections 7, 8 and 9 were changed to match.
- Non-blocking, the quoted numbers: section 6 now quotes scale.md's table after its fixes (graph 0.093 s at N = 10,
  0.413 s at N = 30) and keeps the browser layout times, which did not improve, as the reason for the diagram cap.
Still no new timings taken in this session (as above).
