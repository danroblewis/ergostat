# the-kind-page: The kind's page: its definition, where the model counts and moves it, its goals and loops, and its items

depends-on: [item-and-kind-footprint-proposal, kind-and-item-footprint-api, items-one-section-per-kind-closed]

Problem: owner item 15: 'no page representative of an item type ... its definition, the stocks and flows related to it, the feedback loops and control loops it takes part in, a well-designed filter, what all is this item?' Today the kind link goes to /items?kind=K (ergostat/web/static/pages.js:699), which only filters the list (shots/plan-ks-road-items-ticket.png): the description sits small on the system heading, the states are legend chips, and nothing names the kind's stocks, flows, taking blocks, goals or loops.
Change, as docs/proposals/item-and-kind-footprint.md decided (default: the Items page with exactly one kind chosen, at /items/<kind>, /items?kind=K redirecting with its other params, no new nav entry). Filled from /api/kinds/K, in order:
1. The kind's bar, drawn by the same kindBar function in static/kinds.js that the Items page uses, with the same markup (title, id pattern small, description, 'finishes: merged, closed' or 'lives on', state chips with counts, 'in <system>' with why on hover); here the title is the page's h1 and the list below is open. On the Items page the bar's title links here; the disclosure there still opens the list in place. Filtering by chip behaves identically on both.
2. Now: the state chart and cycle time under the bar; finished states folded per the page's one finished parameter.
3. In the model: a table of counted in (stock, which states), moved by (flow, which events), taken by (block: at, to, where, pool now and at most, attempts, TTL, taken and waiting now), goals (each with its word through goalWord), feedback loops (R/B and name); every name links to the diagram with that part selected or to the goal's evidence; links 'its states as a process map' (view=process&kinds=K, filed Q57's content) and 'draw what it touches' (kind=K) when that gap has landed.
4. Definition, a closed details: events -> states, fields shown, how each folds, relations both ways, joins, the lease rule.
5. Items: the list section, filter and pager built by the Items-list gaps, reused, not redesigned. Graph and Timeline stay views of the list.
Every link to a kind (item page header, Items bar titles, process map, stock panels' 'Show them on the Items page' when it names a whole kind) points to the kind's page.
Definition of done:
1. On the roadmap demo /items/ticket has h1 'ticket', its description, 'finishes', and an 'In the model' table naming todo, in-progress, in-review, developer, reviewer, nothing-ready-waits and its loops, each a link whose href starts with /diagram or opens evidence.
2. /items?kind=ticket ends at /items/ticket; the item page's kind link and the Items page's bar title go there.
3. The bar on /items/ticket and the ticket bar on /items have the same markup apart from the heading level and the open state (a test compares them); a chip click filters the list in place on both (window.__same survives) and lands in the address.
4. A kind nothing counts says so in section 3 and still shows its definition and items; built-in kinds render.
5. At 390 px every section stacks with no horizontal scroll.
6. SPEC §5a describes the kind's page; existing Items tests pass or are updated with the reason.
Files: ergostat/web/static/kinds.js, pages.js, main.js or util.js (route), ergostat/web/server.py (route), style.css, docs/SPEC.md, tests/test_items_page.py.
Acceptance tests: test_a_kinds_page_shows_its_definition_and_model_place, test_the_kind_bar_is_one_component, test_a_kinds_state_link_filters_without_reload, test_an_uncounted_kind_says_so, the redirect test. Each fails on main.
Budget: 300 net lines; if over, split definition and model place from the list wiring.

Milestone: kind-and-item-pages. Owner items: 15 (also 11). From the owner's list and the design review of 2026-11-22.


## Added 2026-11-22 (the owner)

The List, Graph and Timeline views live on this page only, for this one kind; `/items` no longer has them. This page loads only this kind's data. Its charts use the same right-side legend and state-group toggle as the overview (`items-one-section-per-kind-closed`). Opening a kind must not load any other kind's items.
