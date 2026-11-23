# dashboard-diagram-panel: A diagram in a Dashboard panel: a Diagram or Items Graph address drawn read-only

depends-on: [dashboard-page-v1]

Problem: the owner wants a nodes-and-edges diagram on the dashboard. The model diagram runs on page-global state S with an ELK layout and is embedded today only as a whole page in an iframe with ?pane=1 (ergostat/web/static/split.js:1-40); layout is slow on large models (owner item 10), so a dashboard poll must never re-lay it.
Change: a diagram panel takes a Diagram address (view dynamics, blocks or process; system; opened; selection; item= or kind= when available) or an Items Graph address (kinds or system). The Items Graph draws through relGraph directly. The model diagram is drawn read-only and fitted, by the embedding the proposal chose: the existing ?pane=1 frame with toolbar and side panel hidden, or an embeddable entry point in diagram.js with its own state object if the proposal's cost check allows. Values update in place through graph_poll; no re-layout while the structure signature is unchanged (the layout cache of diagram-routes-fast-then-refined is used when present). At most one model-diagram panel is live per dashboard (others draw on click), nothing loads until the panel is on screen, and clicking opens the full page at that address. Text is never drawn under 11 px: when the drawing will not fit, the panel shows the closed boxes and says 'open on the Diagram'.
Definition of done:
1. On :8796 a panel for view=dynamics&system=product draws within 3 s, and on the next poll redraws values without calling layout (asserted by a counter).
2. On :8797 a whole-model panel shows the folded boxes, not unreadable text.
3. The click opens the same address.
4. No console errors on any demo; no elk request before the panel is on screen.
Files: ergostat/web/static/panels.js, dashboard.js, diagram.js or split.js (the embedding), ergostat/web/graph_poll.py if needed, tests/test_dashboard_page.py.
Acceptance tests: the browser checks for 1-4.
Budget: 220 net lines.

Milestone: dashboard. Owner items: 18 (a nodes-and-edges diagram), 10. From the owner's list and the design review of 2026-11-22.
