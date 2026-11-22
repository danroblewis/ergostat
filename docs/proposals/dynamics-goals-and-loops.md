# Dynamics: every goal drawn, and which feedback loops are drawn, named or folded

Status: proposal (2026-11-22). The leaf notation stays Sterman's. This settles two modelling
decisions that cost layout: which goals get a desired level and a gap, and which loops get a
marker. The build gaps are `dynamics-every-goal-drawn` and `dynamics-minor-loops-folded-and-named`.
This proposal confirms both and amends them (see the end).

Sources: Sterman, *Business Dynamics* (2000), ch. 4 (goal-seeking structure: desired state,
discrepancy, corrective action), ch. 5 (causal loop diagrams: §5.2 guidelines, loop identifiers,
naming loops, making the goals of balancing loops explicit, not drawing every loop in one diagram).
Dominance: Schoenberg, Davidsen and Eberlein, "Loops that Matter" (2020), which `dominance.py`
already implements.

## Where software-factory stands today

The demo's subject has three systems (`product`, plus `intake` and `delivery` inside `factory`) and
six goals. Each factory goal has a desired level and a gap: `backlog-clear`, `reviews-done` and
`all-live`, each named by its block. **None of the product's three goals has one**:
`no-live-bugs`, `few-missing` and `users-growing`.

**Why** (`ergostat/dynamics.py`, `dynamics()`): a gap is kept only if a connector leaves it
(`acting`). A connector leaves a goal only when a block reads the goal (`goal:` or `goal.x`).
`support` reads `stock.bugs-live`, and `product-manager` reads `stock.missing-ops` and
`stock.users`. Neither reads a goal, so the causal links run stock → block → flow, and the goal
gets only the link in (stock → error). Its gap feeds nothing, so it is put in `idle`, dropped,
and shown only as a `goals` badge on the stock (`acted: False`, pinned by
`tests/test_dynamics_view.py`). The goal is served (SPEC §12a: a block that names no goal serves
the goals whose loop closes with it), but not drawn.

**The names pile up for the same reason.** Every long loop runs bugs-live/missing-ops/users →
intake → delivery → `deployed` → back into the product. It passes through the three factory goals
and none of the product's. A loop with no `loops:` entry takes as its head the first goal by name,
so all of them become `all-live via …`.

**The '+1'** (`dynamics.js` `sdMarker`) counts the other loops in a marker's group: loops whose
drawn parts are the same, which differ only inside a closed module. Nothing says so.

## 1. Every goal drawn, in its own system

**Rule.** Every goal in an open system is drawn as Sterman's goal-seeking structure (ch. 4), in the
goal's own system, beside the stock or flow it is about:

- a **desired level**, an auxiliary holding the value (`desired bugs-live = 0`);
- a **discrepancy**, drawn the way it is today: `excess X` (actual − desired) for a ceiling, and
  `X gap` (desired − actual) for a floor or a level held. The actual feeds it and the desired
  level feeds it with the opposite sign;
- the **corrective link**: a connector from the discrepancy to each flow moved by a block that
  serves the goal (SPEC §12a *serves*). When that block reads the goal's own stock, not the goal,
  the stock → flow connector is **routed through the gap** (stock → gap → flow), not drawn twice.
  This is Sterman's §5.2 guideline: make the goals of balancing loops explicit. The decision acts
  on the discrepancy, not on the bare level. Routing inserts a node on a link that already exists,
  so it adds no loop and removes none. Its sign is the sign the §12a table already gives such a
  read (+ for a ceiling, − for a floor), so the sign is derived, not made up;
- the **"no feedback" mark**, when no block serves the goal: the desired level and the gap are drawn
  anyway, and the gap ends in a short stub labelled *no feedback* (the stub glyph shadows already
  use). Sterman's ch. 5 point is that a goal with no corrective action is an open loop and should
  be seen as one. Today such a goal becomes a badge and vanishes from the structure.

**Another system.** The gap stays with its goal (in `product`). The corrective connector crosses
the system edge, under the rules §12a already has for crossing lines: both systems open, a line
drawn as itself; the actor's system closed, the line ends at a **port** on the module's edge,
named for the flow it drives (`filed-bugs`); the goal's system closed, the gap shows as a shadow
`<excess bugs-live>` inside the actor's open system. No new glyph.

The `goals` badge on a stock stays only for a goal in a closed system (its module draws no parts).

## 2. Which loops are drawn

Sterman (ch. 5) marks the loops that carry the argument and keeps the rest out of the figure. Here:

- **Drawn**, with a marker: (a) each loop a `loops:` entry names; (b) **one per goal**, its
  goal-seeking loop. That is the shortest *balancing* loop through its gap, named by the goal
  unless a `loops:` entry already names it. Ties go by dominance (below), then by the name of the
  first flow. One loop counts once even when it is both (a) and (b).
- **Minor**: every other loop. It is listed in the side list under *Minor*, with its path, and drawn
  (marker, parts lit) only while it is selected there.
- **'+1' removed.** Two drawn loops whose visible parts are the same (they differ only inside a
  closed module) get one marker, for the higher-ranked loop. The other moves to *Minor* with "drawn
  as R2 here". No marker carries a count.
- **Rank and cap.** Drawn loops are ranked by **dominance now**: from `/api/dominance`, each loop's
  relative score in the last bucket, taking the most it gets at any stock it runs through. A loop
  that is not scored, or a model with no replay, ranks after every scored one, by: named, then
  goal-seeking, then shortest, then name. The cap is **9 markers per canvas**, about as many as one
  of Sterman's larger causal loop diagrams marks. It is a constant, so easy to change.
  Loops past the cap move to *Minor* with "over the cap" beside them. Goal-seeking loops go first,
  then named ones: a goal's structure is never left unexplained by a named loop of lower rank. The
  rank is worked out when the view or the window changes, never on a poll, so markers do not swap
  as numbers move. A cap is a ceiling, so every count here is bounded.

## 3. Loop names

A `loops:` entry names a loop in the model (SPEC §12a: `through` or `goal`). This stays as it is.
What changes is where each form is shown. The **diagram shows the name** under the marker, never
a path. **The panel and the side list show the path** (the members as drawn, in order) under the
name. A goal-seeking loop with no entry is shown by its goal's name. A minor loop with no entry
keeps the §12a head-and-via name, but only in the list. That is where "via" naming belongs (it
tells siblings apart), and it never reaches the canvas.

**Names for software-factory.** These are model edits to `examples/software-factory`, made by the
build gap that draws them. `rework` is already named in `factory/delivery.yaml`.

```yaml
loops:
  bug-fixing:        # B: what support files is fixed by a release (goal no-live-bugs)
    through: [flow.filed-bugs, flow.fixes]
  regressions:       # R: a release breaks what worked, which files more bugs, which brings more releases
    through: [flow.filed-bugs, flow.regressions]
  features-shipped:  # B: what customers ask for is filed, built and shipped (goal few-missing)
    through: [flow.filed-features, flow.shipped]
  users-won:         # B: shipping what was missing brings users in (goal users-growing)
    through: [goal.users-growing, flow.shipped, flow.signups]
  long-tail:         # B: more users ask for more, and what is missing drives them off (limits to growth)
    through: [flow.asks, flow.churn]
```

`users-won` names the loop because `users-growing` has several balancing loops of the same length
(through `shipped` or `fixes`, then `signups` or `churn`). No rule chooses one without dominance,
so the choice is the modeller's (Sterman §5.2: name the loop for the story it tells).

## 4. What the counts then mean

- **On a closed system's box** (today "N feedback loops inside": loops through it with fewer than two
  parts drawn outside): from now on it counts the loops **every one of whose members is inside** the
  module, closed within it. A loop that crosses the module's edge is counted where it is drawn or
  listed, not on the box. One loop is then never counted on two boxes, as it can be today (the
  `every` set in `sdLoopList` works around that).
- **In the side list**, the heading is `Feedback loops · D drawn · M minor`, with D + M the number
  of elementary loops in the view. *Inside* rows still name each closed module's own count.
- Q22 (filed; not in this clone, so its wording is not quoted here) is answered by these two
  definitions: the box counts what is closed inside it, and the list counts what the canvas shows.
  `goals-and-loops-cross-referenced` (also not in this clone) should take this heading form. If it
  lands first with another form, the build gap adopts that form and keeps the two counts.

## 5. Layout cost on :8797 (software-factory, product open)

Derived from the model, by hand, not measured. The session could not run the graph: a scratch
script was refused, so the build gap measures and records the real numbers.

- **Parts**: +6 auxiliaries in `product` (3 desired levels, 3 gaps). Today the product sector draws
  3 stocks, 6 flows and 1 auxiliary, so it grows by about one row of labels.
- **Connectors**: +9 (3 desired → gap, 3 stock → gap, 3 gap → flow) and −3 (the stock → flow reads
  they replace), a net of +6. Lines crossing product ↔ intake: 3 before, 3 after (the same reads,
  now leaving from the gaps).
- **Markers**: from 18 loops (piled, some under '+N') to 9 with everything open (the cap). The canvas loses at least 9 marker labels, each a circle and up to two lines of
  path name, and gains 6 short auxiliary labels, so it ends with fewer labels than today.

### Before / after (product open, factory closed)

Before (the gist of story-6-g3-dyn-product.png: no goal structure, path names on the canvas):

```
 [users] ══churn══▶          R1 +1  "all-live via regressions and churn and asks"
   ▲ signups (− bugs-live, − missing-ops)   B3 "all-live via churn and asks"   … 18 loops
 [bugs-live] ◀══regressions══ (factory)     goals: badges on bugs-live, missing-ops, users
   │ ══fixes══▶
   └──────────(+)──────────▶ filed-bugs ▸ factory
 [missing-ops] ──(+)───────▶ filed-features ▸ factory
 [users] ────────(?)───────▶ filed-features ▸ factory
```

After:

```
 desired bugs-live = 0 ──(−)▶ excess bugs-live ◀(+)── [bugs-live]
                               └──(+)──────────▶ filed-bugs ▸ factory
 desired missing-ops = 1 ─(−)▶ excess missing-ops ◀(+)── [missing-ops]
                               └──(+)──────────▶ filed-features ▸ factory
 desired users = 180 ────(+)▶ users gap ◀(−)── [users]
                               └──(+)──────────▶ filed-features ▸ factory
 markers: B bug-fixing · R regressions · B features-shipped · B users-won · B long-tail
 side list: Feedback loops · D drawn · M minor (paths under the names; no '+N')
```

## Acceptance, as counts, for the build gaps

**dynamics-every-goal-drawn** (confirmed, amended to route the read through the gap and to add the
no-feedback stub):

- software-factory, `open=*`: 6 `desired:` and 6 `gap:` nodes (today 3 and 3); 0 `goals` badge
  entries with `acted: False` (today 3: on `bugs-live`, `missing-ops` and `users`); 0 connectors
  `stock:bugs-live → flow:filed-bugs`, `stock:missing-ops → flow:filed-features` or
  `stock:users → flow:filed-features`; exactly one connector each from `gap:no-live-bugs`,
  `gap:few-missing` and `gap:users-growing`. Signs: + from the first two, + from `users gap`, and
  − from `stock:users` into it. The elementary loop count is unchanged from the count before the
  change, measured on both sides.
- `product` open and `factory` closed: each of the three corrective connectors ends at a port of
  `factory`.
- image-squeeze and big: the number of `gap:` nodes equals the number of goals in open systems (big:
  24, one `hold:` each). Every gap already drawn there keeps its id and label. Its connectors are
  unchanged, except where a stock read is now routed through it.
- A goal with no serving block (a test model): 1 desired, 1 gap and 1 *no feedback* stub, and no
  badge.

**dynamics-minor-loops-folded-and-named** (confirmed, amended with the cap of 9, the rank and the
removal of '+N'):

- software-factory `open=*`: exactly 9 markers (`backlog-clear`, `reviews-done`, `all-live`,
  `rework`, and the five names above), at most 9 on any canvas, 0 `marker-more` elements, and 0
  marker names containing ` via `. The side list's heading says D drawn and M minor, with D + M
  equal to the number of elementary loops, so M is that number less 9 (9 on the definition's count
  of 18; the build gap states the count it measures).
- Selecting a minor row draws its marker; deselecting removes it (0 minor markers at rest).
- The box counts in big: the sum of the "inside" counts equals the number of loops with every
  member inside a closed module (no loop counted twice).
- The model edits above land with `demo_check` passing on software-factory.
