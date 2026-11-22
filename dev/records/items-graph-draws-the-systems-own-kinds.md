# items-graph-draws-the-systems-own-kinds: A system's Graph draws only its own kinds' dependency network; another system's items are stubs at its edge

depends-on: []

Problem: in the factory, review is counted in the knowledge system (instance dev/model/knowledge.yaml:44,252; spec/item_systems.py rule 2) and declares relations {gap: gap}, a plain 'about' relation. The page asks items-graph for each system's kinds with relations (ergostat/web/static/pages.js:670-678) and precedence.build follows every relation both ways for HOPS=6 up to 400 items of any kind (ergostat/precedence.py:40-41, 274-299), so the knowledge Graph fills with gaps, their sessions and depends_on chains drawn as full cards on 'gap' edges. The owner cannot tell why gaps are there. SPEC §5a says 'the items their relations reach, of any kind' on purpose (docs/SPEC.md:1547), so the SPEC changes first (open owner question; the gap proceeds on this default).
Change: (1) items-graph takes system=NAME (relations_api.kinds_asked accepts it); build() then pulls further items only along precedence and parent (group) relations and only of the system's own kinds. (2) a precedence target or parent of another system's kind is not a card: the answer marks it outside: true with its system and rgModel draws a small stub at the frame's edge ('waits on gap/x, ready · building'), linked to /item/ID; its status still counts (the existing cut/beyond logic), so the waiting item stays 'waiting'. (3) 'about' relations are not edges; they are listed in the card's hover text and stay under Relations on the item page. (4) a system whose kinds declare no precedence or parent relation draws no canvas and says once 'These items do not wait on one another, so there is no dependency graph' (filed Q59's sentence) and where the related items are ('reviews are about gaps: see building'). (5) items-graph without system= keeps today's behaviour for the CLI. MOST_PULLED and HOPS stay for chains inside a system.
Definition of done:
1. SPEC §5a's Graph paragraph states the new rule.
2. On a fixture shaped like the factory (review in knowledge with gap: gap; gap elsewhere with depends_on) the knowledge answer has no gap as a full item and its section shows the sentence and the link.
3. A ticket in system A blocked by an item in system B shows one stub naming B, and the ticket is 'waiting' while B's item is unfinished.
4. The gap's own system's graph and critical path are unchanged; on the roadmap fixture the delivery Graph has the same card count.
Files: ergostat/precedence.py (build), ergostat/web/relations_api.py, ergostat/web/static/pages.js (relAsked by system, the sentence), relations.js (stubs, hover text), style.css, docs/SPEC.md, tests/test_relations.py, tests/test_precedence_cap.py, tests/test_item_graph_queries.py.
Acceptance tests: unit tests of build() on the two fixtures; build(kinds=[gap]) still returns the depends_on chain; a browser check on the roadmap fixture.
Budget: 160 net lines.

Milestone: items-page-readable. Owner items: 12. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1; nothing left of the definition. 85 net lines of code (budget 160). Choices made alone, each the more
reversible one:
- The stubs are a list of their own in the answer (`outside`, each `outside: true` with its `system`), with edges of
  kind `outside`, not entries in `items`: the Timeline, the legend's counts, the estimates' merge and `order_ready`
  read `items` and are untouched. Capped at MOST_PULLED (`capped.outside`, said by the legend); past it their status
  still counts.
- The page asks `kinds=` (its kinds with relations, as before) and `system=` together; `system=` alone still means the
  system's kinds. Only the Graph gives way to the sentence; the Timeline of such a system is still drawn.
- `ergostat/web/snapshot.py` (outside the Files list) asks the same `system=` keys as the page, or a snapshot would
  lose its Graph; tests/test_graph_cli_web.py's three snapshot tests follow it. The SPEC's open question (the owner
  may want "of any kind" back) is not answered here.
- "reviews are about gaps" is the kind's name and an "s"; a kind whose plural is not that reads oddly.
Not done: no screenshot was taken (a scratch script outside the repository was refused in this session).
