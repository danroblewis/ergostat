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

## Where it stopped

Built, round 1: `ergostat/spec/footprint.py` (kind_footprint, item_path), `GET /api/kinds/K` and `path` on
`/api/items/ID` (server.py), `kinds/K` in the snapshot, SPEC §5a *What a kind touches, and an item's path*, and
tests/test_footprint.py (8 tests). 193 net lines outside tests, docs and dev, within the 200 budget.

Choices I made with nobody to ask (each the one easiest to undo):
- `finish_of` does not exist on main. A state is `finished` if `messages: done:` names it, else if it is the kind's
  last state (`finished_by` says which). This reads the spec only: `messages/route.done_states` also infers from the
  record, and this gap must not read it.
- The "goal's word" is the goal's `status` (holding or off), taken from the snapshot's loops and shown beside `hold` as written.
- The footprint is the spec's alone, cached in `spec.lookups().kept` (per model version). The server adds `now` (the
  item index's counts), each block's `taken` and each goal's `status` per request. `taken` reads, from the item
  index, the items whose `lease.block` names the block, and counts those whose lease has a holder.
- A step's block is the lease taken out of that state (`how: taken from here`). Failing that, it is the lease open
  when the item entered the state, if that lease had not yet ended (`taken while here`). The k-th move into `leased`
  is matched to the k-th entry of `lease.history`, counted from the tail.
- `how` values use "taken", never "held", following docs/vocabulary.md.
- Done item 4 (under 300 ms on :8796) was not measured: no demo runs on :8796 in this container. A serial unit test
  checks that the answer on 300 roadmap tickets, after a first call, takes under 300 ms.
