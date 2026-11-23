# items-one-section-per-kind-closed: /items is an overview of the item kinds; each kind opens on its own page

Rewritten 2026-11-22 from the owner's direction: "an initial page that shows types of items and metrics per type (like the graphs), and click through to get to a specific item type. We rarely want to use the whole page, so we can speed it up by splitting it ... We want to fit the majority of our item types displayed above the fold."

Problem: /items draws every kind's charts and lists at once: about 8,000 elements and 26 to 28 API requests per load on the factory's record.

Change:
- `/items` becomes the overview. Under each system heading, one compact card per kind in a dense grid: the kind's name (a link to `/items/<kind>`), how many are unfinished and in all, a small state chart over time, and the rate in and out.
- The overview draws no item rows and offers no List, Graph or Timeline switch. Those belong to the kind's page (`the-kind-page`).
- Each chart's legend sits to the right of the chart, not under it.
- A chart shows **state groups** by default (waiting, working, done, stopped, derived from the kind's states and its finished states) with one page-wide toggle to show every state. The choice is kept in the address.
- The whole overview comes from **one** request (`/api/items-overview?since=...`), which reads the item index and the stored counts and never replays the event log. Kinds with no items in the window are folded into one line at the end.

Definition of done:
1. On a generated record of the factory's shape (about 25 kinds, 700 gaps, 2,500 sessions), `/items` makes exactly one data request for its cards besides the page's shared header calls, and has no table row in the DOM.
2. `/api/items-overview` answers in under 200 ms on that record, measured in a test with a generous bound so it is not flaky, and performs no event-log scan (a test counts the segment queries).
3. At 1440x900 at least 16 kind cards are entirely above the fold.
4. The legend is to the right of each chart at 1440 px and the layout stacks with no horizontal scroll at 390 px.
5. The state-group toggle changes every chart with no further request, and survives a reload through the address.
6. A card's title goes to `/items/<kind>`; `/items?kind=K` redirects there. Until `the-kind-page` lands, `/items/<kind>` shows the existing list, graph and timeline for that one kind.
7. SPEC §5a and the Guide's Items text describe the overview.

Files: `ergostat/web/static/kinds.js` (new), `pages.js`, `charts.js`, `style.css`, `ergostat/web/server.py` or a small `items_overview.py`.
Tests: unit tests for the endpoint and the state groups, and structure-only browser tests; the browser suite is not run on each merge, so items 1, 2 and 5's logic must also be covered without it.

Milestone: items-page-readable.
