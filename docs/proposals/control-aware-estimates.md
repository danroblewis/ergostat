# Completion estimates that know the control model (proposal)

Owner item 17 (feeds item 18's Gantt panel), milestone timeline-real-schedule. Definition:
`dev/records/control-aware-estimates-proposal.md`. Written 2026-11-24.

The owner asked: *"We have a system dynamics model and a control model; a small simulation should give a real
estimate of what finishes when and in what order."* The completion estimates (`ergostat/numbers/eta.py`) simulate the
open items against each block's capacity, read once at the moment estimated. Since eta-refused-takes-are-a-closed-gate,
that capacity is also capped by the block's **measured concurrency**: the p90 of its runs going at once while items
waited, over the record's last day. The estimates still do not know the gates that start the blocks. On the factory
that is `implement-when` (dev/model/building.yaml):

    max(ready, fixes) * min(open, 1) * (1 - over) * (busy < min(pool, busy + room)) * (1 - full) * (1 - held)

This proposal settles how that gate, and the stocks it reads, enter the estimates. The short answer:

**Recommendation: do not couple the gates into the simulation, at each event or at a fixed step.** On the one record
with a gate, coupling gives exactly what the measured-concurrency model gives (p50 MAE 409 min, p90 coverage 0.93)
and costs about 1 s more per run with the gate's expression alone, or 14 s more per run with the engine's full pass.
The inputs that would make coupling differ from the measured model are not item counts. They are the machine's
headroom, `machine-full`, the AI budget and the provider's hold, and the simulation does not know them over the
horizon. Coupled, they would have to be held where they read now, which measured concurrency already handles better
when the gate flaps, or projected, and the model has no equation for them. Instead the build works the gate out
**once, at the moment estimated**: how many runs it admits at once *now*. It costs about 14 ms, and it settles the
owner's question below.

## What was measured

Both tables come from one command, which runs only when named (the unit suite never runs it):

    uv run python scripts/named_tests.py tests/test_control_spike.py

It writes `/tmp/control-spike-cost.json` and `/tmp/control-spike-backtest.json` and also prints both in pytest's
warnings summary. The tables below were taken with 5,000 passes, `simulate(runs=200, budget=120)` and three backtest
seeds, which took 220 s; the file now runs with 500 passes, `runs=20, budget=2`, one seed and `_score` at
`runs=20, budget=2` (about 58 s, most of it building the factory-size record), so that a gate naming it stays within
its limits. To take the tables again, set the values noted beside each in the file. `Shadow` has no `per` (the goals
held per item, SPEC §8, which the factory's model now has), so the spike sets it empty, as the engine's is before
its first pass.

**Not run on a copy of the factory record.** No copy is in the implementor's container, and the live record cannot
be shipped. The gate's cost was measured on the factory's **own model** (`ergostat.yaml` at the root, with
dev/model). The events per run were counted on the factory-size record of perf-factory-size-fixture
(`scripts/factory_fixture.py`, seed 1), which is the CI stand-in. Taking both tables on a copy is the build's first
step (§8).

### The cost of the gates per event

`closedloop.Shadow.step` is one pass of the engine's goals and built-in blocks: 65 goals and 25 built-ins on the
factory's model. Each sample first moves the counts the gates read (`gaps-building`, `gaps-ready`), as one simulated
event would, and then makes the pass. "The two gates alone" means `implement-when` and `review-when`, each
evaluated as its compiled expression on its inputs. All figures are means over 5,000 passes.

| what | measured |
|---|---|
| one Shadow pass (every goal and built-in) | **378 µs** |
| the two take gates alone (`implement-when`, `review-when`) | **26 µs** |
| factory-size record: open items, blocks taking items | 795, 23 (all 8 kinds) |
| events one run of the estimates makes there (pushes on the run's heap) | **37,019** |
| today's model there: 200 runs asked, 120 s allowed | 147 runs in 121 s (0.82 s a run) |
| added per run if a Shadow pass is made at every event | 14.0 s (×17 a run) |
| added per run if only the two gates are evaluated at every event | 0.97 s (×2.2 a run) |
| added once per estimate: the gate worked out at now (§1; at most capacity + 1 passes a gate) | ≈ 14 ms (37 × 378 µs; not timed apart) |

The factory has 414 open items, not 795, so its events per run are probably about half the fixture's (not
measured). That changes no conclusion. At 378 µs, a pass at every event costs more than the whole simulation does
today. At 26 µs, the gates alone roughly double it.

A finding outside this gap: on the factory-size record, today's model alone makes about 6 runs within `eta.BUDGET`
(5 s), which is fewer than `FEW` (20), so no p90 is said. That belongs to a gap of its own and is reported, not fixed
here.

### The backtest: three ways to run a gate, against today's models

The record is the gated synthetic one (tests/eta_synthetic.py `gated_record`): a pool of 20 under a control loop that
admits 4 runs at once, refusals put off 300 s, runs of about 3 h, and a batch of 40 tickets. There are 3 truths
(seeds), each cut 15 min, 2 h and 4 h after the batch, with 60 runs per estimate. The table shows the means over those
9 estimates. *Next 24 h* is the number of tickets with a p50 within 24 h of the cut, set against the number that
really finished in that time (the "gaps merged in the next 24 h" of §8).

| model | p50 MAE (min) | p90 coverage | next 24 h: predicted / actual |
|---|---|---|---|
| pool only (before eta-refused-takes-are-a-closed-gate) | 844 | 0.45 | 39.2 / 23.2 |
| **measured concurrency (main)** | **409** | **0.93** | 32.9 / 23.2 |
| two-way coupling: the gate `busy < 4` worked out on the run's own count, at every take | 409 | 0.93 | 32.9 / 23.2 |
| stationary availability: each take admitted with the record's admitted share | 820 | 0.50 | 39.2 / 23.2 |

- **Two-way coupling equals measured concurrency, estimate for estimate.** All 9 rows are identical and draw the same
  random numbers. Its gate reads only an item count, and the cap it reaches (4) is the cap the record measured (4).
  On a gate like this, measured concurrency *is* the coupled answer, and it costs nothing per event. The coupled run
  was given the true gate, as a declared model would give it, so this is coupling at its best.
- **Stationary availability is no better than the pool.** It admits each take with the share the record admitted
  (about 0.3), and refused takes come back every 300 s. Within half an hour all 20 lanes fill, because the gate
  depends on the count and not on chance.
- **A capacity schedule from a closed-loop projection** was not measured. The gated record's model has no stocks or
  goals to project, and the factory's gate inputs that move (headroom, `machine-full`) have no equation (§2). It
  stays a candidate for the factory copy only (§9).
- Every model overpredicts the next 24 h, measured concurrency by 42%. That error is in the run and review curves,
  not in the gate. Coupling does not change it.
- The pool and measured rows agree with docs/roadmap/overnight/eta.md (847 → 409 min, 0.44 → 0.93). The spike scores
  with its own copy of `etacheck.score`'s rule, which accounts for 844 against 847.

**Definition item 3:** coupling did not improve coverage or MAE over the measured-concurrency model, so this proposal
recommends not coupling. There are three reasons. It is identical where the gate reads item counts. It is unknowable
where the gate reads the machine, since no model of the headroom exists to run it ahead. And it costs at least twice
the simulation.

## The nine settled

### 1. Which control parts run inside the item simulation

**None, at each event or at a fixed step.** One part is worked out at the moment estimated: each take gate of a
block that takes items. A take gate is an `expr` (or other built-in) block that commands the block through `in:`. For
each such block, `etamodel.read` (already inside the estimates' thread) evaluates the gate through `closedloop.Shadow`
on the record's newest readings (`gated_off`'s signals, from `start_of`). The inputs that are counts of the
simulated items come from the `Inputs`' own counts at that moment:

- the stock that counts the block's runs (`busy`: `gaps-building`, whose sensor is `items: gap, state: building`) is
  stepped from 0 up to the block's capacity. The **admission limit now**, L, is the first count n at which the gate
  reads closed. At each n the machine's headroom moves with the sessions (§2): `room = room_now + busy_now − n`.
  The Shadow then works out what reads it (`sessions-fit`, which holds at `>= 1`, and `machine-full`) on that value,
  so each step is a whole pass and not just the expression. Each n gets a fresh Shadow from `start_of`, so no goal's
  status carries from one n to the next;
- a goal over an item count that only says items wait (`ready-gaps-taken.off`, `fixes-taken.off`) reads as true. The
  block takes only while its queue has items, so the queue already says this, and the goal is not run in the
  simulation.

The block's lanes are then `min(capacity, L)`. That is the whole coupling: one-way, at now, at most capacity + 1
passes a gate.

If later evidence shows that the gate's limit moving over the horizon matters, the next method to try is a capacity
schedule from a closed-loop projection, stepped hourly (§9). Per-event evaluation is not.

### 2. How every other input is had

The rule: **an input that counts the simulated items comes from the simulation's state. The machine's headroom is
driven by the items, one session for each run of the gate's block. Every other input is kept at its newest
reading**, which is the default the definition sets until the owner answers. A reading that is stale or was never
read counts as its goal's `on-stale` says. On the factory that is `off` for the AI budget and the provider's hold, so
the gate is closed (lesson 3: the worst case, never "fine"). Nothing is projected in this build.

Why the headroom is driven, and not held: the gate's own words are `busy < min(pool, busy + room)`. With `room` held
at 0, that is closed for every count, so a held headroom would give no new start even after the running session
ends. What binds the factory's concurrency as it reads now is the machine's **fit**, `busy + room` (the sessions it
holds now: 1). Keeping the fit, and moving the headroom by one per session, is how "kept as it reads now" applies to
a count of sessions. This is a decision taken alone, because nobody could be asked. It is the reversible choice: the
rule sits in one place in the build, and the owner's answer can replace it. The sessions of other blocks (the
reviewer) stay at their count now. The definition asks for this as "headroom per running session". The other
driven input it names, AI spend per run, is not built.

| `implement-when` input | how it is had | said in the item's why as |
|---|---|---|
| `ready`, `fixes` (goals over item counts) | the queue: true while items wait | (nothing: the queue says it) |
| `busy` (`stock.gaps-building`) | the simulation's count, stepped to find L | "admits L at once now" |
| `pool` (`stock.implementor-pool`) | newest reading (§3) | "its pool now, 36, from stock.implementor-pool" (as today) |
| `room` (`auxiliary.session-headroom`) | driven: `room_now + busy_now − n` (the fit kept) | "the machine fits 1 session now (1 running, headroom 0)" |
| `full` (`block.machine-full`) | worked out by the Shadow at each n from its goals: `sessions-fit` on the driven headroom, the resource goals as they read now | "machine-full 1 now" (when a resource goal closes it) |
| `open` (`auxiliary.intake-open`, a manual switch) | newest reading; never read counts as 0 (as `gated_off`) | "intake-open 0" |
| `over` (`goal.ai-budget.off`) | its status now | "ai-budget off now" |
| `held` (`goal.ai-not-held.off`) | its status now | "ai-not-held off now" |

Considered and **not built**:

- *AI spend driven by the items.* Each simulated run would spend its block's median recorded cost against
  `ai-spend`. No record measures that per run yet, and the budget's daily reset is a clock the simulation does not
  keep.
- *Headroom driven within the run*, as runs end over the horizon (two-way). Here it moves only in the search for L
  at now; the backtest shows two-way coupling adds nothing (above).
- *Projected* (`simulate.project` / `closedloop.closed`). `session-headroom` and the resource utilisations behind it
  have sensors only and no equation, so a projection would hold them anyway (`inputs: hold`).

The factory's figures make the cost of the default plain. Now it reads `busy = 1` and `room = 0`, so the fit is 1
and `machine-full = 1`. The search finds the gate open at n = 0 (room 1, `sessions-fit` holding) and closed at n = 1,
so L = 1, and the 97 ready gaps are drawn 1 at a time. If nothing were running and the headroom were 0 (fit 0), or a
resource goal (CPU, memory, threads, disk) were off now, L = 0. The implementor is then off now, and every gap
waiting on it is **not scheduled**, with the why "waits for implementor, whose gate implement-when is closed now
(machine-full 1: memory-within off, as it reads now)". This is the same path `gated_off` takes today for a switch
at 0.

The estimates are worked out again on every refresh, at most every 30 s, so a gate that flaps makes the estimates
flap. Measured concurrency (the last day's 6 at once) is the *projected* answer. It is steady but blind to the machine
now. Choosing between them is the owner's question below.

A gap waiting on a parked gap stays not scheduled, as main does today (eta-works-out-on-the-factory-record).

### 3. Pools read from stocks that change (`pool: {now: stock.X}`)

**Kept at the newest reading at the moment estimated**, as `poolnow.read_at` does today, under the block's `most:`
ceiling (lesson 4: a pool never above `most`, and 1 at least, with the reason said). Nothing in the model projects
`implementor-pool`. It is set by the pool controller (`dev/bin/pools.py`) through a file, and the model has no
equation for it. The pool is read again on each refresh, so a change reaches the estimates within 30 s. The why keeps
today's words ("its pool now, from stock.implementor-pool").

### 4. Time coupling, the cost bound, and where it runs

**One-way, at the moment estimated.** The gate is worked out once per estimate, and the simulation never writes back
into the stocks. At the factory's size (414 open items, 10 blocks taking items, 200 runs), the added cost is at most
(capacity + 1) Shadow passes for each gated block. That is 37 × 378 µs ≈ 14 ms for the implementor at a pool of 36,
and about 25 ms with the reviewer. It is bounded by the blocks' `most:` (9 and 6 in the repository's model; at most 36
with the live pool), never by a number read at run time.

Per-event coupling would add 0.97–14 s **per run** (the table above). It is not built.

It runs where the estimates run now: the one eta thread (`ergostat/web/eta_api.py` `_worker`), never on a page's
request. A request gets the last answer, and the thread works out the next.

### 5. The closed-loop risk's uncertain parameters in the Monte Carlo

**No.** The closed-loop risk (`closedloop.risk`) draws the stock-and-flow model's uncertain parameters
(`sensitivity.uncertain`: `build-time`, `take-time`, `fix-share` ...) and the identified block models' numbers. The
item simulation does not use those numbers. Its spread comes from the record's own run-time curves, failure shares
and paths, so drawing the risk's parameters as well would add spread that does not belong to the items and would
count run time twice. If a capacity schedule from a closed-loop projection is ever adopted (§9), each of its Monte
Carlo runs would take the schedule of one risk run. That is the only way those parameters would enter.

### 6. One model: the goals' forecast and the items' estimates

**Two projections, held to one check. Not merged now.** The goals' forecast (R6, goal-forecast-proposal) projects
stocks and flows with the loops running (`closedloop`). The items' estimates simulate items. They agree when a flow
whose sensor counts items entering a state (`gaps-built`: `entering: built`) projects the rate the levelled run
implies. The levelled run's entries into that state per hour over the first 24 h is the number the backtest's
"next 24 h" already counts.

The build exposes that count in the estimates' answer (`flows: {flow: per hour}`, no new panel). goal-forecast-proposal
is not on main, so whether R6's forecast then takes its item-counting flows from the estimates is settled there, not
here. Merging the two into one run would put the 0.97–14 s per run of §4 into every Dynamics forecast.

### 7. What the Timeline and Lanes show

There is no new page or panel. Everything is said through the Timeline, the Lanes and the item's why.

- **Starts staggered by the gate.** The lanes are `min(capacity, L)`, so the levelled run already staggers the
  starts: 1 lane now on the factory, with the rest following as each run ends.
- **A gate's closed span.** With the gate kept as it reads now, a closed gate is closed for the whole horizon. The
  Lanes draw the block's lane row as one closed band from now, labelled with the gate and the inputs that close it
  ("implement-when closed now: machine-full 1"). The items waiting on it are not scheduled, with the why above. No
  span is drawn ending at a moment the model cannot know.
- **The why names the gate**: "1 of 1 busy in implementor (its gate implement-when admits 1 at once now: the machine
  fits 1 session, 1 running and headroom 0, under its pool now of 36); 96 ahead of it".
- **The Timeline's "Not modelled"** sentence (relations.js, twice) becomes: "A block's gate is worked out at now and
  kept as it reads now; not modelled: the machine's headroom and the AI budget changing over the horizon."

### 8. The validation bar

The build adds `Flags.control` (default off until its bar passes) and the ablation `"+ gate now"` to
`eta.ABLATIONS`, run by `tests/eta_backtest.py`'s `backtest`. It is kept on only if all of the following hold.

1. **Gated synthetic record (CI).** Its model gains the expr gate `busy < 4` reading a stock of the `doing` count.
   The "+ gate now" row must equal the measured-concurrency row within run-to-run spread: p50 MAE within 5% of 409
   min, p90 coverage within 0.05 of 0.93. This table shows they are identical when coupled.
2. **The four existing records.** These have no gate, so their inputs are identical, pinned as
   `test_backtest_gated_record_improves` pins them today.
3. **A copy of the factory record, at the 7 cuts of `etacheck.cuts` over its last week.** Against the
   measured-concurrency model (and the pool-only model, for reference), "+ gate now" must have:
   - p50 MAE no worse than measured concurrency's;
   - p90 coverage at least 0.8, and no more than 0.05 below measured concurrency's;
   - a next-24-h merged-gap count (p50 within 24 h, against gaps that reached `approved` in that time) whose error
     is no larger than measured concurrency's.

   If it fails, `Flags.control` ships off, and the why says the gate's limit now beside the measured one.
4. **The command.** The table is reproduced by
   `uv run python scripts/named_tests.py tests/test_eta.py::test_backtest_gate_now` for (1) and (2). For (3), the
   coordinator runs the same `backtest` by hand on a copy of the factory record (copied whole on the host, never
   committed), with the factory-size fixture as its stand-in in CI. The fixture gains the factory's gate shape:
   an expr gate on `gap-building` reading the `building` count, the block's pool stock and a manual `full`
   switch planted at 1 for two hours. CI then covers the closed-now path without the owner's work.

**Prediction, not measured:** on the factory copy, "+ gate now" will lose to measured concurrency at cuts where
`machine-full` read 1 and then cleared within hours. A full machine at the cut then draws everything at 1 lane, or not
at all. This is why the owner is asked.

### 9. The build split

**Amend control-aware-completion-estimates** from "run the blocks' gates and the stocks they read" to **"the gate's
admission limit at now"** (§1–3, §7–8):

| part | files | budget (net lines) |
|---|---|---|
| L at now through Shadow, the lanes `min(capacity, L)`, the gate's words in the why | ergostat/numbers/etamodel.py, eta.py | 70 |
| `Flags.control`, the "+ gate now" ablation, the `flows` count of §6 | ergostat/numbers/eta.py | 20 |
| the Timeline's and Lanes' sentences, the closed band | ergostat/web/static/relations.js | 15 |
| the fixture's gate shape | scripts/factory_fixture.py | 20 |
| the gated record's expr gate; test_backtest_gate_now; a closed-now test; a why test | tests/ | 150 (tests) |
| SPEC §5a | docs/SPEC.md | (docs) |

That is 125 net lines of code, plus tests. It depends on a copy of the factory record being backtested by the
coordinator (§8.3).

**Not filed:** two-way coupling, which is identical and expensive. Also not filed is a capacity schedule from a
closed-loop projection (about 250 lines: a headroom model per running session, the schedule stepped hourly). File it
only if the owner answers "project" **and** the factory copy shows measured concurrency missing because the gate's
limit moves within the horizon. The definition's own figures (`gaps-building` 6.1 on average over the day, 1 now)
are the two answers the owner chooses between: the measured 6 is the projection, and the gate's L = 1 is "as it
reads now".

## The owner's question

**Should the estimates take the factory's concurrency as its gate reads now (the sessions the machine fits now: 1
gap at a time today, none while a resource goal is off), or as the record measured it over the last day (6 at
once)?**

Until it is answered, the build ships "as it reads now" if its bar (§8.3) passes, and otherwise keeps the measured
concurrency and says the gate's limit now in the why. Either way, a gap waiting on a parked gap is not scheduled.
