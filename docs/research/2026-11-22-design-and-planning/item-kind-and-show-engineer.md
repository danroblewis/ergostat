# Owner items 15, 20, 16: the kind page, the item page, leased items on a valve

Engineer's notes, 2026-11-22. Read only. Code at DESIGN/ergostat (main 2468c59b). Paths below are relative to it.

## Summary

| Owner item | What it takes | Size |
|---|---|---|
| 16 Leased items on a valve's sidebar | Mostly built already: the valve panel's first line says "BLOCK works items of kind K: N leased now. Show the leased items" (a count and a link). It lists none of the items. One function (`countsLines`) grows a live list. | quick |
| 20b-d Item page: compact fields, history, the `contexts` field | The cause is one recursive renderer, `fieldView`. A list of objects becomes a table with one column per key used by any entry, and a `file:` cell renders the whole file inside it. Rework the item page's Fields section. | incremental |
| 20a Item page: the Dynamics and Blocks parts the item passed through | Needs an item's path through the model (states to stocks, moves to flows, leases to blocks and valves), a subset selector on the graph API, and a choice between embedding a diagram and linking to one. | large: proposal first |
| 15 A page for a kind | Every ingredient exists, spread across modules. It needs a footprint function, a place to live (it collides with the Items-page rework, owner items 1, 11, 13 and 14), and a filter design. | large: proposal first |

Items 15 and 20a share one missing piece: **what a kind or an item touches in the model**. So one proposal covers both, and one backend gap serves both pages and the diagram.

## 16. Leased items on a valve's sidebar

- **Where.** `ergostat/web/static/itemsets.js:86-95` (`countsLines`). It is used by the Dynamics valve panel (`dynamics.js:613`, `openNodeSD`) and the Blocks/classic panel (`details.js:108`, `openNode`). The server side is `ergostat/web/server.py:778-780`, which sets `out["leases"]` from `ergostat/spec/item_sets.py:399-410` (`leased_by`): each block that `takes:` items and has this flow in its `targets()` (its `out:`), with its kind, the count `held`, and the item set `{kind, state: leased, where: lease.block:B}`.
- **Why the owner sees no items.** The panel shows only a count and a link to the Items page. With 0 held, it shows "0 leased now" and nothing else. Checked on :8791: `/api/part/flow/work` gives `leases: [{block: work, agent: ai, kind: ticket, held: 0, ...}]`. No demo has a lease held right now; all of the ticket-factory's tickets are done. The live factory (:8798) did not answer `/api/part/flow/reviews-started` within 100 s while other agents were reading it (owner item 2).
- **Change.** When `held > 0`, the panel fetches `api("items", {...l.set, n: 10, shown: 1})`, as `itemsSection` already does for a stock. It lists each item with:
  - its id (a link) and its title;
  - the run holding it;
  - how long it has been held;
  - when the lease expires (or "overdue");
  - its attempt, n of max.

  Reuse `leaseCells` (`pages.js:819`); it is global. Read the list again every 4 s while the panel is open (the panel does not poll today). With `held == 0` the line says "none leased now", plus, if any, "N waiting at <at>": the block's queue. The queue is the `at` states minus the held items, read with the same `items` call by state.
- **Risk.** Low. `tests/test_items_page.py::test_a_valves_leased_items_are_listed_live` pins `#detail .leases-line` with "1 leased now" and a link. Keep both. A block with four `out:` flows (the factory's reviewer, merge queue and planner) lists the same items on four valves. That is correct: each of those valves is moved by the block.
- **Overlaps.** Q30 (the goal evidence panel links to items its agent holds: another panel, the same data) and Q39 (an agent's recent runs name their items). This gap's list can be the helper Q30 reuses.

## 20. The item page (`/item/ID`)

Code: `ergostat/web/static/pages.js:911-998` (`pageItem`), `fieldView` at `pages.js:182-211`, `historyView` at `pages.js:856-868`, `leaseView` at `pages.js:829-842`.

### 20b-d. The fields, their history, and `contexts` (the problem found)

- `contexts` is a `fold: append` field of `gap` (`ergostat.yaml:137`). Each entry is the dict `brief.assemble` returns (`dev/bin/brief.py:85-88`), with keys added by its callers. In `scratchpad/gaps.json` (a dump of 201 live gaps), `gap/queue-picks-mergeable` has 6 entries with **17 keys** among them: role, template, guides, files, findings, definition_chars, gaps_entry, brief_chars, brief_tokens, diff_chars, model, knowledge (a list of about 20 ids, 719 chars), knowledge_dropped, knowledge_chars, **brief** (`file:run/briefs/...md`), round, merge_conflicts.
- `fieldView` (`pages.js:197-203`) renders any list of objects as a `table.sub` with one column for every key any entry has, and each cell recursively. Strings that start with `file:` go to `fileView` (`pages.js:186-194`; `small` is false at depth 1), which fetches the file and renders the **whole Markdown brief inside the table cell**. That is column 15 of 17, so tens of KB of Markdown sit in a narrow cell at the far right. The fields table nests this sub-table inside its own `td`, which pushes it right again. Depth only stops objects at `depth > 2`; files and lists are never stopped. This is exactly "nests to the right, renders nested markdown in tables, most of the page ends up as markdown on the far right".
- There is a cost too. `refreshFiles` (`pages.js:228`) asks again for every `file:` on the page on each 4 s poll (each a 304). With 6 briefs plus other files, that is about 10 requests every 4 s per open tab, against a server that already queues (owner item 2).
- **Short fields take a row each.** The same gap has 47 fields, and 30 are short scalars (rank, rounds, ai_cost_usd, net_lines, `*_at` timestamps and so on). Each gets a full-width row of `table.fields`.
- **History everywhere.** Each row also carries a `details.history` "history (N changes)" (`pages.js:953`). That is 47 disclosures. In the API answer, `history` is 43% of the payload: 32.8 KB of 77 KB for `ticket/SCRUM-2` on :8791. It is sent on every poll, though it is looked at rarely.
- **Change.**
  1. **Facts.** Short scalars (number, bool, or a string of 60 characters or fewer that is not `file:`) go in a flowing grid, `repeat(auto-fill, minmax(11rem, 1fr))`, with the name small above the value. The kind's `show:` fields come first.
  2. **Long fields.** Long text, objects, lists and files go below as full-width blocks, each headed by its name.
  3. **A list of objects is a list of cards,** newest first, the first 3 open and the rest under "N earlier".
     - A card's scalar keys flow on one line, `key value · key value`.
     - A list of short strings wraps as chips.
     - A `file:` value is a closed `<details>` named "brief (34,120 characters)". It is fetched and rendered full width only when opened, and `refreshFiles` skips closed ones.
     - A nested object is a definition list. A table never sits inside a table.
     - A table remains only for a list of objects whose entries all have the same few scalar keys (at most 6), such as `queue_runs`.
  4. **History.** Instead of a disclosure on every field, a field with more than one change gets a small "N changes" link next to its name. The link opens that field's history in one "Changes" section at the bottom. The section is collapsed and filtered to the field, and lists all fields when opened from its own summary. The API sends the history only when asked (`history=FIELD`, or `history=all`), which shrinks the 4 s poll.
- **Risk.** Medium. `fieldView` is shared: the Items list (`small=true`, unchanged), remote items (`pageRemoteItem`), a session's messages (a list of objects, with `LIST_SHOWN`), and claim, decision and action views. Limit the new layout to `pageItem`'s Fields section and pass a mode, so the other callers keep their output. Tests to update: `tests/test_diagram_rendering.py:1021-1030` pins `table.fields tr[data-field=title] details.history` and "history (4 changes)". SPEC §5a (`docs/SPEC.md:1267`) says "each field shows its value and a history disclosure". The API's history default changes, which `--history` in the CLI does not use.
- **Overlaps.** Q53 (the header as words), Q54 (How it moved; the Lease table in a closed `<details>`), Q82 (counts as words, "Not held Attempts 0 of 3."), Q34 (one time format: the `*_at` fields now print as 1,763,... numbers), Q61 ("Send a note" placement). All are filed and all touch `pageItem`, so land this after them or rebase onto them. None of them covers the fields section or `contexts`.

### 20a. The diagram subset the item passed through

- **What exists.**
  - The lease history: each attempt with its block, in `fields.lease.history` (the `leaseView` table: close, merge, ci, fix-ci, sail, review, address and so on on `ticket/SCRUM-2`).
  - The moves (states entered).
  - Sensors that count a kind in a state (stocks) or entering a state (flows), in `spec.sensors()` with `s.items` (`item_sets.counted_by`, `item_systems.kind_systems`).
  - Blocks that `take` a kind, with their `out:` flows (`b.targets()`).
  - `graph.select(model, system, around, depth)` (`ergostat/graph.py:19`) already draws an explicit set of parts for Dynamics when `around=` is given (`server.py:476-514`). That path skips the folded system tree.
  - The Blocks view (`blockdiagram.diagram`, `ergostat/blockdiagram.py:1423`) takes only `open_` and `focus`, so it has no subset.
- **What is missing.**
  1. A function: an item becomes its path, an ordered list of `{state, stock?, flow?, block?, valve?, goal?}`. States with no stock (`leased`, and states no sensor counts) are said as such.
  2. A selector `item=` (and `kind=`) on `/api/graph` for Dynamics, the set fed to `graph.control`.
  3. For Blocks, a rule. A partial control loop is not a block diagram, so the subset is the whole control loops (goals) the path touched.
  4. A decision on the item page: draw it there, or link to `/diagram?view=dynamics&item=ID`. The diagram code (`diagram.js`, 1409 lines, the ELK and libavoid layout) works on global page state (`S.graph`, `#detail`, pins keyed by view). Embedding it in another page is a refactor, and the owner calls layout slow (item 10). The cheap first step is a link that opens the diagram drawn to the subset with the path numbered, plus a one-line strip on the item page: `new → picked (pick-up) → located (locate) → worked (work, 2 attempts) → ...`, each part a link.
- **Size.** Large. Covered by the proposal below.

## 15. A page for a kind

- **Today.** Clicking a kind's name on Items (`pages.js:699-703`, `.kname`) sets `?kind=K`, which filters the Items page to that kind: its state chart, its list (300 at most), its cycle-time chart, Graph and Timeline. The page has no definition and no model context. `/api/items` gives each kind `{name, id, states, show, formats, description, system, system_why, relations, counts}` (checked on :8796). The IR (`ergostat/spec/ir.py:865-889`, `ItemKind`) also holds:
  - `on` (the events that move it);
  - `fold` (how each field folds);
  - `lease` terms;
  - `join`;
  - `final`;
  - `about`;
  - `where`.

  The page shows none of these.
- **Ingredients that exist.**
  - The counting sensors: `spec.sensors()` with `s.items` (state or entering/leaving).
  - The blocks that take it (`b.takes`: at, to, where, order, unblocked) with pool, lease, goal and `out:`.
  - The goals on those stocks (control loops; `snap["loops"]`).
  - Feedback loops through them (`ergostat/spec/causal.py:242`, `loops(spec)`).
  - The process map for the kind (`/diagram?view=process&kinds=K`; `process.py`).
  - The state chart and cycle time (`/api/items-flow`).
  - Graph and Timeline (`/api/items-graph`).
  - Completion estimates (`eta_api.py`).
- **What it takes.**
  1. A footprint function (kind to parts), shared with 20a.
  2. `/api/kinds/K` returning the definition and the footprint.
  3. A home for the page. Recommended: `/items?kind=K` becomes the kind's page, so it is not a new top-level page and keeps every existing address and filter. Owner items 1, 11, 13 and 14 rework the same page.
  4. A filter: state chips with terminal states off by default (item 1); `where` on the kind's `show` fields; search; sort; pages (item 14).
  5. Links into the diagram subset (`/diagram?kind=K`).
- **Design rule.** intent.md says "no new pages". The owner asked for this one in their own list (item 15), so the proposal must say how it satisfies both: the kind's page is the Items page with a kind chosen, the same way `/item/ID` is the show page of a list.

## Proposed gaps

1. `valve-panel-lists-its-leased-items`: quick. No dependencies.
2. `item-page-fields-flow-and-lists-are-cards`: incremental. Land it after Q53, Q54 and Q82; there is no hard dependency.
3. `item-and-kind-footprint-proposal`: writes `docs/proposals/item-and-kind-footprint.md`.
4. `kind-and-item-footprint-api`: depends on 3.
5. `diagram-draws-what-an-item-or-kind-touches`: depends on 4.
6. `the-kind-page`: depends on 3 and 4, and on the Items-page cluster's gaps (owner items 1, 13 and 14) as that plan names them.

Gaps 1 and 2 can start now, in parallel with each other and with the proposal.

## Questions

- Item 20a: should the item page draw the diagram inline (a refactor of `diagram.js` away from global state, plus layout cost on every item page), or is a link to the subset on the Diagram page, plus a textual path strip, enough? The proposal recommends the link first.
- Item 15: is `/items?kind=K` acceptable as the kind's page (no new address), or does the owner want `/kind/K` beside `/item/ID`?
