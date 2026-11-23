# Blocks above the leaf

Proposal, 2026-11-22 (owner item R4, pieces 3-6; the design review of 2026-11-22). At the leaf the Blocks
view already uses textbook notation: summing junctions, r/e/u/y/d, H on the return path, C(z) with a sampler and a hold.
Above the leaf it does not. A closed system is an opaque box `Q`. The top level has no reference, no summing junction
and wires without labels. Inside a system, loops are not laid out in signal order. This proposal settles five things
and confirms or amends the build gaps that follow it. It changes no code.

Where it stands today: `fold()` in `ergostat/blockdiagram.py` makes every closed system a box with
`fn.sym = "Q"` (and `Q(s)` when every part inside is continuous). It bundles the signals between two boxes into one
vector named `y_a` (:1325-1341) and writes `y = Q u` with dimensions counted from the box's ports (:1347-1361). The
disturbances that arise inside the system are not among those ports. When the system is opened, its process shows as
`P` with those disturbances among its inputs, so the letter and the dimensions both change. To a control engineer,
`Q` reads as the Youla parameter (Skogestad & Postlethwaite, *Multivariable Feedback Control*, 2nd ed., §4.8), which
is not what the box means.

## 1. A subsystem is C, P, or a named block

**Rule.** A system is classified only by the wires that cross its border at the level it is drawn, never by what
is inside it. It is read from the folded signal graph, never declared, and always says it was inferred (invariant 11).
A wire is a **u wire** when two things hold. (a) Its signal is set by a controller inside the source system (a
block's output, or a flow that a block drives). (b) The part of the target it enters (a flow or stock) reaches,
along the target's own causal edges, a stock or an auxiliary that carries a goal of the target (a goal names either,
by `stock:` or `auxiliary:`, as in coordinator's `quality.yaml:96-107`). Every other wire is a **y wire**: a
stock or auxiliary of the source that the target reads, or a controller's output that only feeds the target's
bookkeeping (a count or a cost that reaches no goal). A block that reads nothing and is commanded by nothing (the
world, `WORLD_NOTE`) is a disturbance source d, not a controller, so its wires are never u wires. Condition (b) is
what makes a wire a manipulated input: a u that moves no controlled variable is a measurement of the controller's
activity, not a control action (Skogestad & Postlethwaite §10.2, where inputs are chosen by their effect on the
controlled outputs).

- **C** (it controls): at least one u wire leaves it, and no u wire enters it.
- **P** (it is acted on): at least one u wire enters it, and no u wire leaves it.
- **A named block**: every other case. That is either **mixed** (u wires both leave it and enter it: it controls
  one system and is controlled by another) or **neither** (no u wire crosses its border either way: it holds only
  its own loops). The box is labelled with the system's name and no letter, for example `api`. Its inputs are its
  references r, the disturbances d and any y wires. Its outputs are its measurements y. It is the closed-loop block
  T = PC/(1 + PCH), drawn as one block, as in block-diagram reduction (Ogata, *Modern Control Engineering*, 5th ed.,
  §2-3; Franklin, Powell & Emami-Naeini, *Feedback Control of Dynamic Systems*, 8th ed., §3.2).

The three cases are exclusive and cover every system, so each system gets exactly one answer. **Loops a system holds
closed inside it do not enter the rule.** They are inside C (or P) as a cascade's inner loop is inside its outer
controller. So software-factory's `factory` holds backlog-clear, reviews-done and all-live closed, and it is still
**C**: `deployed` is a u wire into `product`, and nothing enters `factory` except product's measurements (y wires).
`product` is **P** (`deployed` drives the flows into `bugs-live` and `missing-ops`, which carry goals). In
ticket-factory, `factory` → `oversight` carries only y wires, so both are named (neither). Its stocks are read by
`prs-awaiting-review`, `cycle-hours` and `repinging`, and `flow.work`, `flow.address` and `flow.fix-ci` drive
`ai-spending` (oversight.yaml:99-109), which fills `ai-spend`. `ai-spend` has no goal and feeds nothing in
`oversight` (whose two goals are on the stocks `actions-waiting` and `stopped`, with no goal on an auxiliary), so by
(b) those three are y wires: they count what the factory's sessions cost.
Each of big's six systems and every `modelling` system is named (neither).

**The same letter and p × m at both levels.** The box carries `C_name` or `P_name` with p × m, where p counts its
outputs and m counts its inputs, **disturbances included**. Skogestad & Postlethwaite (§3.2) write the plant as
G(s), l × m, with d as an input of the generalised plant. Opening the box shows the same letter, and its frame gets
the same p × m. A disturbance that arises inside a closed P (for example from `customers`) is drawn as an arrow
d_name that enters the box from outside, so it is counted at both levels. **Q is dropped** from the code, the math
text, `says` and the docstring. `Q(s)` versus `Q[u]` becomes `P(s)` versus `P[u]` (and the same for C). A named
block keeps "Not identified." in its math text.

## 2. The top level: references, a summing junction, labelled signals, H on the return

When the top level has a C acting on a P, it is drawn as the textbook loop: Ogata §2-3, Fig. 2-9; Franklin, Powell
& Emami-Naeini, Fig. 1.2 and §3.2, the standard feedback loop with the sensor on the return path.

- **r** is the vector of P's goals that C serves: every goal of P, on a stock or an auxiliary, that C's u reaches
  and no controller inside P holds. It is drawn as the reference and sum nodes already drawn at the leaf, ahead of C.
  A goal on an auxiliary is a reference like any other: its y is that auxiliary's value.
- **When r is empty** (every goal C's u reaches is also held by a controller inside P), no loop closes at this
  level: no reference, no Σ and no H are drawn. C and P keep their letters and are joined by their labelled wires
  only, as a one-way row of §3, and P's west port reads "r: none, held inside P (goal names)". C is then a
  feedforward or load on P's inner loops, which is how a measured disturbance entering a loop is drawn (Seborg et
  al., ch. 15). If ticket-factory later puts a goal on `ai-spend` (a budget held inside `oversight`), this is the case
  it falls into.
- **Σ** computes e = r − y_m and feeds C's input port. C's blocks may read y_m itself rather than a goal's error
  (`support` reads `bugs-live`). Their port says so ("reads y_m: bugs-live, …"), as the leaf already does for a
  controller given r beside it. The junction stays ahead of C, because a two-degree-of-freedom drawing (r beside C,
  Åström & Murray, *Feedback Systems*, 2nd ed., §12.1) hides the comparison the owner reads.
- **Every wire between systems is labelled** with its signal and its width: u_factory (deployed), y_product (3). A
  wire carries one bundle (today's vector, renamed from `y_a` to the signal it really is: u when it leaves a C, y
  when it leaves a P).
- **H** is on the return path, beneath the forward path: H_product, made of the sensors that read P's outputs. It is
  diagonal and H = 1 where a sensor gives no dynamics, as at the leaf.

Sketch for :8796, assumed to be software-factory (story G6, `ceb-annotated-sf-top.png`):

```
                                  d_product (customers: signups, churn; ops-broken-per-ticket)
                                       │
 r_product ──►(Σ)── e ──►[ C_factory ]── u: deployed ──►[ P_product ]──┬──► y_product
 no-live-bugs  ▲ −         1 × 3                          3 × (1 + d)    │   bugs-live, missing-ops, users
 few-missing   │                                                         │
 users-growing └──────────── y_m ◄──────[ H_product = diag(1,1,1) ]◄────┘
```

Below this loop, as a second row by §3's rule, sits `r_modelling ──►[ modelling ]──► y_modelling`, and the caption
"no signals between these" is drawn once. `intake` and `delivery` stay inside C_factory (`deployed` is
`delivery.yaml`'s deployer block's output, `out: flow.deployed`). Opening `factory` shows them in its frame under
the same C_factory, 1 × 3. The widths here come from reading the YAML. The build gap's test pins them from `diagram()`.

## 3. Uncoupled systems: parallel rows, each with its own r and y

**The counting rule.** Take the top level's systems as nodes and every wire between two of them, in either
direction, as an edge. **Each connected component is one row.** Every top-level system counts, `modelling` (from
`uses:` or `systems:`) included, with no exception. A row is drawn by §2 when it holds a C and a P. Otherwise it is
drawn as its named blocks joined by their labelled wires, upstream to the left. When there are two or more rows, they
are drawn as **parallel rows**. Each row has its own r on the left and its own y on the right, and the rows are
aligned at their left edges. One caption, **"no signals between these"**, is drawn once, under the last row. So a
top level with a C-P loop and an uncoupled system (software-factory with `modelling`) is two rows: §2's loop
above and the uncoupled system below. This is the multiloop or decentralised form, in which each loop is
drawn and tuned on its own when the plant is diagonal (Skogestad & Postlethwaite, §10.6; Seborg, Edgar, Mellichamp
& Doyle, *Process Dynamics and Control*, 4th ed., ch. 18, where loops with no interaction are drawn as separate
loops). It uses the same top-level assembly as §2 and is built after it. A row is §2's loop with one system: a named
block (§1) with r in and y out, or a C-and-P loop when the row holds a pair. The rows are ordered by the model's own
order of each row's first system (the order of `systems:`, then of the included files, then of `uses:`). Uncoupled
rows have no signal order to follow, and model order is the easiest choice to reverse. It puts `modelling` last in
all four examples.

Sketch for :8797, assumed to be big (`ceb-big-blocks-dark.png`, today seven boxes in a column with no signals):

```
 r_api (4)       ──►[ api       4 × 5 ]──► y_api (4)          (d: api-arrivals enters each box from above)
 r_billing (4)   ──►[ billing   4 × 5 ]──► y_billing (4)
 r_build (4)     ──►[ build     4 × 5 ]──► y_build (4)
 r_data (4)      ──►[ data      4 × 5 ]──► y_data (4)
 r_support (4)   ──►[ support   4 × 5 ]──► y_support (4)
 r_web (4)       ──►[ web       4 × 5 ]──► y_web (4)
 r_modelling     ──►[ modelling       ]──► y_modelling
                         no signals between these
```

By the same rule, the four examples give these rows (top-level systems → rows):

| example | rows, top to bottom | count |
|---|---|---|
| software-factory | {factory → product, §2 loop}, {modelling} | 2 |
| ticket-factory | {factory → oversight, one labelled wire}, {modelling} | 2 |
| big | {api}, {billing}, {build}, {data}, {support}, {web}, {modelling} | 7 |
| the-job | {job}, {modelling} | 2 |

The table assumes, from the YAML, that `modelling` exchanges no signal with the other systems at the top level. If
`diagram()` shows a wire to it, the rule still decides: `modelling` joins that system's row, and the build gap's test
pins the count the rule gives, not this table's.

Systems that are coupled one way only, with no loop closing between them, are one row joined by the labelled wire
(ticket-factory: `factory` → y_factory (pr-open, review-asked, changes-asked, sailed; work, address, fix-ci) →
`oversight`, both named blocks by §1). In ticket-factory the
owner's approvals do not flow back into any factory flow. That is a modelling finding for the owner. It is not
drawn, because the drawing shows only what the model says.

## 4. Inside a system: one loop per row, in signal order

**The layout.** Inside an open system there is **one loop per row**. Each row runs left to right: r, Σ, C, u, the
process, y. Rows are ordered **upstream first**: a loop whose process output or controller output feeds another
loop's process sits above that loop. **Couplings run downward**: an upstream u or y enters the downstream row's
summing junction from above, as a disturbance to that loop. **The sensor sits under its own process**, in the same
row, on the return path. This is how series inventories are controlled and drawn, in the direction of flow
(Buckley, *Techniques of Process Control*, 1964, ch. 13; Skogestad, "Control structure design for complete chemical
plants", *Comp. Chem. Eng.* 28, 2004, §5), with each loop in Franklin, Powell & Emami-Naeini's Fig. 1.2 form.
Loops inside a cycle of couplings are ordered by model order, and the upward edge is the one drawn against the flow.

Sketch for ticket-factory `making` (story G5, `story-6-g5-blocks-making.png`), opened alone with `intake` closed:

```
 row 1  located-worked
        r = 0 ──►(Σ)── e ──►[ C_work  ai ]──── u_work ──┬──► (out to intake: drains located)
               ▲ −                                      │
               └──[H items 3s]◄── y_located (in from intake)
                                                        │ (coupling, downward)
 row 2  worked-opened                                   ▼ +
        r = 0 ──►(Σ)── e ──►[ C_open-pr ]── u_open-pr ─►(Σ)──►[ 1/s worked ]──┬──► y_worked
               ▲ −                            │      −                        │
               └──────────────[H items 3s]◄───│───────────────────────────────┘
                                              └──► +[ 1/s pr-open ] ──► y_pr-open (out to review)
```

The big api chain is the same pattern four times. The rows are q0, q1, q2, q3 from top to bottom, and each drain's
u enters the next queue's junction from above.

**Whether ELK layered can do it.** Not with today's single pass. The options in `blocks.js:131-139` (one layered
graph, direction RIGHT, model-order cycle breaking) choose layers along x and only an order within a layer, so a
loop's parts land wherever crossing minimisation puts them. Proposed, as the hypothesis to settle with
diagram-layout-engine-proposal: give each loop a layout-only compound node (a "row", never drawn as a frame), lay
out each row with layered RIGHT, and stack the rows top to bottom in the order above (`elk.direction: DOWN` with
`elk.layered.considerModelOrder.strategy: NODES_AND_EDGES` and `crossingMinimization.forceNodeModelOrder`). Then
route the couplings across the rows. ELK's INCLUDE_CHILDREN uses one direction through the whole hierarchy. So
either the rows are laid out with SEPARATE_CHILDREN and the couplings run through hierarchical ports on the rows'
edges, or `blocks.js` stacks rows that ELK laid out separately and routes the downward couplings itself (vertical
then horizontal, which is short code). The second option is the fallback if a spike shows ELK misroutes the first.
Either way, the tests in the build gap below decide whether it is done.

## 5. A closed block's r, y and status on its ports

blocks-closed-block-r-y-and-status puts each closed block's references and measurements on it, and the worst status
of its loops. On a classified block:

- **Named block**: r is its input port on the west side (a vector of its loops' setpoints, its tooltip listing each
  `≤ 20`). y is its output port on the east side (the measured values). d enters on the north side. The status is
  the box's outline: the worst of its loops' statuses, in the one order **unknown, off, stale, open, holding**
  (worst first). A loop with no status, or missing from the snapshot, counts as unknown, so a block holds only when
  every loop is read and holding: what cannot be read counts as the worst case. This puts unknown ahead
  of `off`, unlike `WORST` in `ergostat/fold.py:18` (off, stale, open, unknown, holding), which the system boxes use.
  The Blocks outline follows this order; aligning `fold.py` is for the owner and not part of these gaps.
- **C**: no r of its own at the top. Its input port is e, or y_m with the note from §2. Its inner loops' worst status, in the same order, is
  the outline, and the "inside" row of its panel lists them.
- **P**: y is its output port. Its status is the worst, in the same order, of its goals not held inside it, on
  stocks and auxiliaries alike. These are the top loop's r, so each is shown again on its reference node's value, as
  at the leaf.
- Nothing new is added to the page. All of this is on the box, its ports and its existing panel rows (the rule of no
  new panels).

That gap therefore depends on blocks-classified-subsystems. Its port names follow §1, and it must not write `Q`.

## The build gaps, and the tests each must add

The four build gaps are confirmed, renamed as below (the names are this proposal's), and ordered. One amendment:
the closed block's r/y/status gap waits on the first.

1. **blocks-classified-subsystems** (§1). `tests/test_blocks_classified.py`:
   on software-factory at the top level, `sys:factory` has `fn.sym == "C"` (although it holds loops closed inside)
   and `sys:product` has `"P"`. On big, `sys:api` is a named block with no letter, and so are ticket-factory's
   `sys:factory` and `sys:oversight` and every `sys:modelling`. A fixture with three systems a → b → c, each joined
   by a u wire, makes `b` a named block (mixed). A fixture where a block's flow in `a` drives a flow of `b` makes `a`
   C and `b` P when that flow fills a stock of `b` with a goal, and leaves both named when the stock has none (rule
   (b)). A third variant, where that stock has no goal but feeds an auxiliary of `b` that has one, makes `a` C and
   `b` P too, and its top level draws a reference node for the auxiliary's goal. On ticket-factory, the edges from `flow.work`, `flow.address` and `flow.fix-ci` into `oversight` are marked
   y, and the factory → oversight label lists them. For every example and every top-level system, the class equals the
   one §1's rule gives from the edges' u/y marks, computed in the test, so each system has exactly one class. For every example and every system, the letter and p × m of the closed
   box equal those of its frame when it is opened (`focus=` the system), with disturbances counted. No node's `fn`,
   math text or `says` contains `Q`, across all examples. Each of these fails on main today.
2. **blocks-top-level-loop** (§2). `tests/test_blocks_top_loop.py`: software-factory at the top level has one
   reference node per goal of P that C serves, a sum node whose edge goes into `sys:factory`, an H node on the
   return from `sys:product` to the sum, and a non-empty `signal.sym` on every edge between systems. `sys:modelling`
   is drawn, and it is not on that loop: no edge joins it to the sum, H, `sys:factory` or `sys:product`. A fixture
   C → P whose every reached goal is held inside P has no reference, sum or H node, keeps `C` and `P`, and P's port
   reads "r: none". The Blocks
   browser file must show, on software-factory: the sum to the left of C, H below the forward path, and each label
   drawn on its wire.
3. **blocks-uncoupled-rows** (§3, after 2). Unit: for every example, the top level's rows are exactly the
   connected components of its system-to-system edges (computed in the test), `modelling` included, and there is
   one caption "no signals between these" when there are two rows or more, none with one. Pinned by §3's table:
   big 7 rows, the-job 2, ticket-factory 2 (`factory` and `oversight` in one row with a labelled wire, then
   `modelling`), software-factory 2 (the §2 loop, then `modelling`). Each row has its own reference and y. Browser: the rows' vertical extents do not overlap, their left edges are equal, and the caption is drawn
   once.
4. **blocks-rows-per-loop** (§4, with diagram-layout-engine-proposal). Unit: each node in an open system carries
   its loop's row index. In ticket-factory `making`, located-worked's row is above worked-opened's. In big `api`,
   q0 < q1 < q2 < q3. Browser, on both: each loop's parts lie within its row's band, each sensor's horizontal centre
   lies within its process's width and below it, every coupling edge points downward, and no row's parts are drawn
   out of the r → y order.
5. **blocks-closed-block-r-y-and-status** (§5, amended to follow 1). Unit: a named block's input ports include r
   (a vector of its loops' setpoints) and its output ports y. Its status is the worst of its loops' statuses in a
   given snapshot, in §5's order: holding + unknown gives unknown, off + unknown gives unknown, off + holding gives
   off, all holding gives holding, and a loop absent from the snapshot gives unknown. A P whose only goal not held
   inside it is on an auxiliary takes that goal's status. Browser: the outline's class follows a change of the
   snapshot.

Not one of these gaps, and proposed as its own: **status-order-aligned**, which makes `WORST` in `ergostat/fold.py:18`
follow §5's order (unknown worst) so that a system box and its Blocks outline cannot show different worst statuses.
It is the owner's choice. Until it lands, the two views can differ for a system with an unknown and an off loop.

Each new test is to be seen failing against main first (review lesson 9). The report says which ones were.

## Choices made alone, and easiest to reverse

- :8796 is read as software-factory and :8797 as big, from the screenshots' names. Each sketch's form holds for
  the other example if that reading is wrong.
- The gap names in the list above are this proposal's own. The rows of uncoupled systems follow model order, and
  the junction is kept ahead of C rather than using the two-degree-of-freedom drawing.
- §1 reads "mixed" as controlling one system and being controlled by another, and classifies by border wires only,
  so inner loops never change the class. `modelling` is counted as an ordinary system in every example.
- A controller's output counts as u only when it reaches a goal of the target (rule (b)), rather than ticket-factory
  being reclassified as C → P with an empty r. Dropping (b) gives that reclassification, and the empty-r case in
  §2 already draws it.
- A goal counts for rule (b), for r and for P's status whether it names a stock or an auxiliary. In the four
  sketched examples nothing changes: software-factory's and ticket-factory's goals are all on stocks, and the-job's
  goals on auxiliaries are inside its one system `job`. coordinator and image-squeeze do set goals on auxiliaries
  (`work.yaml:244`, `quality.yaml:96-107`; `intent.yaml:74`, `lab.yaml:169`, `rollout.yaml:141`), and their
  classes were not worked out by hand here. Test 1 computes them from the rule.
- Unknown is ranked worst in the Blocks outline. `fold.py`'s order for the system boxes is left as it is and
  proposed as its own gap (status-order-aligned) for the owner.
- The widths in the sketches come from reading the YAML. A script that prints `diagram()` could not be run in this
  session. The build gaps' tests pin the real widths.
