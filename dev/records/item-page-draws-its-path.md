# item-page-draws-its-path: The item page draws its path on the Dynamics and Blocks diagrams, on demand

depends-on: [diagram-draws-what-an-item-or-kind-touches]

Problem: the owner asks to see, on the item page itself, the subset of the Dynamics and Blocks diagrams an item leased to agents passed through. diagram-draws-what-an-item-or-kind-touches gives the subset on the Diagram page and links to it; the item page still shows no picture. diagram.js (pageDiagram and its drawers) runs on the page-global S, #detail and pins, so it cannot be mounted elsewhere as it is. Build this as docs/proposals/item-and-kind-footprint.md decided (inline on demand is the default; if the proposal chose links only, close this gap).
Change: under 'Where it went' a closed section 'Draw its path' with a Dynamics/Blocks switch. Opening it draws item=ID in a box about 420 px high, full width, fitted, with no toolbar, side panel, pins or address changes, by the embedding the proposal chose (the renderer mounted with {view, item, embedded: true} and its own state object, or the ?pane=1 frame). A click on a part goes to /diagram with that part selected. Nothing loads (no ELK, no libavoid) until the section opens; the item page's poll does not re-lay the diagram unless the path changed; closing and reopening leaks no listeners or timers (the page guard of diagram-lines-stay-attached).
Definition of done:
1. On the roadmap demo /item/ticket%2F<done ticket> opening 'Draw its path' shows an svg with the stocks todo and in-progress and the valve started; switching to Blocks shows the developer's block and its loop whole.
2. With the section closed no request for elk.bundled.js is made and the item page's load time is unchanged (measured before and after).
3. No console error; the Diagram page's render tests and page-polling tests pass.
Files: ergostat/web/static/diagram.js, dynamics.js, blocks.js, interact.js (state scoping), pages.js, style.css, tests/test_items_page.py.
Acceptance tests: the browser checks above. If mounting needs more than the budget because of global state, stop and file a proposal splitting the renderer's state first.
Budget: 180 net lines.

Milestone: kind-and-item-pages. Owner items: 20 (the subset of the diagrams, on the item page). From the owner's list and the design review of 2026-11-22.
