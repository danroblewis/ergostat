# Owner items 15, 20, 16: the item kind, the item page, held items on a valve

Designer's notes, 2026-11-22. Read only; demos :8792 (the-job), :8793 (image-squeeze), :8794 (roadmap); code at
DESIGN/ergostat (main). Screenshots in DESIGN/shots/, prefix `plan-ks-`.

## What I saw

### The live factory (:8798) did not answer
`GET /api/items/gap%2Fregression-guarantees-proposal` got no answer in 500 s; `GET /` and `GET /api/status` got none
in 60 s and 88 s (many design agents were reading it at once). So I could not screenshot the owner's example. What
follows about it comes from the code and the factory's model (`ergostat.yaml`, `dev/bin/brief.py`). This is also
evidence for owner item 2: one busy server stops answering every page, not just slow ones.

### Item 16: the valve panel says "0 leased now" while two items are held (a bug, not only a missing list)
roadmap, Dynamics, `delivery`, valve `started` (`plan-ks-road-valve-started.png`):
- "developer works items of kind ticket: 0 leased now. Show the leased items", while the same panel's "Items through
  it" lists two rows "leased by developer", and `/api/items` shows `ticket/e203-release` in state `doing`, held by
  developer. Three reads in a row gave the same result.
- Cause: `spec/item_sets.py::leased_by` counts items in the state `leased` only (`states=[LEASED]`). A run that
  takes an item and sends its first event (developer: `ticket.started` → `doing`) moves it out of `leased` while it
  still holds the lease. The count and the link's set are both wrong whenever a block records progress.
- Even when right, the panel gives a count and a link to another page; the owner asks for the items themselves.
- The Blocks view's panels for the same valve/block have no held-items list at all.

### Item 20: the item page
Seen on `/item/ticket%2Fe201-integrate` (:8794, `plan-ks-road-item-leased.png`), `/item/review%2F2243` (:8792,
`plan-ks-job-item-review.png`, `plan-ks-job-review-2.png`) and `/item/hypothesis%2F11` (:8793,
`plan-ks-is-hyp-2.png`).
- **Fields are one per row at full width**, each with its own "history (1 change)" disclosure under it: a one-word
  field ("author Hana") takes ~65 px of height; four short fields fill a screen. Nearly every field has exactly one
  change, so the disclosure says nothing.
- **Nested values**: `fieldView` (web/static/pages.js:182) draws a list of records as a table whose columns are the
  union of their keys, and calls itself for each cell, including `file:` values, which `fileView` renders in full
  (markdown rendered, code highlighted). The factory's `contexts` field (fold `append`) is a list of dicts from
  `dev/bin/brief.py::assemble`: role, template, guides (a list), files (a list), findings, definition_chars,
  gaps_entry, brief_chars, brief_tokens, diff_chars, model, the knowledge carried, round, merge_conflicts, and
  `brief: file:run/briefs/....md`. So each gap's page has a ~15-column table, one row per session, whose last column
  holds a whole rendered brief (several thousand words of markdown, with h1s) per row. That is exactly the owner's
  "nests to the right, renders nested markdown in tables, most of the page ends up as markdown on the far right".
  The same happens, smaller, on the-job's `brief` field (an h1 "Review brief: ..." inside the value column).
  `reviews`, `plan_reviews`, `queue_runs`, `resources`, `join_verdicts`, `measured_runs` are lists of records too.
- **Leasing is told three times and its path not at all**: the Lease table ("Not held Attempts 0 of 3." runs
  together, Q82), the "How it moved" table (`review → leased → done`: the state it was reviewed in is lost, Q54), and
  raw `ergostat.lease.*` events. Nothing says which stocks it was counted in or which valves moved it, and nothing
  links to the diagram (Q58).
- What is good and should stay: Relations (with its derived inverse), the order header → lifecycle → relations, the
  Events table with its rollup note.

### Item 15: no page for a kind
- The kind name on the item page and on Items links to `/items?kind=ticket`, which only filters the list
  (`plan-ks-road-items-ticket.png`): the kind's description sits small on the system's heading line, its states are
  chart legend chips, and nothing names its stocks, flows, the blocks that lease it, or its loops.
- Everything needed is already in the model: sensors with `items: {kind}` (what counts it, `item_systems.py`), blocks
  with `takes: {kind}` (what leases it: pool, attempts, TTL, targets = flows), the blocks' goals (control loops),
  `causal.loops(spec)` (feedback loops through those parts), the kind's `on:` (events → states), `fold:`, `relations:`,
  `join:`, `show:`, and the process map (`process.py`) for its states.

## Judgement

### 15: the kind's page is the Items page with one kind chosen
The owner asks for it explicitly, so it overrides "no new pages" in the sense that matters (a place that answers
"what all is this item?"). The cheapest way that adds no navigation entry: the Items page with exactly one kind
chosen becomes that kind's page, at its own address `/items/<kind>` (and `/items?kind=<kind>` goes there). The
review agrees in substance: Q61 (each kind says what it is, finishes or lives on), Q57 (link to the process map, 'now
N' per state), Q56 (labelled state chart). Those three become sections of the kind page instead of decorations of a
list heading. It also answers owner item 11 (the heading of a kind is hard to find: on its page it is the h1).

Sections, in order:
1. h1 the kind's plain name; its description; `gap/*`; "finishes: merged, closed · parked can resume" or "lives on";
   the system it belongs to and why (`system_why`).
2. **Now**: one line per state with items in it now, final states folded ("+ 2 final states, 1,212 items"), each a
   link that filters the list below. The state chart over the window under it (Q56's labelling).
3. **In the model**: a table, one row per part: stocks that count it (and in which states), flows that move it (on
   which events), blocks that lease it (pool, attempts, TTL, how many held now), the goals those blocks serve, and
   the feedback loops (R/B with their names) through those stocks and flows. Each name links to the diagram with
   the part selected (Q36). The process map of the kind (a recognised diagram for states) is one link: "its states as
   a process map".
4. **Definition** (collapsed `<details>`): events → states (`on:`), fields shown, how each field folds, relations
   (to which kinds, precedence or parent), joins, the lease rule.
5. **Items**: the existing list for that kind, with the filter the Items page gets from the owner's items 1, 3, 4,
   13, 14 (terminal states hidden by default, filters without reload, real pagination). Not redesigned here.

### 20: the item page, three changes
1. **Fields flow; nested values never nest sideways.** Short scalar fields (number, short text, link, state) sit in
   a flowing grid (`repeat(auto-fill, minmax(14rem, 1fr))`, name above value), in the kind's `show:` order; long or
   structured fields follow full width, one per block. A list of records is a list of rows: each row shows its
   scalar keys on one line ("implementor · round 2 · opus · 41k tokens · 6 guides"), and anything nested or a file
   sits under a closed disclosure on its own full-width line ("brief (12,400 words)"), rendered only when opened. A
   file's contents are never drawn inside a table cell. Depth beyond two is a disclosure with the JSON, not an
   80-character cut. Per-field history: shown only for a field that changed more than once, as "changed 3×" beside
   its name, opening below it; a field set once has none (it is in Events).
2. **Where it went: its path through the model.** A section after the lifecycle: the item's own chain, drawn the
   stock-and-flow way as a row of the stocks it was counted in, with the valve and the block that moved it between
   them and the time it spent in each ("todo 15s → started by developer (run 2f02cb16, 4s) → in-progress → ...").
   It replaces the Lease table (kept as Q54's closed "Attempts (N)"). Two links draw the same subset on the real
   diagrams: Dynamics and Blocks with `around=item/<id>`.
3. **The subset of the diagrams on the page.** The owner asks for the diagrams themselves on the item page. Done
   second, behind a closed section ("Draw its path"), so the item page stays fast, using the diagram renderer
   mounted into a box with `around=item/<id>`. It depends on the diagram being mountable outside its page and
   should follow, not race, the layout rewrite (owner item 10).

### 16: held items on the valve's panel
Fix the count (held = has a lease holder, whatever its state), then list the held items in the panel: id (link),
title, its state, run (link to the session/Record), held for, expires in (overdue in the accent colour), attempt
n of max. At most 10, then "all N held" to the Items set. Same section in the Blocks panel of the block/valve. The
same row is what Q30 asks for in a goal's evidence ("holding: ticket/SCRUM-7 (leased 03:26, 40s left)"): one helper.

## Where the owner and the review agree, conflict, combine
- Agree: Q53 (header in words), Q54 (states not leases; lease table collapsed), Q55 (path taken), Q58 (counted in, a
  link back), Q61 (kind says what it is), Q57 (process map from Items), Q30 (goal links to held items), Q82.
- Combine: Q55's path strip and Q58's "counted in" link become one "Where it went" section (gap
  item-path-through-the-model); it should land after them and absorb them, not draw a third lifecycle form.
- Conflict: the intent's "no new pages" against the owner's kind page. Resolved by making the kind page the Items
  page with one kind chosen, at its own address, with no new nav entry. The inline diagram on the item page is a new
  panel by the intent's rule; the owner asked for it by name, so it is in, but on demand and last.
- Q61 says "Send a note" only on held or waiting items: keep; the flowing fields put the facts above it.

## Proposed gaps
1. ui-held-items-on-the-valve-panel (quick): owner 16. Fix + list.
2. ui-item-fields-flow-and-nested-values (incremental): owner 20 (fields, history, contexts).
3. item-path-through-the-model (incremental): owner 20 (the path, links to the diagram subset).
4. ui-item-page-draws-its-path (incremental): owner 20 (the diagrams inline). After 3.
5. item-kind-anatomy-api (incremental): owner 15, the server side.
6. ui-item-kind-page (incremental): owner 15, the page. After 5 and the Items-list gaps for owner items 1, 13, 14.
