# Forecasts, promises, quotes, frozen windows and calibration (proposal)

Definition: `dev/records/forecast-promise-proposal.md`. Written 2026-11-24. It builds on
[control-aware-estimates.md](control-aware-estimates.md) (called *CAE* below) and does not repeat it.

The owner wants to add work knowing three things: that it will be done in the right order, that its prerequisites
come first, and what it does to the timeline. The estimates must also be abstracted from the Gantt so that other
features can use them. This proposal settles how the existing completion estimates become a **forecast**, a result
with a stable shape. On that result a model can declare **promises**, ask for **quotes**, hold **frozen windows** and
**calibrate**. Every one of these is a general part of the core. Each is off unless a model declares it. None names a
production style.

**One estimator.** Everything here is worked out by the Monte Carlo that already runs over every open item
(`ergostat/numbers/eta.py`, from `etamodel.py`). Quotes reuse its what-if path, and calibration reuses its backtest
(`numbers/etacheck.py`, `tests/eta_backtest.py`). No second estimator is started. Where something needs a number
the simulation does not yet keep, the simulation keeps it. Nothing new simulates on its own.

**Illustrative numbers.** The worked examples (§9) use figures worked out by hand from the stated shares. Nothing in
this file was run on a record, and nothing was measured on the live instance. The one figure the build is held to
exactly, the binomial table of §9.2, is said as a check the build's test must reproduce.

## What already exists, and what is new

| part | exists (file) | new here |
|---|---|---|
| Monte Carlo over every open item: paths with rework, Kaplan–Meier stays, queues at capacity, leases, dependencies, arrivals | `numbers/eta.py`, `numbers/etamodel.py` | per-run finishes kept as a quantile ladder (p05…p95) and not only p50 and p90 (§1) |
| per item: p50, p90, start, dead share, counted-out share, runs, why | `eta.simulate`, `eta.reasons`, `web/eta_api.py` | `waits_on` as data, `basis`, per-stage entries (§1) |
| per kind: when its last open item finishes | `eta.simulate` `kinds` | per **group** (a `group: true` relation) and per **stage** (§1) |
| the levelled schedule the Timeline draws | `eta.simulate` `schedule`, `eta_api.merge` | the Timeline reads the forecast and not the simulation's raw answer (§1) |
| what-if: `block.NAME.pool`, `block.NAME.failure` | `closedloop.parse_whatif`, the eta worker's cache | hypothetical items, run as a quote (§4) |
| a block's gate worked out once at now; pools read from stocks | CAE §1–§3 (its build: control-aware-completion-estimates) | nothing: used as CAE settles it |
| where an item is held as one of many (a batch naming it; how many are ahead of it), read from the record's relations, never a precedence, group or remote's | `why/within.place`, in the why answer (SPEC §5a, *Why it is not done*) | nothing: kept apart from `waits_on` (§1) |
| one worker thread that simulates on demand: a page's ask, at most every `EVERY` 30 s, the latest asked first, gone after a minute idle; calibration only when no ask waits | `web/eta_api.py` (`estimates`, `_worker`) | a **standing run**: on a schedule, asked by no page, taken before any page's ask, the worker kept alive for it (§1, *Standing runs*) |
| a background thread the runner starts beside the engine, bounded per period | `remote/refresh.start` (in `cli/running.py`), `remote/items.period` (`LEAST`/`MOST`) | the standing schedule started the same way, its periods clamped the same way (§1) |
| take order (`takes:` order, `unblocked`, `order:`) shared by the dispatcher and the simulation | `leases/ready.take_key` | a frozen term at the front of the key (§5) |
| backtest at past cuts: p50 MAE, p90 coverage, bias | `numbers/etacheck.score`, `tests/eta_backtest.py` | promises scored, and the forecasts as said recorded and scored (§6) |
| the Timeline's calibration line ("8 in 10 tickets finished by their p90") | `etacheck.calibration`, `relations.js` | a second clause for the recorded forecasts, and promises kept against their level (§6) |
| goals' risk: chance a goal is off over the horizon, from the closed-loop runs | `closedloop.risk` (`p_ever_off`) | read as a stock's service level for make-to-stock (§2) |
| remote API (`/remote/v1/`: status, model, events, items, counts, readings, series, process) | `web/remote_api.py`, `remote/` | `/remote/v1/forecast`, and a relation `forecast: true` that reads it (§7) |

## 1. The forecast as a stable result

The forecast is one JSON answer, `forecast/v1`, made by a new small module `ergostat/numbers/forecast.py` from
`eta.simulate`'s runs. The Gantt (Timeline and Lanes), the Items tab, an item's page, promises, quotes, the CLI
(`ergostat forecast [--json]`), `GET /api/forecast` and the remote API all read this one shape. The Timeline's
`eta_api.merge` takes its bars and words from it, so the Gantt is one reader among several and not the owner of
the estimates. It is worked out in the eta worker, never on a request, as now (SPEC §5a). When a model
declares something that must happen whether or not anyone is looking, it is also worked out on a schedule
(*Standing runs*, at the end of this section).

```
{"schema": "forecast/v1", "at": T, "version": MODEL_VERSION, "runs": 200, "seed": 1, "horizon": 7776000,
 "basis": {"since": T-14d, "flags": {...}, "whatif": [...], "assumed": {block: why}, "limits": {block: L},
           "capacity": {block: n}, "sources": {block: words}},
 "items":  {ID: {"p50": T, "p90": T, "mean": T, "start": T,
                 "finish": {"p05","p10","p25","p50","p75","p90","p95"}, "beyond": 0.0,
                 "dead": 0.0, "out": 0.0, "runs": 200,
                 "waits_on": [{"on": "block", "name": "welders", "ahead": 9},
                              {"on": "item", "id": "order/118", "binding": 0.62}],
                 "stages": {"inspect": {"enter": {"p50", "p90"}}, ...},
                 "basis": {"curves": {"weld": {"runs": 311, "whose": "own"}}, "visits": {"weld": 1.33}},
                 "why": "...", "unscheduled": "", "promise": {...}}},
 "groups": {PARENT_ID: {"members": 12, "open": 9, "finish": {...}, "by": {"good": {"p50": 10, ...}}}},
 "kinds":  {KIND: {"finish": {...}, "open": n, "unscheduled": n, "visits": {...}}},
 "stages": {KIND/STATE: {"clears": {...}, "per_hour": x}},
 "promises": {...}, "calibration": {...}}
```

- **Finish-time range.** The ladder is the empirical quantiles of the runs' finishes, with `beyond` the share of runs
  not finished within the horizon. With fewer than `eta.FEW` runs, only p50 is said, as now: the rest are null and
  never extrapolated. `p50`, `p90`, `mean`, `start`, `dead`, `out`, `runs`, `why` and `unscheduled` keep the keys
  and meanings `eta.simulate` gives them today, so today's readers are unchanged; `finish.p50` equals `p50`.
- **Per group.** A group is a parent under a `group: true` relation (SPEC §5a, `parent`). In each run, the group's
  finish is the latest finish of its open members and of the parent itself. `by.good` counts, per run, the members
  that reached a *good* finished state (§2) by each moment of the ladder, which is what an N-of-M promise reads.
- **Per stage.** A stage is a state of a kind. Per item, `stages.S.enter` is when the item first enters S after now:
  its p50 and p90 over the runs that reach S. This is kept only for the states a model's promise or frozen window
  names, plus the kind's finished states, so memory stays items × named states × runs. Per kind and state,
  `stages.clears` is when the items in or bound for S now have all left it, and `per_hour` is entries per hour over
  the first 24 h. `per_hour` is the same count CAE §6 exposes as `flows: {flow: per hour}`: CAE's `flows` is this
  count read at each flow's sensor state (`entering: S`), so it is one number under one name, not two.
- **What it waits on.** This is the data behind today's `why`. The block and its place in the queue, or the state,
  come from `eta.reasons`. The unfinished items it names come with `binding`: the share of runs in which that item was
  the last thing released before it moved (counted in `_Run.done`). Also listed: a gate closed now (CAE §7), a frozen
  window ahead of it (§5) and a remote item (§7). The words in `why` are made from this list, so the two cannot
  disagree. It does not repeat the why answer's `place` (`why/within.py`): that one reads which unfinished items
  hold this one through a relation that is neither precedence, a group nor a remote's (a batch naming it), from the
  record now. The simulation does not model such a hold, so it is not a forecast wait and is not listed here; the
  why answer keeps saying it beside the forecast's words.
- **Basis and sample size.** `runs` is the Monte Carlo's run count. `basis.curves` gives, for each state or block the
  item passes, how many recorded stays or runs its curve is drawn from and whose curve it is (own, the kind's, every
  kind's: `KindIn.said`). `visits` is the fundamental matrix's row (the rework). The top `basis` names the record's
  window, the flags, any what-if, the blocks run on an assumed curve, and CAE's limit at now for each gated block.

The answer is versioned by `schema`. A new key may be added, and a key's meaning is never changed under the same
schema. That is what "stable" means here, and what a remote reader relies on (§7).

**Standing runs.** Today's worker is demand-driven: it simulates only when a page asks, and it stops after a minute
idle. A frozen window (§5) and recorded calibration (§6) cannot rest on that. The order would lapse whenever no page
is open, and the forecasts recorded "as said" would sample only the moments someone looked, a biased sample. So:

- **Started by the runner, not by a page.** A new small module, `numbers/standing.py`, is started by the runner
  beside the engine, as `remote/refresh.start` is (`cli/running.py`), also under `--no-web`. It runs only when the
  model declares `frozen:` on a block or `forecast: {record: …}`. Otherwise it is never started and nothing changes.
  The worker loop and its queues move from `web/eta_api.py` to `numbers/etaworker.py` unchanged, so the engine does
  not import the web package. `web/eta_api.py` keeps `estimates` and `merge`, which call it.
- **One schedule per model.** Its period is the shortest declared `frozen.every` or `forecast.record`, each clamped
  to its bounds below. When a pass is due, it puts one job, `standing`, on the worker's queue. The job runs the plain
  forecast (no what-if) once, at the standing seed. From that one result it writes each due frozen list (§5) and the
  due recorded forecast (§6), so the two never read different runs.
- **Never starved.** The worker takes a due `standing` job before any page's ask and before calibration. The
  last-asked-first order of page asks is kept below it. A page waits behind at most one standing simulation (the
  existing `BUDGET` of 5 s). While a standing schedule is declared, the worker does not exit when idle.
- **Each pass is recorded, as one small event.** Every pass, failed or not, ends by writing `standing.pass` {`at`,
  model version, `ok`, the reason when not ok, and `lists`: for each frozen block, the `seq` of the list it holds in
  force and that list's renewed `until`}. It is about the item `ergostat.standing`, so the roll-up folds old passes
  as it folds frozen lists (§5). This is the one place a pass's `at` is kept, with or without `forecast.record`. At
  most 96 a day, each a few dozen bytes per frozen block. A failed pass renews nothing.
- **A pass that does not happen is said, never read as fine** (lesson 3). Lateness is measured from the newest
  `standing.pass` by `seq` whose `ok` is true, never from a list's age: a list that has not changed for a day while
  every pass runs is not late. When the newest pass failed, or the newest good pass is more than two periods old
  (or none was written within two periods of the runner's start), the engine's health reports it, and each frozen
  block's why says "last standing pass 3h ago (refresh every 1h)". When `standing.pass` cannot be read, health says
  so in the same way and the lists are read without their renewals (§5). The last list stays in force up to its
  renewed `until` and lapses after it. Since every pass renews every frozen block's list and `for` is at least three
  times `every` (below), one missed pass never lapses a list, and health reports a late pass a full period before
  any list can lapse. A list that lapses all the same is said at once (§5). A missed recorded pass is counted in the
  next pass's summary as `missed: n`.
  It is never filled in afterwards, since a forecast made late is not what was said then.
- **Page forecasts are never recorded.** Only standing passes write `forecast.made`, so the recorded sample is the
  schedule's and does not depend on who looked when.

**Bounds** (lesson 4). Each one is refused outside its range when the model is checked (`bad-frozen`,
`bad-forecast`, `bad-promise`) and clamped again at run time, as `remote/items.period` clamps a remote's `every`:

| number | range | default | why it is bounded |
|---|---|---|---|
| `frozen.every` | 15 min … 1 d | 1 h | standing passes a day: at most 96 |
| `frozen.for` | 3 × `every` … 7 d | 1 d | how far a list reaches; at least three periods, so one missed pass never lapses it (§5) |
| `frozen.most` | 1 … 200 | 100 | ids in one `block.frozen` event |
| `forecast.record` | 1 h … 1 d | (none: off) | recorded passes a day: at most 24 |
| items in one recorded pass | at most 200 | | the side file's growth (§6) |
| `forecast.keep` (how long recorded forecasts are kept) | 7 d … 400 d | 90 d | the side file's size on disk |
| `extra.most` (k tried per group) | 0 … 10 | 6 | quotes per group |
| `extra` quotes in one standing period, every group together | at most 24 | | worker time (§2) |
| quote items | at most 200 | | as §4 |

The worker's time per standing period is then at most one forecast and 24 `extra` quotes, each within `BUDGET` 5 s,
so at most 125 s. At the 15-minute floor that is 14% of the one worker at worst. The record's growth is said with
§5 and §6.

## 2. Promise types a model may use

A promise is declared on an item kind, in the model, under `promises:`. With none declared, nothing below runs. A
promise never acts. It is a question the forecast answers for each open item or group it covers. Date, quantity and
level are read from the forecast already worked out, on every refresh, and cost no simulation. Only `extra` costs
simulations. It is worked out in standing passes and in quotes (§4) only, never for a page's refresh, within the
bounds of §1.

```yaml
messages:
  done: {order: [shipped, scrapped], lot: [packed, scrapped]}   # finished, as today (SPEC §5a)
items:
  order:
    promises:
      good: [shipped]                     # the finished states that count as kept (default: every finished one)
      date: {field: due}                  # per-item date
      level: 0.9                          # the service level each promise is made and judged at
  lot:
    promises:
      good: [packed]
      quantity: {group: parent, need: {field: need}, by: {field: due}}   # N of M by a date
      extra: {most: 6}                    # how many more to start, to cover expected loss
      level: 0.9
stocks:
  shelf:
    promises: {level: 0.95, goal: shelf-never-empty}    # make-to-stock: a stock goal's service level
```

| type | answered from the forecast | said |
|---|---|---|
| **date** (per item) | P(finish into a `good` state ≤ the item's `field`) = the share of runs that do | "on time in 94% of runs (level 90%): kept" or "at risk: 71%" |
| **quantity** (N of M by a date) | over the group's members: P(at least N reach `good` by the group's date), from `groups.by.good` per run | "10 of 12 by Fri 06:00 in 93% of runs" |
| **level** (service level) | the level α each promise is held to. A quoted date is the α-quantile of the finish. A stock's level reads `closedloop.risk`'s `p_ever_off` for the named goal: kept when 1 − p_ever_off ≥ α | "promised at the p90: Fri 11:00" |
| **extra** (start more to cover expected loss) | the least k ≤ `most` hypothetical members which, added to the group through the quote (§4), make the quantity promise's chance ≥ α | "start 2 more (12): 93%"; "no k up to 6 reaches 90%: best 84% at 2" |

- **Loss is what the record measured.** It is the share of members that reach a finished state not in `good` (scrap,
  a dropped order) or a dead letter, from the kind's path shares and attempts. No yield parameter is declared or
  fitted apart from the record.
- **`extra` is searched from k = 0 upwards**, as one quote with k extra members for each k. It stops at the first k
  that reaches α, or at `most`, which is a hard ceiling (at most 10 when the model is checked, and again at run time;
  lesson 4). The chance is not monotone in k when added members compete for the same capacity before the date, so
  the search never bisects, and it reports each k it tried. k = 0 is the forecast itself and costs no quote.
- **`extra` has a total ceiling as well as a per-group one.** One standing period runs at most 24 `extra` quotes,
  across every group together, each within `BUDGET`. The groups go earliest date first. A quote item's own `extra`
  counts against the same 24. These quotes run as worker jobs below page asks, so a page never waits behind them. A
  group not reached in its period, whether for the ceiling or because page asks kept the worker busy, is said
  **unknown** ("extra not worked out this period: 24 quotes used"), never "no k reaches", and never kept.
- **A field that is missing, not a time, or not a number** leaves that promise **unknown**, with why ("order/207:
  due is not a time"). It is never counted as kept (lesson 3). A group with no `need` is unknown in the same way.
- **The make-to-stock level** uses the stock-and-flow model's existing risk run. It is the one promise answered from
  system dynamics and not from the item simulation (§3).

## 3. What each of the three models contributes

The three views of one model each give the forecast something different. None runs a simulation of its own for it.

- **The process model** (the items' record, SPEC §5b) is the forecast's body: the paths per kind, with their rework
  loops and losses (the semi-Markov next-state shares, the fundamental matrix's expected visits), the stage times
  (Kaplan–Meier per state, run-time curves per block), and how runs end (moved on, given back, expired, dead). Rework
  and yield loss need no new part: a return to an earlier state, and a finish into a state not in `good`, are paths
  the record already carries. New from it are only the quantile ladder, `stages` and `binding` of §1.
- **System dynamics** (stocks, flows and the closed-loop projection) supplies the aggregate. It gives the
  make-to-stock service level (§2, from `closedloop.risk`). It also gives the one check that holds the two views
  together: a flow whose sensor counts items entering a state must project the `per_hour` the forecast implies (CAE
  §6, kept as CAE settles it: two projections, one check, not merged). Aggregate capacity from a projection, the
  capacity schedule, stays not filed, as CAE §9 decided. Arrivals stay at the record's rate. A flow's projected rate
  taking their place is not proposed, because the item simulation cannot yet be checked against it.
- **Control** (blocks, gates, pools) decides what starts. Gates enter as CAE §1–§3 settle: the admission limit
  worked out at now, and pools read from stocks at now. **Release** is a block that takes from a held state into the
  first worked one, so its capacity and gate bound how fast new work enters, exactly as any block's do. The extra
  members of §2 are started only by such a block, through its valve, when the model wires it. A **frozen window** is
  a term in a block's take order (§5). Control is the only view that adds new behaviour here, and that behaviour is
  one ordering term.

## 4. A quote: hypothetical items, without touching the record

A quote asks what happens if these items are added. It is the what-if path with items added to the `Inputs`, worked
out by the eta worker, cached under its own key beside the what-ifs (`KEEP` 8). It never writes an event, a lease, a
reading or a file under the model. It is asked by `ergostat quote FILE [--json]` or `GET /api/forecast?quote=…` (a
hash of the file's content, posted once to `/api/quote`, which stores it only in memory). The Timeline draws a quote's
items as dashed rows when the address carries `quote=` (no new panel).

```yaml
quote:
  - {name: a, kind: order, fields: {due: 2026-12-04T17:00, rush: false}, after: [order/118]}
  - {name: b, kind: order, after: [a]}         # its prerequisite is the quote's own a
  - {name: lot, kind: lot, count: 3, parent: batch/41}
```

- **Its items** are `ItemAt`s with ids `\0quote:NAME[#n]`. No record id can collide with them, because an id has no
  NUL. Each enters its kind's first state (or `state:`) at `at:` (default now). Its relations name record items or
  other quote items, and precedence is honoured as for any item, so its prerequisites come first. `count` is at most
  200 items in a quote (a ceiling at parse time and at run time).
- **Paired runs.** The quote and the forecast without it are run with the same seeds. The build gives each item its
  own random stream (seeded from the run and the item's id), so adding items does not reshuffle the draws of those
  already there. A change in an existing item's ladder is then the quote's effect and not noise. This changes the
  estimator's draws and not its model. It ships only if the existing backtest (`tests/eta_backtest.py`) stays within
  its run-to-run spread (§8).
- **It reports**, in `forecast/v1` with a `quote` key:
  - each quote item's own forecast (ladder, start, `waits_on`, `why`) and its place in each block's queue: the items
    it is taken after and before in the levelled run, which is the "done in the right order" answer;
  - its promise if one applies: the date at the level, and N of M with the extra of §2;
  - **its effect on the timeline**: each existing item, group and kind whose p50 or p90 moves by more than the paired
    runs' spread, by how much; each promise that falls below its level because of it ("order/215: 91% → 86%, below
    90%"); each frozen item it would go ahead of (§5);
  - its basis and run count, as any forecast.
- **A quote item of a kind with no record** (no curve) is not scheduled, with why ("no record of kind lot: cannot
  forecast"). It is never given the assumed run of an empty block in silence. When a block it needs is assumed, that
  is said in its basis.

## 5. A frozen window

**What it protects:** the *order* of the items already committed to start at a block in the near term. A frozen item
is not overtaken by work that arrives or is re-prioritised later. It does not protect run times, which no ordering
can.

**How it is declared**, on a block that takes items:

```yaml
blocks:
  welders:
    takes: {kind: order, at: [weld]}
    frozen: {for: 1d, every: 1h, urgent: {field: rush, is: true}, most: 100}
```

- Every `every`, the standing pass (§1, *Standing runs*) freezes, whether or not a page is open. It takes the items
  whose forecast start at this block falls within `for` of now, ordered by that start. The start is read from
  `stages` of the block's `takes.at` states, which a frozen window names and so keeps: the p50 of `enter`. The list
  is recorded as one event, `block.frozen` {block, items in order, until = `at` + `for`, the forecast's `at` and
  version}. `every`, `for` and `most` have the floors and ceilings of §1. `most` caps the list, and the rest are
  counted. An item stays frozen until it is first taken by that block, or it finishes, or the list's `until` passes
  without a newer list. A rework return then queues normally. The newest list for a block is the one in force,
  ordered by the event's `seq` and never by time (lesson 2).
- **An unchanged list is renewed, not lapsed.** A pass whose list for a block equals the one in force writes no new
  list, but its `standing.pass` (§1) names that list's `seq` with `until` = this pass's `at` + `for`. The list's
  `until` in force is the one named by the newest good `standing.pass` by `seq` that names it, and the list's own
  `until` when none does (a pass that wrote the list and stopped before its `standing.pass`, or `standing.pass` not
  readable). So while passes run, a steady list never lapses, however long it stays the same. When they stop, it
  lapses `for` after the last good pass, and the block takes by its plain order, said as in the next point. The
  renewal costs no event of its own: it rides on the pass's one event.
- **Every good pass renews every frozen block.** A block makes a new list only on its own due pass (every `every`),
  but each good pass of the schedule, whose period is the shortest declared (§1), renews the list in force of every
  frozen block, due or not. A block whose `every` is 4 h on a schedule of 1 h is renewed hourly.
- **`for` is at least three times `every`** (§1, *Bounds*). A shorter `for` is refused at check (`bad-frozen`) and
  raised to 3 × `every` at run time, the clamp that keeps more of the window rather than less. Then a list renewed
  at a pass's `at` reaches past the next two passes: the seconds the next pass spends queued and simulating (at most
  two `BUDGET`s, a page's run already under way and its own) leave no gap, and one missed pass does not lapse it.
  Health reports a late pass when the newest good one is more than two periods old (§1), a full period before the
  list lapses at three.
- **A lapsed list is said at once.** From the moment a list's `until` in force passes without a newer list, the
  block takes by its plain order and its why says "frozen window lapsed at 11:00 (last good standing pass 03:00):
  plain order", and health reports it beside the late pass. It is never read as a window in force, and never left
  for health's next alarm to find.
- **What it adds to the record.** A new list is written only when its order or its members differ from the one in
  force; an unchanged pass writes only its `standing.pass`. At most one list per block per pass is written, so at
  worst 96 × 200 ids a day per block. The event is about the item `ergostat.frozen/BLOCK`, so the existing roll-up
  (`rollup.py`, per item, a prefix by `seq`) replaces lists older than its horizon with one snapshot, the way it
  rolls up any item. Only the newest list is ever read. The build's `test_frozen_lists_roll_up` checks it, for the
  lists and for `ergostat.standing`'s passes.
- **The engine and the simulation read the same order.** `leases/ready.take_key` gains one leading term: urgent 0,
  frozen 1 (then its frozen rank), the rest 2, before the existing order. The dispatcher and `eta._Run` already share
  that function, so the window has the same effect in the simulation as on the floor. In the simulation that effect
  is: items not frozen, quote items and arrivals included, start at that block only after the frozen ones ahead of
  them.
- **Urgent work overrides it.** An item whose `urgent` filter matches takes term 0 and goes ahead of the frozen items.
  When the dispatcher takes an urgent item while frozen ones wait, it records `block.frozen.broken` {block, item,
  went ahead of [ids]}. The Items tab and the item's why say so. A quote with an urgent item reports whom it would push,
  and by how much.
- **When the list cannot be read**, the block takes by its plain order. This falls back on purpose, and is not
  failing closed: a missing freeze is a missing preference, not a refusal, and stopping the block would be the worse
  case for the work it protects. This is said in the block's why ("frozen window not read: plain order"). A list
  naming an item not in the record is skipped for that item and counted.

## 6. Calibration

Two calibrations, side by side.

1. **Replay** (exists). `etacheck.calibration` re-forecasts past cuts from the record before each cut and scores
   against what happened. It judges the *method* as it is now, which is what the backtest and the flags need. It
   stays as it is.
2. **Recorded** (new; on when a model declares `forecast: {record: 1h}`). It judges what was *said*, including the
   model and code as they were then. Every `record` period, the standing pass (§1) records it, whether or not a page
   is open. A forecast worked out for a page is never recorded, so the sample is the schedule's and not the moments
   someone looked. `record` lies between 1 h and 1 d (§1). A pass records two things:
   - **the ladders, in a side file**, `forecasts/YYYY-MM.jsonl.gz` under the run folder, one line a pass. Each line
     has each item's ladder (p05…p95, `beyond`) for at most 200 items, those with a promise first and then the
     earliest p50. The rest are counted, never silently dropped. Each promise's chance and its level are included,
     as is each frozen list's `seq`. The file is append-only and never edited. Month files older than
     `forecast: {keep: 90d}` (7 d … 400 d) are deleted, matched by the name pattern the module writes and never
     by a keep-list (lesson 11). Raw, that is at most 24 × 200 ladders a day, about 0.5 MB before compression, so
     at most about 200 MB raw at the 400-day ceiling.
   - **one small event**, `forecast.made` {at, model version, runs, flags, basis summary, items recorded, items
     counted out, `missed`, the side file's name and line}, at most 1 kB. It is about the item
     `ergostat.forecast/MODEL`, so roll-up treats it as any item's events. It is an event because it is what was
     said, and the remote API's `events` serves it (§7).

**How it is scored** (in `etacheck`, the same tallies as now):

- For each recorded item that has since finished, its **PIT** value is its ladder's interpolated F(actual). For
  coverage at each level u, the share with PIT ≤ u is set against u. An item still open past its p90 is a miss. One
  still open before its p90 is unresolved and counted apart, as today.
- For promises, the share **kept**, set against the level, with its count: "kept 37 of 41 (90%; level 90%)". It is
  said *below level* only when the Wilson upper bound of the kept share is under the level, and *above* only when the
  lower bound is over it. Otherwise it is "within what 41 can tell" (never said better or worse than the count
  supports).
- The Timeline's calibration line gains one clause per kind for the recorded forecasts beside today's replay clause:
  "as said: 7 in 10 orders by their p90 (n 140)".

**How results feed back:**

- **To promises, as a correction that the record supports and the model does not have to change.** When a kind has
  at least `etacheck.FEW` resolved recorded forecasts, a promise made at level α is quoted at the ladder level α′
  whose recorded coverage was α, interpolated on the PIT curve (a conformal correction). α′ is capped at p95, and
  past it the promise says "cannot promise at 90%: the forecast's p95 covered 0.84". The why says so: "promised at the
  p95, since this kind's p90 covered 0.81 over 140 orders". This is a correction to what is said, not a parameter, so
  it needs no owner's accept (NOTES: nothing estimated changes the *model* by itself). It is off unless the promise
  says `calibrate: true`.
- **To the model, only as evidence.** A kind or state whose recorded coverage is below its level by more than the
  count can explain is a check finding, **forecast-miscalibrated**, with the state whose stays the misses ran long in
  (by the PIT's residual per stage). This is a structured residual (invariant 7). It may become a proposal, for
  example a shorter record window after the process changed, which the owner accepts or dismisses.

## 7. How a remote system's forecasts are read by another model

**Exposed.** `/remote/v1/forecast?kinds=…&items=…&groups=…` serves `forecast/v1` as the remote last worked it out.
It is read only, under the existing token and its rate bucket, with at most 200 ids a call (as `process`'s `at=`). It
never starts a simulation on a request: it asks the remote's worker as a page does, and answers the last result with
its `at`, or 503 "being worked out". Promises and frozen lists (`block.frozen` events) are also served through the
existing `events`, as are the recorded passes' summaries (`forecast.made`). The ladders in the side file (§6) are
not served. A reader that wants to calibrate a remote records what it read itself. Calibration is in the
forecast's own key. A remote
quote, `/remote/v1/quote`, is served only when the remote model declares `forecast: {quotes: remote}`, at most 10
an hour per token. Off by default, since each costs a simulation there.

**Read.** A relation to a remote's kind stays never precedence for the engine (SPEC §5a: ergostat cannot see the
remote item finish, so it cannot gate on it). A new key on such a relation, `forecast: true`, makes it precedence **in
the forecast only**:

- in each run, the local item leaves its first state only after a finish drawn from the remote item's ladder. The draw
  is the inverse of the piecewise-linear CDF through p05…p95. Past p95 it uses an exponential tail whose mean is
  (p95 − p90)/ln 2, and with the remote's `beyond` share it is drawn as never;
- the remote items named in one run share one uniform draw per remote (rank-coupled). Their joint lateness is then
  not understated, as independent draws would understate it. A group is read from the remote's own group answer,
  never composed from its members here;
- the item's `waits_on` lists `{"on": "remote", "remote": NAME, "id": …}`, and its basis gives the remote forecast's
  `at`, its version and its runs.

**Failing closed.** A remote forecast that is unreachable, unanswered, older than three of the remote's `every`, from
a schema not `forecast/v1`, or that does not name the item leaves the local item **not scheduled**, with why ("waits
on incidents-incident/7, whose forecast is 14m old"). Its dependants follow, as for any unschedulable item. The read
is bounded like `remote/items.py`: one lock per remote across read, decide, ask and write, and `ASKS` per period.

## 8. The build split

The gaps of this milestone were not in this clone (no record and no GAPS.md entry names them), so the split below is
proposed whole. The coordinator can map it onto the names already filed. CAE's own build,
control-aware-completion-estimates, is **confirmed as CAE §9 amends it** and is not changed here. It does not wait
on any of these, and none waits on it.

| gap | builds | files | depends on | budget (net lines) |
|---|---|---|---|---|
| forecast-stable-result | §1: `forecast/v1`, ladder, groups, stages, `waits_on` with `binding`, basis; `ergostat forecast`, `/api/forecast`; the Timeline reads it | new `numbers/forecast.py`; `numbers/eta.py`; `web/eta_api.py`; `cli/`; SPEC §5a | (none) | 150 |
| forecast-standing-runs | §1, *Standing runs*: `numbers/standing.py` started by the runner; the worker moved to `numbers/etaworker.py` with a `standing` job taken first and no idle exit while one is declared; the schedule's clamps; `standing.pass`; health's late or failed pass, from the newest good pass; `missed` | new `numbers/standing.py`; `numbers/etaworker.py` (moved from `web/eta_api.py`); `cli/running.py`; health | forecast-stable-result | 120 |
| forecast-promises | §2: `promises:` schema and check (`promise-field-unknown`, `bad-promise`), date, quantity, level, the stock level from `closedloop.risk`; the Items tab's "at risk" in each row's why | `spec/`, `numbers/forecast.py`, `web/static/` (the row's existing why) | forecast-stable-result | 160 |
| forecast-quotes | §4: quote items, per-item random streams (guarded by the backtest), the effect report, `extra` of §2, `ergostat quote`, dashed rows by address | `numbers/eta.py`, `numbers/etamodel.py`, `numbers/forecast.py`, `web/eta_api.py`, `relations.js` | forecast-promises | 170 |
| frozen-windows | §5: `frozen:` schema and check with its bounds, the freeze in the standing pass, `block.frozen` written only when changed, its renewal through `standing.pass`, `block.frozen.broken`, the `take_key` term, every pass renewing every block, the `for` floor of 3 × `every`, the lapse said at once | `leases/ready.py`, `numbers/standing.py`, `spec/`, the dispatcher | forecast-standing-runs | 160 |
| forecast-calibration-recorded | §6: the side file and its keep, `forecast.made`, PIT and promise scoring, the second calibration clause, `calibrate: true`, `forecast-miscalibrated` | `numbers/etacheck.py`, `numbers/standing.py`, `relations.js` | forecast-promises, forecast-standing-runs | 160 |
| remote-forecasts | §7: `/remote/v1/forecast`, the opt-in remote quote, `forecast: true` relations, the draw and the fail-closed read | `web/remote_api.py`, `remote/`, `numbers/etamodel.py` | forecast-stable-result | 160 |

Acceptance tests each gap must carry (named here so the definitions can take them):

- forecast-stable-result: `test_forecast_ladder_brackets_p50_p90` (p05 ≤ … ≤ p95 and today's p50/p90 unchanged on
  `owners_record`); `test_group_finish_is_latest_member`; `test_waits_on_binding_names_the_late_prerequisite`.
- forecast-standing-runs: `test_standing_pass_runs_with_no_page_asking` (no `estimates` call, a pass made in its
  period); `test_standing_before_a_queue_of_whatifs` (nine what-if asks waiting, the due pass is taken first);
  `test_late_pass_is_said` (a pass held up past two periods is reported by health, never read as current);
  `test_late_measured_from_last_pass` (a list unchanged for 3 h while passes run every hour is not late; no good
  `standing.pass` for three periods is late, and an unreadable one is said, never fine);
  `test_periods_clamped_at_check_and_run` (`every: 1s` refused at check and clamped to 15 min at run time).
- forecast-promises: `test_date_promise_unknown_when_field_missing` (never kept); `test_stock_level_reads_risk`.
- forecast-quotes: `test_quote_writes_nothing` (event `last_seq` and the files are unchanged);
  `test_quote_prerequisite_first`; `test_quote_effect_zero_for_unrelated_kind` (paired streams);
  `test_extra_matches_binomial` (§9.2: no time pressure, 8% scrap, need 10 at level 0.9 → 12 started, within the runs'
  spread); `test_backtest_unchanged_by_item_streams`; `test_extra_quotes_capped_per_period` (30 groups asking: 24
  quotes run, the groups left said unknown, none kept).
- frozen-windows: `test_frozen_order_holds_against_a_later_arrival` (engine and simulation both);
  `test_urgent_breaks_and_is_recorded`; `test_unreadable_freeze_takes_plain_order`; `test_newest_list_by_seq`;
  `test_unchanged_list_writes_no_new_list` (only its `standing.pass`);
  `test_unchanged_list_stays_in_force_past_for` (`for: 3h`, `every: 1h`, five unchanged passes: one `block.frozen`,
  the list still in force at 5 h, and lapsed to the plain order 3 h after the passes stop);
  `test_one_missed_pass_does_not_lapse` (`for: 3h`, `every: 1h`, the pass at 1 h missed and the one at 2 h run late
  by two `BUDGET`s: the list is in force throughout, and health is quiet until the newest good pass is two periods
  old); `test_lapse_said_at_once` (passes stop: health reports the late pass at 2 h, and from the moment of the lapse
  at 3 h the block's why says "frozen window lapsed" and health reports it, with no moment between where the list
  is neither in force nor said); `test_block_renewed_by_every_pass` (a block with `every: 4h` on a schedule of 1 h,
  set by `forecast: {record: 1h}`, is renewed by each hourly pass); `test_for_below_three_every_refused`
  (`for: 2h`, `every: 1h` refused at check with `bad-frozen` and raised to 3 h at run time);
  `test_failed_pass_renews_nothing`; `test_frozen_lists_roll_up`.
- forecast-calibration-recorded: `test_pit_coverage_on_a_calibrated_record` (coverage at 0.9 in [0.8, 1.0]);
  `test_below_level_only_past_wilson`; `test_calibrated_promise_moves_to_the_covering_level`;
  `test_page_forecast_never_recorded`; `test_side_file_kept_to_keep` (only month files past `keep`, by the
  module's own name pattern, are deleted).
- remote-forecasts: `test_remote_forecast_stale_is_not_scheduled`; `test_remote_draw_matches_ladder`;
  `test_remote_quote_off_by_default`.

Seven gaps, about 1,080 net lines of code in total, plus tests. Order: the stable result first. Then standing runs
and promises in parallel. Then frozen windows (after standing runs), quotes (after promises) and recorded
calibration (after both). Remote forecasts may follow the first gap at any time.

**Not filed:** a batch block that loads several items into one run (an oven), so that they start and end together.
Today such a block is drawn as that many lanes whose runs start apart. The Timeline's "not modelled" sentence says
so. Also not filed: yield inside an item (a lot of 50 that comes out 46), which is the first owner's question. And,
as CAE decided, nothing projected over the horizon for gates and capacity.

## 9. Worked examples

### 9.1 A job shop with rework

Orders go `booked → cut → weld → inspect → shipped`. Inspection sends 25% back to `weld`, and 2% end `scrapped`. Three
welders (`pool: 3`). From the record: a weld run's median is 3 h, over 311 runs. The expected visits to weld are
1/(1 − 0.25) ≈ 1.33 (the fundamental matrix). Orders are grouped under contracts (`parent: contract`).

- **Forecast** for order/207, at Tue 09:00: `finish` p50 Thu 14:00, p90 Fri 11:00 (200 runs). `waits_on`: welders,
  9 ahead; order/201 (`binding` 0.62, its prerequisite). `basis`: weld from its own 311 runs, inspect from 290 stays,
  visits weld 1.33. Contract/12's group finish: p90 Mon 16:00.
- **Promise** `date: {field: due}`, `level: 0.9`, due Fri 17:00: on time in 94% of runs, so kept.
- **Quote**: a new contract of three orders a → b → c, c due next Thu, not rush. Reported: c's p50 next Wed 10:00,
  p90 Thu 08:00, so promised at the p90 for Thu 08:00, before its due. Each order is taken after order/219 and before
  any later arrival. Effect: order/215's on-time chance falls from 91% to 86%, below its level, which is said; four
  orders' p90 move by about 3 h; nothing else moves beyond the runs' spread.
- **Frozen window** `frozen: {for: 1d, urgent: {field: rush, is: true}}` at the welders: at 09:00 the orders whose p50
  start at weld falls before Wed 09:00 are frozen (7 of them). The same quote with `rush: true` on a reports that a
  goes ahead of order/209 and order/210, pushing each by about 3 h. Taken for real, `block.frozen.broken` records it.
- **Calibration**: with `record: 1h`, after four weeks 140 orders are resolved, and their p90 covered 0.81, below 0.9
  past the Wilson bound. Promises with `calibrate: true` are now quoted at the ladder level that covered 0.9 (about
  the p95), saying why. The finding forecast-miscalibrated names `weld`, whose stays ran long: the welds of a new
  material, which the owner may answer with a shorter record window.

### 9.2 A batch process with yield loss

Lots go `mixed → baked → inspected → packed`, and inspection scraps 8% of lots (23 of 287 on record) into `scrapped`.
An order (`parent: batch`) needs `need: 10` good lots by `due`. The oven block has four lanes and a 2 h median bake.

**Starting extra.** When time does not bind, the chance that at least 10 of M lots pass, each passing with
p = 0.92, is binomial. Worked by hand:

| lots started M | P(at least 10 good) |
|---|---|
| 10 | 0.434 |
| 11 | 0.782 |
| 12 | **0.935** |
| 13 | 0.984 |

Starting for the *expected* loss, 10 / 0.92 ≈ 10.9, so 11 lots, keeps the promise only 78% of the time. At level 0.9
the promise's `extra` answers **start 2 more (12): 93%**, and at 0.95 it answers 3 more. With a due date well after
the 12 lots' p90 (say Fri 06:00 against a p90 of Thu 20:00), the simulation must reproduce this table within its runs'
spread. That is `test_extra_matches_binomial`.

**When time binds.** With due Thu 18:00, the 13th lot would start behind the other twelve in the oven's queue, so it
adds chance only if it finishes in time. The search tries every k up to `most` and reports each: "k=0 41%, k=1 70%,
k=2 84%, k=3 83%, k=4 80%, k=5 77%, k=6 74%: no k up to 6 reaches 90%: best 84% at 2". Each is at most the
binomial's chance for the same count (43%, 78%, 93%, 98%, …), which time can only lower. The added lot competes for
the same four lanes, which is why the chance is not monotone. The answer here is a promise that cannot be kept,
said before work starts, and not more lots.

**Frozen window**: `frozen: {for: 8h}` on the oven keeps the next eight hours' loading order. A rush order's lots go
ahead only with `urgent`, and are recorded when they do. When the loading order stays the same over a quiet night,
one `block.frozen` is written at 18:00, and each hourly `standing.pass` renews it to its `at` + 8 h, so at 03:00 it
is still in force (until 11:00), and health is quiet. If the 04:00 pass is missed, the list is still in force and
renewed by the 05:00 pass. If the runner stops at 03:00, health reports the late pass from 05:00, and the list lapses
at 11:00, when the oven's why says so and the oven takes by its plain order. **Make-to-stock**, on the same model:
the `shelf` stock's
goal `shelf-never-empty` at level 0.95 reads `closedloop.risk`. It is kept when the share of closed-loop runs where
the shelf is ever empty over the horizon is at most 5%.

**Read as a remote.** A shop that sells the lots reads this model as remote `bakery`. Its kind `delivery` has
`waits_for: {kind: bakery-lot, forecast: true}`. Each delivery's forecast then draws its lot's finish from the
bakery's ladder, and a delivery says "not scheduled: waits on bakery-lot/88, whose forecast is 14m old" when the
bakery stops answering. In the model that is
`items: {delivery: {relations: {waits_for: {kind: bakery-lot, forecast: true}}}}`: `bakery-lot` is the remote's kind
`lot` by its local name (SPEC §5a, *A remote's kind*), and it stays never precedence for the engine.

## The ergostat-on-ergostat factory, as one user

The factory is a job shop with rework (implement, review, revise and back). Its choices belong in its own model
(`dev/model/`): which kind carries a `date` promise, whether review has a frozen window, whether it records its
forecasts. This proposal adds none of them. Nothing in the core names its kinds or states. The owner's wish, to add
work and see its order, prerequisites and effect on the timeline, is `ergostat quote` on that model, with no
declaration needed beyond the relations it already has.

## Decisions taken alone (each the more reversible)

- The frozen list is made by the standing pass every `every` and recorded as an event. A list made by hand is not
  proposed. Recorded events can be read back and replaced by a newer list, while a list never recorded could not be
  judged.
- Standing runs share the one eta worker, taken first, rather than getting a thread of their own. This keeps one
  simulation at a time on the machine (lesson 4), and giving them a thread later is a small change.
- The ceilings (§1, *Bounds*) are set low. Raising one later loosens a check without breaking a model that passed it.
- The recorded ladders go to a side file with a keep, and the event carries only a summary. Moving them into events
  later stays possible, while ladders written into the append-only record could not be taken back out.
- An unreadable freeze takes the plain order (§5): a lost preference, never a stopped block.
- An unchanged list is renewed by the pass's own `standing.pass` event rather than by a renewal event or by
  rewriting the list (§5). One small event a pass keeps lateness and renewal in one place, and dropping it later
  for a renewal written only near `until` stays possible.
- `frozen.for` has a floor of 3 × `every`, rather than tying health's alarm to each block's `for`. A floor can be
  lowered later without breaking a model that passed it, and one alarm for the schedule stays one rule. A `for`
  below the floor is raised at run time, keeping more of the window rather than less.
- The conformal correction is off unless a promise says `calibrate: true`.
- Remote quotes are off unless the remote declares them.
- Per-item random streams ship only if the existing backtest is unchanged within its spread.

## Questions for the owner

1. **Should a lot's loss be whole-lot only (a lot passes or is scrapped), or should a lot's good count inside it be
   drawn from the record too?**
2. **Should a block's frozen window be refreshed by the forecast every hour, or frozen only when a person asks?**

Until they are answered, loss is whole-item only, and the window refreshes hourly where a model declares one.
