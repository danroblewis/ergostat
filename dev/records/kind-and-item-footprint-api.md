# kind-and-item-footprint-api: The model says what a kind and an item touch: /api/kinds/K and an item's path

depends-on: []

Problem: no function says what a kind or an item touches in the model. /api/items gives a kind's name, states, show, description, system, relations and counts only; the rest of ItemKind (ergostat/spec/ir.py:865-889: on, fold, lease, join, final, about) never reaches a page, and an item's moves are not related to stocks, flows or blocks. The parts exist spread out: sensors counting a kind in or entering a state (spec.sensors() with .items; spec/item_sets.py:370 counted_by; spec/item_systems.py), blocks that take it with their out: flows, pool and lease (b.takes, b.targets()), goals (snap['loops']), feedback loops (spec/causal.py:242), an item's moves and fields.lease.history.
Change: new ergostat/spec/footprint.py. kind_footprint(spec, kind): definition (plain title, description, id pattern, states with which are finished via finish_of when present, on: event -> state, show, fold per field, relations both ways, join, lease rule, system and why); counted_in (each stock/auxiliary/flow whose sensor counts the kind, with states or events and system; several sensors on one state all listed); taken_by (each block: at, to, where, order, pool, attempts, TTL, out flows, agent, and how many it has taken now, a lease holder in any state); goals (those blocks' goals and goals on counted stocks, with the goal's word); loops (causal.loops through those parts, R/B and name); now (count per state). item_path(spec, item): its moves joined to the footprint as ordered steps {state, stock, flow, block, run, attempts, goal, entered, left}; `leased` is not a step; states nothing counts are said as such; nack loops and rework appear as repeated steps with attempts. GET /api/kinds/K returns the footprint (404 for an unknown kind); /api/items/ID gains path. Cached per model version; the functions read the spec only (item_path one item more), never scan the record. Snapshot includes kinds/K. Field names follow docs/vocabulary.md: taken and waiting, never held.
Definition of done:
1. On the roadmap demo's spec /api/kinds/ticket names stocks todo, in-progress, in-review, blocks developer and reviewer with their pools, goals nothing-ready-waits and in-review-clear and their loops.
2. item_path for a done roadmap ticket lists its states in order with the block that took it and attempts.
3. A kind nothing counts returns an empty footprint and a reason; a block with takes.where says it takes only some items.
4. /api/kinds/K answers under 300 ms on :8796.
5. SPEC §5a documents both.
Files: new ergostat/spec/footprint.py, ergostat/web/server.py, ergostat/web/snapshot.py, docs/SPEC.md, new tests/test_footprint.py.
Acceptance tests: unit tests for ticket-factory's ticket footprint (every step's stock and flow from demos/ticket-factory/steps/*.yaml and each taking block), a done ticket's path with two leases, an uncounted kind, the API 404. Each fails on main.
Budget: 200 net lines.

Milestone: kind-and-item-pages. Owner items: 15, 20. From the owner's list and the design review of 2026-11-22.
