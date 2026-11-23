# Owner item 17: a Gantt that predicts the real timeline

Designer's notes, 2026-11-22. Read only; screenshots `shots/plan-gantt-*.png`.

## What the owner sees, and why

The owner: the Items page Gantt "stacks every gap as far left as possible, as if 100 gap runs start at once. We have a
system dynamics model and a control model; a small simulation should give a real estimate of what finishes when and in
what order."

**The simulation already exists.** `ergostat/numbers/eta.py` is a discrete-event Monte Carlo over every open item
together: semi-Markov paths per kind, Kaplan-Meier stays, queues at each block in its `takes:` order, at most each
block's capacity at once (its pool read from its stock now, agent seats, daemon concurrency, workspace pools), leases'
ages, rework, precedence relations and arrivals (SPEC §5a *Completion estimates*). `web/eta_api.py` works it out on a
worker thread, and `merge()` gives the Timeline a levelled run (`projected` bars, lanes, p50 ticks, p90 whiskers). The
roadmap demo draws it well (`plan-gantt-road-timeline.png`, `plan-gantt-road-lanes.png`).

**What the owner is looking at is the fallback.** When `est` is None or has no items, `merge()` returns `eta: None`
and the Timeline draws `precedence.py`'s critical-path forward pass, which the module says itself is "Not levelled":
every unblocked item starts at 0 (now). That is exactly "every gap as far left as possible".

**Why the factory falls back** (confirmed on a synthetic input, `scratchpad/gantt-exp/paused.py`): an item in a
*paused* state (`messages: paused: {gap: [parked]}`, added with the backlog work, commit 600535dc) is kept in
`inp.items` but `_Run.enter` returns without ever finishing it. `_Run.go` loops `while self.heap and self.open > 0`;
with arrivals on, the heap never empties and `open` never reaches 0, so **every run simulates the full 90-day horizon**.
On 60 items with one paused item: 53 runs in 5.1 s instead of 200 in 0.1 s, and the kind's last finish is None
("beyond the horizon"). The live factory has hundreds of open gaps, many blocks, and parked gaps (plus gaps whose
`depends_on` reaches a parked gap, which also never start): the first run cannot finish in the 5 s budget, `simulate`
breaks with `n = 0`, `items` is `{}`, and the page shows the unlevelled forward pass, forever. The same holds for an
item waiting at a block commanded off. Nothing in `tests/test_eta.py` covers a paused item.

The live page (`:8798/api/items-graph?kinds=gap`) did not answer within 5+ minutes during this review (the server was
saturated by other reviewers' requests: owner item 2), so the live answer could not be read directly; the code path
above is the explanation, and the first gap's acceptance test checks it on the live record.

**Second problem: the order.** Even with estimates, `relTimeline` sorts rows by `segments[0][1] ?? es ?? first`. An
open item has segments from its first move, so open gaps are ordered by when they were created, not by when they are
projected to start. The backlog is ranked (`takes: order: rank`), so the projected bars come out scattered rather than
as a readable waterfall. The owner asked "what finishes when **and in what order**".

**Third problem: the control model is not in it.** The simulation reads each pool at its value now and holds it. The
factory's capacity is set by its control structure: `implementor-pool` and `reviewer-pool` are stocks moved by the
pool controller (`dev/model/pools.yaml`), `implement-when` and `review-when` gate on `ai-budget`, the machine's
headroom and `machine-full`, `plan-when` on `planning-open`. The page itself says "Not modelled: a goal that switches
a block off, a capacity no block declares". `numbers/closedloop.py` already runs the control structure forward beside
the stocks (the engine's own goals and built-ins, identified models for machine blocks). Coupling the two is what the
owner literally asked for, and it is research: whether it improves the estimates must be shown by the backtest
(`tests/eta_backtest.py`, its ablation flags), not assumed.

## The right design (within the rules)

No new page or panel: the Timeline that exists, the legend that exists, the item page's estimate that exists.

1. **The schedule is always the simulated one.** Never draw the forward pass as if it were a forecast. Until the
   estimates are worked out, draw what happened and one line: "Working out the schedule: a simulation of 412 open
   gaps at each block's capacity (implementor 9, reviewer 6, planner 12)". The forward pass stays only for the
   critical path's highlight.
2. **Held items are said, not simulated to the horizon.** A parked gap, a gap waiting (however far back) on a parked
   gap, and an item waiting at a block switched off are *held*: no projected bar, grouped at the end of the Timeline
   with their reason ("waits on gap/x, parked"). The run ends when every movable item finishes. The legend: "last of
   40 gaps expected Tue 14:10, by Wed 09:00 at worst (9 in 10); 3 held, not projected" (Q60's sentence form).
3. **Rows in projected order.** Open items by projected start (p50), then p50 finish, with the finished above as what
   happened (collapsed per Q60). A waterfall from the now line.
4. **Capacity is visible.** The note names the capacity each block is simulated at and where it came from ("pool
   stock.implementor-pool reads 9 now"); Lanes stays the view of it.
5. **The control model, after evidence.** A proposal decides how the control structure enters the schedule
   (time-varying capacity from a closed-loop projection, or each block's measured on-share), judged by the backtest on
   the factory's own record; the Timeline says which was used.
6. **Trust from calibration.** One clause in the note: "last week's estimates: 8 in 10 gaps finished by their p90",
   from the backtest run on the record. This is how a user decides whether to believe a Gantt; it is cheap once the
   backtest exists.

## Agreement with the review and filed gaps

- **Q60** (`gap/ui-the-finish-estimate-is-a-clock-time-that-agrees`): agrees and is extended. Q60 fixes the sentence's
  form and opens the Timeline at now; it does not fix that there is no estimate at all on the factory. Gap 1 makes the
  estimate exist; gap 2 builds on Q60's sentence (held count, capacity) rather than re-doing it.
- **Q59** (`gap/ui-timeline-draws-each-item-s-states-over-time-rela`): complementary. Q59 makes the Timeline draw for
  kinds without relations; gap 2 changes what is projected and the row order. Gap 2 should land after Q59 or merge
  with its change in `relTimeline` (same function).
- **R6** (forecast in words, computed with the page, horizon stated): same direction for goals; gap 2's "working out"
  line and clock-time sentence follow R6's wording rules.
- **Owner item 18** (Dashboard, a Gantt panel): the panel reuses `relTimeline`; it inherits these fixes.
- **Owner item 2** (slow pages): the live API did not answer within minutes; the eta worker is off the request path,
  but `precedence.build` for hundreds of gaps is on it. Not in this cluster; noted.
- No conflict with the owner's rules: no new page or panel, nothing editable, items stay items.

## Gaps proposed

1. `eta-held-items-end-the-run` (incremental): the bug; the estimates exist on the factory.
2. `ui-timeline-shows-the-simulated-schedule-in-order` (incremental, after 1): what the user sees.
3. `schedule-with-the-control-model-proposal` (proposal, after 1): the control model in the schedule, decided by the
   backtest; it splits itself into build gaps.
4. `eta-calibration-said-on-the-timeline` (incremental, after 1): the backtest on the record, one clause.

1, 3 and 4 can run in parallel once 1 merges (3 and 4 only need 1); 2 after 1, alongside 3 and 4.
