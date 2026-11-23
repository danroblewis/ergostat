# Owner item 17: a Gantt that predicts real timelines (engineer's notes)

## What the owner sees, and why

The Items page's Timeline (`ergostat/web/static/relations.js:222`, `relTimeline`) draws, for each unfinished item,
`x.projected`. That comes from one of two places:

1. **The completion estimates** (`ergostat/numbers/eta.py`, a discrete-event Monte Carlo over every open item with
   each block's capacity, run-time curves, rework, dependencies and arrivals; worked out in a thread by
   `ergostat/web/eta_api.py`, merged in by `eta_api.merge`). The levelled run replaces the projection.
2. **The fallback**, when there are no estimates: the critical-path forward pass in `ergostat/precedence.py`
   (`cpm`, line ~170; `build`, `plan = cpm(...)` near the end). It is deliberately **not levelled** (its docstring
   says so): every unblocked or queued item starts at 0, as if each had a worker of its own.

So the simulation the owner asks for already exists. The owner sees the fallback because **on the live factory the
estimates have never been worked out**:

- `~/.ergostat/ergostat-factory-678f59af/run.log` has **6,443 lines `eta: KeyError: 'how'`** and no successful one.
- Reproduced offline on a copy of the factory record (scratchpad `gantt-home/`, script `gantt-replay.py`):
  `etamodel.read` → `_leases` → **`ergostat/numbers/etamodel.py:292` `elif r["how"] == "ack":`** raises. An open run
  (taken, not ended: no `how` yet) on an item whose lease `_fold` does not see (the factory's own events move a gap to
  `building` after the take, so the item is not in `leased`) falls through to that branch. `_work`
  (`eta_api.py:83-95`) swallows it, caches `None`, the page gets `eta: null`, and relations.js draws the forward pass
  with no word that the simulation failed (`relations.js:362-366`: the note only speaks of estimates when they exist).
- The fallback on the factory record (`gantt-replay5.py`): of 112 projected gaps, **103 start at now**; the
  critical path "done in about 7.6 h" for ~110 gaps with a median gap duration of 3.2 h. That is the owner's
  "as if 100 gap runs start at once". (84 of them are `queued`, in `ready`, a state a block takes from; `cpm` counts a
  queued item as started, `precedence.py` `plan = cpm(d, pairs, [... st in ("active", "queued") ...])`.)
- The page asks again every refresh, so every request on the live server pays for a failed simulation attempt at most
  every 30 s (`EVERY`): another small contributor to item 2.

## With the one-line fix, is the answer real? Not yet

Replayed with line 292 patched (`gantt-replay2.py`, `gantt-replay3.py`, `gantt-replay4.py`):

| what | finding |
|---|---|
| capacities | implementor 36 (its `pool: {now: stock.implementor-pool}` reads 36: `run/pools.json` says 36), reviewer 20, planner 12, merge-queue 1 |
| real concurrency | `stock.gaps-building` over the last day: mean 6.1, max 20, **now 1** with 97 gaps ready. `block.machine-full` = 1 now: the `implement-when` gate (`dev/model/building.yaml`: `busy < min(pool, busy + room)`, `1 - full`, `1 - over`, intake open) is what binds, not the pool |
| simulated concurrency | 36 implementor runs at once in the first hours; all 151 gaps' expected starts within 6 minutes of now |
| the record's attempts | implementor: 2,144 attempts, **1,463 are uncounted give-backs put off 300 s, under 30 s long** (the run refusing: drain, machine full), 523 real runs (median 16 min). merge-queue: 744 of 870 uncounted give-backs. `attempt()` replays these as runs that hold a seat and push the item back: rework that is really the gate closed |
| cost | all kinds together (the page's call): **1 run in 8.5 s** (budget 5 s): no p90, near-useless. Gaps only, no arrivals: 200 runs in 4.4 s; with arrivals: 30 runs in 62 s |
| why so slow | a run ends when every tracked item finishes (`_Run.go`: `while self.heap and self.open > 0`). Paused gaps (`parked`: 43) and those waiting on them (55 in all) never finish, nor do items of kinds that live forever (`pool: [held]`), so **every run goes to the 90-day horizon**, generating arrivals at 7.75 gaps/h all the way |
| result | p50 finish quantiles of gaps 19 h to 1,149 h with arrivals; 20.9 h to 46.8 h without. Neither matches a factory that merges a handful of gaps an hour when the machine has room |

So item 17 is three things: (a) a bug that keeps the existing simulation from ever running on the large case, plus
a page that does not say so; (b) the simulation misreading the control loop's refusals as work, and not knowing the
gates (the control model) that really set the factory's concurrency; (c) the owner's real ask, a projection that runs
the control model and the system dynamics model together with the items.

## What exists to build on

- `numbers/closedloop.py`: the model run ahead with its loops running (`Shadow`: the engine's own goals and built-in
  blocks on a shadow state, from `start_of`; machine blocks as identified models from `blockmodels.py`). Already used
  by `etamodel.gated_off` to see a block switched off **now**; never stepped during the item simulation.
- `numbers/simulate.py` (`project`, with a control hook): the SD projection of stocks and flows.
- `eta.py`'s hooks: `_Run.room(b)` decides whether a block may take; `wake(t)` is called on every event. A gate
  evaluated in `room` from the run's own counts (items per state = the `items:` sensors) is the natural seam.
- `tests/eta_backtest.py`, `tests/eta_synthetic.py`: the ablation backtest that decides what stays
  (`docs/roadmap/overnight/eta.md`). It dropped the Little's-law server cap because none of its four records had a
  gate; the factory is the record where it binds.

## Overlaps with filed quick fixes and redesigns

- **Q60** `gap/ui-the-finish-estimate-is-a-clock-time-that-agrees` (one sentence with a clock time, on first paint, not
  earlier than the critical path's end; the Timeline opens at now): its "present on first paint" needs estimates
  that exist (gap 1) and a fallback that is levelled (gap 3); its "not earlier than the critical path" holds only once
  the forward pass is not the unlevelled one. Gap 3 extends it; it should land after gap 1.
- **Q59** `gap/ui-timeline-draws-each-item-s-states-over-time-rela` (Timeline without relations): independent; the
  same `relTimeline`, so gap 3 and Q59 touch the same function (rebase, no conflict in intent).
- **R6** ('Off' tells the truth; the forecast computed with the page) shares the closed-loop projection; the proposal
  (gap 4) must say whether the goals' forecast and the items' estimates are one run of one projection (the owner's
  "one model") or two.
- Owner item 2 (slow pages): the estimates' worker runs in the web process and competes for the GIL; gap 1 removes
  the failing attempts and the 90-day runs, the proposal settles where the coupled simulation runs.
- Owner item 18 (Dashboard: a Gantt panel) reuses whatever this produces; no extra work here.

## Risks

- Gap 1 is low risk (a crash fix, an early stop, a sentence). It changes every estimate on records with paused items
  (they stop being simulated to the horizon): the backtest must not move on the four existing records (no paused items).
- Gap 2 reintroduces something the backtest once dropped; keep it only if the backtest says it helps on a gated record
  and does not hurt the others.
- Gap 4/5: coupling the engine's gate evaluation into a 200-run Monte Carlo may cost too much; inputs that are not
  item counts (AI spend, machine headroom) need their own projection or are held, which may be no better than gap 2's
  measured cap. That is why it starts as a proposal with a backtest bar.

## Sizes

1. quick (about 50 lines: etamodel.py, eta.py, eta_api.py, relations.js, tests).
2. incremental (about 120 lines: etamodel.py, eta.py, tests/eta_synthetic.py, tests/test_eta.py, SPEC §5a).
3. incremental (about 80 lines: precedence.py, relations.js, tests): a levelled fallback for first paint and for a
   moment travelled to, which never has estimates (SPEC §5a: "of now only").
4. large: proposal `docs/proposals/control-aware-estimates.md`.
5. large: the build the proposal defines.
