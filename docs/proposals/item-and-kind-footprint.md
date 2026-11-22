# What an item or a kind touches: the diagrams' subset, the item page's picture, the kind's page

Proposed 2026-11-22, for owner items 15 ("the whole picture of an item type") and 20 ("the subset of the Dynamics
and Blocks diagrams it passed through"). The data side is the footprint: for a kind, the parts it touches; for
an item, the parts it passed through, with how often (the gap kind-and-item-footprint-api). This settles how that is
drawn and where it is shown. Each decision is a default: the four gaps in §6 go ahead on it without asking the
owner, and each says the alternative and why it lost. Line numbers are as of `main` at cc75b443.

**What a footprint is, in the model's words.** A kind touches a part when the part is counted from its items or acts on them:
a stock or auxiliary with an `items: K` sensor (SPEC.md:1694, 1912), a flow counted from K's moves between states
(SPEC.md:1696, 3579), and a block whose `takes:` reads K (SPEC.md:1488). An item's footprint is the part of its
kind's footprint it went through: the stocks whose states it entered and the blocks (valves) that took it. Below,
the footprint is a set of part names, plus counts for an item. If the footprint API lands with another shape, the
gaps adapt to it. The decisions below do not depend on its shape.

## 1. How the diagrams draw a subset

**Decision: an explicit set, addressed by what it is about.** `/diagram?view=dynamics&item=ID` and
`/diagram?view=dynamics&kind=K` (and `view=blocks` with the same two). The server's `graph` answer
(ergostat/web/server.py:474-514) reads `item` or `kind`, asks the footprint for its part set, and draws exactly
that set, the way `around=loop/NAME` already draws an explicit set (ergostat/graph.py:24-30) rather than a
neighbourhood. `graph.select` (graph.py:19) gets a `parts=` argument that returns the set as given. `graph.control`
already brings in a drawn flow's two ends (graph.py:116-119), so a flow in the set never hangs in the air.

- *Alternative: `around=kind/K` or `around=item/ID`.* It loses. `around` means "within `depth` steps of one part"
  (graph.py:20, 31-52). A kind is not a part, and its set is not a neighbourhood. The model's rule is that no word
  means two things (SPEC.md:36). `item` and `kind` are also the words the Items page already uses in its
  addresses (pages.js:557, 615).
- *Alternative: the whole diagram with the set lit and the rest greyed.* It is kept only as the fallback for an
  oversized set (cost, below). As the default it loses: it pays the whole layout every time (owner item 10), and
  owner item 20 asks for the subset, not the whole.

**Dynamics** draws the set's stocks, flows, valves and auxiliaries as stock-and-flow structure. A feedback loop (R
or B) is marked only when every link of it is in the set. Half a loop marked R would claim a reinforcement the
drawing does not show.

**Blocks: whole control loops.** Today `blockdiagram.diagram` takes only `open_` and `focus` (blockdiagram.py:1423).
The server passes `system` as the focus and ignores `around` (server.py:488-492). It gets `loops=`, a set of goals:
every goal whose loop has a node in the footprint (the `nodes` per loop that diagram() already lists,
blockdiagram.py:1430-1436). Each such loop is drawn whole: its goal, comparator, controller, actuator (valve),
process and sensor. Nothing outside those loops is drawn. A part of the footprint that is in no control loop (a
stock no goal holds) is not drawn in Blocks. The strip below the drawing names it, with a link to Dynamics.

- *Alternative: draw only the touched blocks.* It loses. A block diagram is the loop: controller, actuator,
  process, sensor and the feedback path (docs/DISCIPLINES.md, the Block diagram row; SPEC.md:45-46, "the loop it
  closes"). A loop missing its sensor or its controller would read as an open loop, a structure the model does
  not have.

**How the path is marked.** For an item: each stock it entered carries a small number, how many times it entered.
Each valve that took it carries its attempts (`2 attempts`, the second the one that moved it on). Drawn parts it
never reached (in Blocks, the rest of a touched loop) are drawn faint, as `highlightLoop` dims what is outside a
loop (diagram.js:834, 973). For a kind, the numbers are its items in each stock now, and each valve's attempts on
the kind in the window. The order of the visits is not drawn. Order is the process map's reading
(`/diagram?view=process&kinds=K`, DISCIPLINES.md: process mining). The Dynamics and Blocks views draw structure.

- *Alternative: number the steps (1, 2, 3...) along the pipes.* It loses. A rework loop revisits a stock, so
  ordinals pile up on one shape. The process map already draws exactly that sequence.

**The folded system tree.** A drawn set is drawn flat, as `around` is today: the server folds only when `around` is
unset (server.py:501), and the page turns system outlines off when `around` is set (diagram.js:1034). `item` and
`kind` join that same condition. Each part still names its systems in its panel (graph.py:124, `systems=`). This
is the reversible choice, because it adds no new fold path.

- *Alternative: fold, with the systems the set touches opened.* It is deferred, not refused. It needs `fold`
  (ergostat/fold.py:61) to take a part set as well as `open_`. It can be added later with no change of address.

**Pins.** Today the pin key is `ergostat.pins.<project>.<view>.<system>.<around>` (diagram.js:1032). A drawn set
adds `.kind:K`. An item's drawing uses its kind's key too, so all of a kind's items share one arrangement. An
item's set is a subset of its kind's, and a pin for a part that is not drawn is ignored.

- *Alternative: key by item id.* It loses. Each item would make its own localStorage key, which grows without
  bound and is never cleared. The same item drawn again after more moves would also keep pins laid out for a
  different set (lesson-5).

**Cost, on the factory's own model (dev/model, about 800 parts).** Not measured here. The server side is one
footprint lookup plus `graph.control` over the set, which is linear in the model (graph.py:104-130). The browser's
layout grows as about shapes^2.8 (190 s for 280 shapes, docs/proposals/scale.md:302). So a kind that touches a
tenth of the model lays out in a small fraction of the time the whole system takes. The gap
diagram-draws-what-an-item-or-kind-touches measures the largest kind footprint in dev/model and records it. A set
over 150 shapes is not laid out flat. It falls back to the folded whole with the set lit, and says so above the
drawing.

## 2. The item page's picture

**Decision: an inline drawing on demand, built last** (item-page-draws-its-path). It comes after the path strip and
the links to the subset (item-page-says-where-it-went). The item page (pages.js:912) gets a *Where it went* section
right after its state track (pages.js:942) and before *Lease* (pages.js:985). The section holds the path strip: the
stocks entered, with their counts, and the valves that took the item, with their attempts, in words. The track and
*How it moved* (pages.js:944) stay as they are, because they read the kind's states. The strip reads the model:
which stocks and valves those states were. It also has two links,
`/diagram?view=dynamics&item=ID` and `view=blocks&item=ID`. The strip and the links answer owner item 20 without
any drawing. Then a *Draw it* button draws the Dynamics subset in place, below the strip. The drawing is static:
no panel, no pins, no pan state kept. A click on a shape opens the full diagram at the item's address.

**The renderer refactor it needs, and its cost.** diagram.js runs on page-global state: `S.graph`, `S.layout`,
`S.pins`, `S.pinKey`, `S.hl` and others (172 uses across 15 files in ergostat/web/static), and one side panel,
`#detail` (diagram.js:936; details.js). The Guide already draws diagrams inside its own page by setting those
globals for one drawing at a time, through a queue (guide.js:74-98, `guideDrawNow`). The item page needs only that:
move `guideDrawNow` into a shared `drawStatic(svg, graph, view)`, used by both the Guide and the item page. It
saves and restores the `S` fields it sets, so a drawing never leaves state behind. That is about 40 lines moved and
10 new. No other page shares this page's `S`: the split pane is a separate frame with its own (split.js:5,
13), and a diagram page sets its own `S` fresh on each route (diagram.js:1031-1034).

- *Alternative: a per-mount renderer* (`mountDiagram(el, ask)` with its own state object in place of `S`). It loses
  for now. It means rewriting about 172 uses in 15 files for a drawing that needs no interaction, and it puts the
  main diagram, the thing most used, at risk. It is the right change if a page ever needs two *interactive*
  diagrams. That would be a gap of its own.
- *Alternative: an iframe of `/diagram?item=ID&pane=1`.* It loses. It is a page inside a page (decision 1). It
  loads every script a second time and runs a second poll timer. In a snapshot (one file, no server; util.js:14)
  there is no second address to frame.

## 3. The kind's page

**Decision: the Items page with exactly one kind chosen, at `/items/<kind>`.** `/items?kind=K` redirects to it with
`replaceRoute`, and every other parameter is kept: `/items?kind=K&state=S&view=graph` becomes
`/items/K?state=S&view=graph`. There is no new nav entry: the nav lights its entry by the path's first part
(util.js:501-502), so *Items* stays lit. The server already answers the address, since anything under `items` is
one of the page's own (server.py:35, 76-77). The client adds one line to `route` beside `/item/` (util.js:511),
calling the same `pageItems` with the kind chosen. The split pane must not take `/items/K` for a diagram: add
`"/items/"` to `OTHER_PAGES` (split.js:26). Today it matches only `/items` exactly. Snapshot mode works unchanged:
`#/items/K` is a page path by its first part (util.js:16), and the data asked for is the same `items` request with a
kind (pages.js:615).

**How this squares with decision 1 and R12.** Decision 1 (no new pages; the house rule "show things through the
diagrams, the system boxes and the Items tab") is kept. This is the Items page in one of its states, drawn by the same
function, under the same tab, at an address that can be shared. R12 is not in this clone. It is read here as
invariant 12 (ergostat adds nothing of its own accord, CLAUDE.md): the page shows only what the owner declared
under `items:`, and nothing ergostat adds. If R12 means something else, the gap the-kind-page checks it before it
is built.

- *Alternative: `/kind/K`.* It loses. It is a new first part in two lists (util.js:15, server.py:35), so in effect a
  new page. The nav would light nothing, or need a special case. The kind's list and filters would be drawn by a
  second function that drifts from the Items page's own (the two-surfaces problem §4 settles).

**Its sections, in order.**
1. *The kind's bar* (§4): title, description, whether it finishes (has a final state) or lives on, and the state
   chips with their counts. These are the header and *states now* in one, the same markup as on the Items page.
2. *In the model*: the footprint as a list. Stocks and flows counted from the kind, the blocks that take it, and the
   goals that hold those stocks (each goal a control loop). Then three links: `/diagram?view=dynamics&kind=K`,
   `view=blocks&kind=K`, and the process map `view=process&kinds=K`. No drawing inline. The links are the picture
   (§1), and an inline drawing waits for the same static renderer as §2.
3. *Definition*: the kind as declared (its states in order, lease, fields, the file it is in), read-only, linked to
   the Model page.
4. *Chart and cycle time*: the cumulative flow diagram the Items page already draws per kind (pages.js:709-711)
   and the cycle-time scatter.
5. *The list*: the kind's items, open, filtered as on the Items page.

## 4. The one kind bar

**Decision: one function, `kindBar(kind, opts)`, in a new `ergostat/web/static/kinds.js`.** It draws the kind's
bar: title (with its name, mono), description, finishes / lives on, state chips with their counts, and the total.
It is used on both surfaces with the same markup. It replaces the `card` closure on the Items page
(pages.js:700-712), which today draws a name and either the state boxes or the flow chart.

- On the Items page each kind's bar is a disclosure. Opening it opens that kind's list in place, under the bar,
  without leaving the page. The kind's name in the bar is the link to `/items/<kind>`. Today the name toggles the
  filter (pages.js:701); the disclosure takes over that job.
- On the kind's page the same bar sits above *In the model*, with its list open.
- Filtering is the same on both. A state chip sets `state=` on the current address (`/items?…` or `/items/K?…`)
  through the one `pick` (pages.js:699). A second click clears it. The set chip and its × (pages.js:695-697) work
  the same way on both.
- `kindBar` returns an element keyed by the kind's name (`key: k.name`), so `patch` matches it by key and never by
  position (lesson-5). Its handlers are passed in through `opts`, never closed over a build's rows.

The gap the-kind-page tests that the bar's markup for one kind is the same on both surfaces, apart from the
disclosure's open state.

- *Alternative: two renderers, a card on Items and a header on the kind page.* It loses. Two surfaces showing the
  same counts by two code paths drift apart: one gets a fix and the other does not (lesson-7).
- *Alternative: no bar on the Items page, only the kind page.* It loses. The Items page is where the kinds are
  compared side by side, and owner item 15 asks for the picture without removing the overview.

## 5. The filed fixes that move

Q57, Q58 and Q61 are in the factory's queue, not in this clone, so their texts were not read here. The rule
applies by content. What Q57 and Q58 ask about a kind as a whole moves into the-kind-page (the bar, *In the model*,
*Definition*). What they ask about one item's travel moves into item-page-says-where-it-went (the path strip). Both
gaps cite the fix they absorb. Q61 is closed as superseded by §3 and §4.

- *Alternative: land the fixes as filed, before these gaps.* It loses. They would change the very card (pages.js:700)
  and item page sections these gaps rebuild: two changes on one surface, each passing alone (lesson-7).

## 6. The follow-on gaps, confirmed and amended

In order. Each depends on kind-and-item-footprint-api.

1. **diagram-draws-what-an-item-or-kind-touches** (confirmed). §1: `item=` and `kind=` on `/api/graph` for
   Dynamics and Blocks, `graph.select(parts=)`, `blockdiagram.diagram(loops=)`, the marks, the pin key, the flat
   drawing, and the 150-shape fallback with its measurement on dev/model. Tests: a kind's Dynamics set equals its
   footprint plus its flows' ends. A Blocks drawing holds every node of each touched loop and nothing else. A
   kind's pin key is the same for its items. The browser file tests/test_diagram_rendering.py covers the marks.
2. **item-page-says-where-it-went** (confirmed; amended: it may land before 1, with its links gated until 1 is on
   main). §2's *Where it went* strip and links. It absorbs the item half of Q57/Q58.
3. **the-kind-page** (confirmed; amended: depends on 1 for its links). §3 and §4: `/items/<kind>`, the redirect,
   `route` and `OTHER_PAGES`, `kinds.js` with `kindBar`, the sections in order, the same-markup test, and the kind
   half of Q57/Q58. Browser file: tests/test_items_page.py.
4. **item-page-draws-its-path** (confirmed; amended: last, after 1 and 2). §2's *Draw it*, built on `drawStatic`
   moved out of guide.js. The per-mount refactor is not part of it.

## Checked against DISCIPLINES.md and vocabulary.md

- *Feedback loop* is the system dynamics term (R or B, docs/vocabulary.md, "Feedback and structure"). It is used
  only for Dynamics (§1). *Control loop* is the control term, a goal with its controller, actuator and sensor
  (SPEC.md:45-46, 2046). It is used only for Blocks. A *goal* is what a control loop holds (vocabulary.md, Reference
  (setpoint)), never a "target" or a "loop" on its own.
- *Taken, not held.* A block **takes** an item (its lease, SPEC.md:1488, 1514). A goal **holds** a stock. The path
  marks say "attempts" on a valve and "taken by" in the strip, never "held by". The kind's bar says an item is
  *taken* when it is leased.
- Each drawing stays in its discipline (DISCIPLINES.md, and the decision "One model, three drawings"). Dynamics
  draws stock-and-flow structure, Blocks whole loops, and the process map the order. No new symbol is invented for
  a path: a number on a shape and faint shapes are the marks already in use.
- *Valve* here is the model's actuator on a flow (vocabulary.md, Valve and Actuator rows). *Item*, *kind*, *agent*
  as in NOTES.md. No task, ticket or job.
