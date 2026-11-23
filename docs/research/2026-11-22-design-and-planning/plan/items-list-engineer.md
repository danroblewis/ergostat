# Items page: owner items 1, 3, 4, 11, 12, 13, 14 (engineer's notes)

Code read at ergostat main 2468c59b. Paths are relative to DESIGN/ergostat. `pages.js` = ergostat/web/static/pages.js.

## Where it lives

- The page: `pages.js:551-803` (`pageItems`). Defaults for the graph/timeline: `pages.js:564-567`
  (`frontier` defaults true, `collapse` defaults true only in Graph). Checkboxes: `pages.js:688-689`. `go()`
  (address + refresh): `pages.js:614-622`. System folding (localStorage): `pages.js:505-510`, `625-631`. One
  refresh per click: `pages.js:607-613` and `tick` `632-800`. List tables: `tables()` `pages.js:743-761`; the
  kind heading is an `h3.kind-head` at body text size (`pages.js:751`, `style.css:357`). "All N" link
  `pages.js:757-758`. Systems and charts: `pages.js:776-792` (all of a system's charts first, `787`, then all its
  tables).
- List API: `ergostat/web/server.py:607-660` and `_as_listed` `server.py:271-298`; `its.listing`
  `ergostat/spec/items.py:517`, paged by the index `items.py:_paged` (takes `n`, `offset`, a states list
  underneath). A comma list of states only through item sets (`spec/item_sets.py:124-200`, needs `kind=`).
- Finished states: `spec/itemindex.py:119` `done_states` (declared `messages: {done:}` else "states no item has
  left"); `precedence.py:58-97` (`Kinds._info`, `status`): done / paused / dead are separate statuses.
- Graph/Timeline: `relations.js:35-87` (`rgModel`: frontier `43`, collapse `51-52`), API
  `web/relations_api.py`, `precedence.build` `precedence.py:247-300` (follows *every* relation out to six hops,
  400 items of any kind: `precedence.py:40-41`, `281-299`). SPEC §5a "The Items page's views" (docs/SPEC.md
  around 1545-1560) says on purpose "the items their relations reach, of any kind".

## Item by item

**1. Hide terminal states by default; no reload.** Nothing filters by "unfinished" in the list: the default
asks `per_kind=25` of every state (`pages.js:642-644`). The server can page a kind by a list of states but has no
"open only across kinds" switch. Every click goes through `go()` → `replaceRoute` (no navigation: `util.js:455`)
→ `refresh()`, which re-asks `items` (300 rows when a kind is chosen), each kind's `items-flow`, the trust table,
and `items-graph` *serially per system* (`pages.js:674-678`, an `await` inside the loop) before patching. Nothing
shows that work started (no "Loading…"), so on a large record a click looks like a reload that hangs. The live
factory (:8798) did not answer `GET /api/status` or `/api/items` within 100 s while I measured (150% CPU, other
agents probing it), which is item 2's territory, but it is why every click "reloads". Change: a server switch
`finished=hide` (default) that lists each kind's unfinished states (finished per `done_states` + `dead`, paused
kept); the page says "N finished hidden · show" per kind; an explicit `state=` (a click on a "closed" band) always
shows it; clicks answer at once (filtered locally from what is loaded where possible, "Loading…" otherwise), stale
answers dropped, the per-system graph requests in parallel. Risk: snapshot mode (SNAP) filters client-side; the
heuristic finished set for kinds with no `messages: {done:}` can hide a state no item has left *yet* (early on);
use declared done else the kind's last state, never the "not left" guess, for hiding. Size: incremental.

**3. Frontier does nothing.** Reproduced on :8794 (roadmap), Graph: frontier on and off draw the same cards
(shots `plan-items-rm-graph-frontier1.png`, `-frontier0.png`). Reason: in Graph, Collapse done defaults on, and
collapse removes every finished item that has no unfinished child (`relations.js:52`); frontier only decides
whether finished items with no unfinished successor are in scope (`relations.js:43`), exactly the ones collapse
removes. With collapse off, frontier off draws ~1000 finished cards shrunk to illegibility
(`plan-items-rm-graph-f0c0.png`). In Timeline (collapse off by default) frontier does act. Change: one control
instead of two, "Finished: hidden · as 'via N done' · shown" in Graph and "Finished: hidden · shown" in
Timeline, naming the states. Size: quick.

**4. What "collapse done" means.** "Done" is the status `done` = the kind's finished states (`messages: {done:}`
in the model, else the guess above): for gaps merged and closed; parked is *paused*, a dead letter is *dead*,
neither is "done". The page never says so (hover text only). The graph answer already carries each kind's
`finished` list (`precedence.py:412`); the control's label and legend should print it ("finished: merged,
closed"). Same gap as 3.

**11. Kind headings hard to find.** A system shows all its kinds' charts in a grid first (`pages.js:787`), then
each kind's table under a small `h3` (body size, `style.css:357`), so the chart titled "gap" and the list headed
"gap 2,340" are screens apart and the list heading is no bigger than a cell. Change: one section per kind:
heading (larger than a table, name, count, description), its chart, its list.

**13. Every kind's list closed by default.** Today folding is per *system* and remembered in localStorage
(`pages.js:505-510`), open by default. Change: each kind section is a disclosure, closed by default, showing its
heading, one-line description and state counts (or chart); opening it asks the server for that kind's rows only
(less to fetch: helps item 2). Opened kinds live in the address (`open=gap,review`); `kind=gap` opens gap. System
folding then has no job: drop it (subtraction) and keep the system as a plain heading.

**14. "Show all" is not pagination.** "All N" sets `kind=` (`pages.js:757`), which asks 300 rows; past that the
page only says "N older items not loaded" (`pages.js:799`). The server already pages (`n`, `offset`, `LISTED=500`
`items.py:30`). Two more defects found: the search (`q`) is applied *after* the server cut its 500 newest
(`server.py:281-286`), so an old item is never found, and the client's column sort sorts only the rows loaded.
Change: pages of 50 per open kind with "1-50 of 2,340 · Older · Newer" and the offset in the address; `q` runs
on the index (`search` words, `items.py:_paged` `ws`) for the kind shown so the count and pages are of the
matches; column sort said to be "within this page" (server sort deferred). Size: incremental.

**12. Graph mixes kinds and systems.** In the factory, `review` is counted in the knowledge system
(instance `dev/model/knowledge.yaml:44`, `:252` → `item_systems.py` rule 2) and declares `relations: {gap: gap}`.
The page asks `items-graph` for each system's kinds that have or are named by relations (`pages.js:670-678`), and
`precedence.build` follows every relation out six hops, up to 400 items of any kind (`precedence.py:281-299`),
so the knowledge graph pulls in gaps (and through their `depends_on` and `parent`, more gaps), drawn as full
cards joined by "gap" edges. SPEC §5a states this on purpose. Change (SPEC first): a system's graph draws its own
kinds; an item of another system appears only as the precedence predecessor of a drawn item, as a small stub
naming its system and linking to that system's graph; non-precedence relations are not followed out of the
system (the card says "about gap/x"). A system with no relations among its own items says so (Q59's sentence).
Size: incremental (server + rgModel + SPEC + test).

## Gaps proposed (order)

1. `items-list-hides-finished-by-default` (1, the no-reload half) - incremental.
2. `items-graph-one-finished-control` (3, 4) - quick; parallel with 1.
3. `items-graph-draws-the-system-s-own-kinds` (12) - incremental; parallel with 1 and 2 (SPEC change).
4. `items-one-section-per-kind-closed-by-default` (11, 13) - incremental; after 1 (same function).
5. `items-pages-through-a-kind` (14) - incremental; after 4.

None needs a proposal first; the design choices are settled in each definition. Item 15 (a page per kind) is
another cluster's; gap 4's kind heading is where that page's link would go.
