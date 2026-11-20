# eta: each item's time to completion, estimated from the model

Branch `eta`, from main at 214d864. Gap (`docs/GAPS.md`, *Relations, what is left*: "the projection does not level
resources (a block's `pool`)"). The owner's report: on ticket-factory with 100+ tickets the Timeline said 100 tickets
would finish by 17:43, which is impossible with 6 leases at once. The projection (`precedence.py`) runs each item's
median times after what it waits on, as if every item had a server of its own.

## Definition of done

Each open item's finish is estimated by a **Monte Carlo over all the open items together** (`numbers/eta.py`), from
everything the record measures, in a thread, never on a page's request, cached until the record changes (at most
every few seconds), with a fixed seed, bounded runs (200) and a time budget:

1. **Path** (a semi-Markov model per kind): each state's next-state probabilities from the record's moves (a lease's
   hold folded into the state it was taken from, rework loops kept); the expected visits per state from the
   absorbing chain's fundamental matrix N = (I − Q)⁻¹, reported per kind.
2. **Survival:** each state's time-in-state by **Kaplan–Meier**, items still in it censored; an item's residual life
   given its age in its state, S(a + t) / S(a); a state with too few observations falls back to its kind's pooled
   stays, then to every kind's.
3. **Queues at the valves:** a state a block takes from is waiting plus service: the item queues at the block in its
   `takes:` order (the states of `at` in order, oldest first; `unblocked: true`: the least slack first), at most its
   capacity at once (its `pool`, its agent's `at-once`, its daemon's `concurrency`: whichever binds; agent seats and
   daemons shared between blocks), each run a recorded attempt; the servers also capped by the **measured outflow**
   while it had a backlog (Little's law: busy servers = throughput × run time). Dependencies: an item does not leave
   its kind's first state, nor is it taken by an `unblocked` block, until what it waits on is done.
4. **Leases:** a leased item's remaining run is the run-time distribution given the time its lease has been held; a
   failed or expired attempt (the record's share, nack's `after` kept) returns it to the queue, its attempts counted,
   a dead letter after the most allowed.
5. **Arrivals** at the record's rate (optional), competing for the same capacity.

Output per item: p50 and p90 finish, its expected start, what it waits in now (block or queue, or state), its
position, and why in words ("6 of 6 busy in review; 38 ahead of it; a run takes 9 min (median)"); per kind, when the
last open item finishes (p50, p90). **A backtest with ablations decides what stays**: replay past moments, predict,
compare with what happened (MAE of the p50, p90 coverage), for path only, + survival, + queues, + measured rates,
+ leases; a component that does not help is dropped, and the table is in this file.

UI, in the existing views only: the Items list gains an estimate column (p50, the p90 beside it in the cell's title);
the Timeline's projected bars come from a levelled run (never more than a block's capacity at once), with a p90
whisker, and a *Lanes* choice draws each block's lanes (at most its capacity) with the items' runs in them; the frontier and the
critical path stay; the item page says its ETA, what it waits on and why; the what-if field (`block.NAME.pool`, and
a new `block.NAME.failure`) changes the estimates.

## Acceptance tests

- `tests/test_eta.py::test_kaplan_meier_with_censoring` (a textbook table; censored items lower nothing at their time)
- `tests/test_eta.py::test_residual_life_is_conditioned_on_age`
- `tests/test_eta.py::test_fundamental_matrix_counts_rework_visits`
- `tests/test_eta.py::test_capacity_is_never_exceeded`
- `tests/test_eta.py::test_dependencies_are_respected`
- `tests/test_eta.py::test_rework_adds_time`
- `tests/test_eta.py::test_mmc_wait_matches_erlang_c`
- `tests/test_eta.py::test_the_same_seed_gives_the_same_estimates`
- `tests/test_eta.py::test_the_owners_case_100_tickets_6_leases`
- `tests/test_eta.py::test_a_leased_item_is_conditioned_on_its_lease_age`
- `tests/test_eta.py::test_whatif_pool_and_failure_change_the_estimates`
- `tests/test_eta.py::test_backtest_p90_coverage_on_a_synthetic_record`
- `tests/test_items_page.py::test_the_timeline_levels_lanes_per_block` (Playwright)
- the four suites, rc 0, no page test skipped; `demo_check` on ticket-factory, roadmap and coordinator.

## Size budget

800 net non-test lines (outside `tests/` and `docs/`), raised from 600 by the coordinator when the owner refined the
brief (survival analysis, a semi-Markov path, measured rates and the ablation backtest on top of the queueing
simulation).

## Where it stopped

Built as defined, with one component dropped by the backtest, and over the budget (below).

**The backtest with ablations** (`tests/eta_backtest.py`: at past moments, each open item's finish estimated from the
record before it alone, against when it finished; MAE of the p50 in minutes, bias = p50 − actual, coverage = the
share finished by their p90). Each row adds a component to the one above; the last takes arrivals out of the full set.

| components | owner's case: items, MAE, bias, p90 | steady, overloaded (6/h, pool 3) | steady, ρ ≈ 0.7 (3/h) | ticket-factory record (47 tickets) |
|---|---|---|---|---|
| path (semi-Markov, ended stays drawn whole) | 256, 173, −169, **0.36** | 298, 317, −28, 0.74 | 109, 209, −10, 0.91 | 33, 1.0, +0.1, 0.88 |
| + survival (Kaplan–Meier, residual given age) | 256, 152, −128, 0.59 | 280, 285, −161, 0.85 | 109, 213, −64, 0.97 | 33, 1.6, +1.4, 1.00 |
| + queues (capacity, recorded runs that succeeded) | 256, 62, −46, 0.81 | 278, 214, −129, 0.91 | 109, 214, −170, 0.81 | 33, 5.9, +5.7, 0.91 |
| + leases (lease age, failed and expired runs) | 256, 65, −50, **0.84** | 259, 242, −85, 0.99 | 109, 211, −85, 0.90 | 33, 1.1, +1.1, 1.00 |
| all but arrivals | 256, 64, −51, 0.80 | 300, 221, −114, 0.75 | 109, 212, −112, 0.74 | 33, 11.0, +11.0, 1.00 |

The owner's case is a synthetic record (`tests/eta_synthetic.py`, a truth simulated apart): a day at 2 tickets an
hour, then 100 brought in at once, a dev pool of 6, runs lognormal (median 20 min), 10% failing, 10% sent back by
review; cuts 15 min, 2 h and 4 h after the batch. The steady records are 48 h at 6 and 3 an hour, a pool of 3, 15%
failing, 30% sent back; cuts at 8, 16, 24 and 32 h. The ticket-factory record is the offline demo's (47 tickets over
15 minutes, its fakes; cuts at 20 to 65% of it).

**What stays:** queues (they halve the error and lift the p90's coverage from a third to 0.81 where capacity binds,
the owner's case), leases (rework: coverage back to about 0.9 everywhere, the ticket-factory record's error back to
the path's), survival (better where items wait long, the owner's and the overloaded case; even elsewhere), and
arrivals (coverage falls without them in two of four). **Dropped:** a cap on a block's servers from its throughput
measured while it had a backlog (Little's law): it changed no estimate in any of the four (its rows were identical to
the queues'), so its code went. The coordinator's record could not be backtested: its `work` items go round
(`ready → reported → accepted → ready`) and finish only as dead letters (1 of 192 open items finished after the cut).

**The owner's case** (`test_the_owners_case_100_tickets_6_leases`): 100 tickets, a pool of 6: the last finish is
within 0.85 to 1.35 of 100 / 6 × the mean run (24 min) × the runs each needs (1 / 0.9 / 0.9) ≈ 8.2 h; on the demo the
legend said "last of 102 ticket done in about 9.1h (p90 11h)" where the critical path's projection said 56 min.
**Erlang C:** an M/M/c queue (c = 3, ρ = 0.8) waits within 12% of Erlang C's Wq.

**Size: 886 net lines, 86 over the 800.** The refined brief's survival curves (68), the path's fundamental matrix
(23) and the levelled Timeline's Lanes (about 60 in relations.js) came on top of the queueing simulation; the backtest
itself was moved into `tests/`, and the measured-rate cap was removed. Nothing else is left to cut without dropping
part of the definition of done.

**Left:** a goal that gates a block is not simulated (it takes whenever it has room); ticket-factory's workspace pool
(held from `work` to `close`) is a capacity no block declares, and its record's `work` gives tickets back every ten
seconds while the AI seat is busy, which the simulation replays as rework: a run on that record is slow, and the
budget cut it to 3 runs on the screenshot's page (`eta-shots/ticket-factory-item.png`).

### After the gate review (merge after fixes)

Fixed: an item older than every stay seen gets the curve's tail (the longest tenth's mean excess), never nothing
left; a run's length is drawn from the block's run-time curve with the leases still held censored (no length bias
toward finished runs), its ending from the recorded attempt nearest that long, and a run past its TTL expires at it
(for a leased one too, and the failure what-if reaches leased runs); every open item is read, the latest 2,000 only
for the fit; no run within the budget is "not worked out", under 20 runs no p90; the backtest counts an item
estimated beyond the horizon as a miss, and counts apart those it cannot judge (`unresolved`) and those with no run
(`not worked out`); its bias is the estimate's mean against what happened (a median sits below a skewed finish's
mean, so the p50's own "bias" was not one), with the share finished by their p50 beside it. One worker thread (the
latest ask first) and an LRU of eight; queue positions by a map; the pooled and all-kinds curves censored; visits
said in the legend; the pages say what is not modelled, the run count, the blocks assumed, the p90's date when it is
another day, and an item's expected start and dead-letter share.

**The table after the fixes** (items (unresolved), MAE of the p50 in minutes, bias of the mean in minutes, share by
their p50, share by their p90):

| components | owner's case, 3 truths | overloaded (6/h, pool 3) | ρ ≈ 0.7 (3/h) | ticket-factory record |
|---|---|---|---|---|
| path | 250, 170, −152, 0.12, 0.39 · 247, 153, −131, 0.16, 0.42 · 252, 172, −155, 0.13, 0.36 | 335 (5), 353, +15, 0.46, 0.67 | 109, 209, +98, 0.60, 0.91 | 33, 1.0, +0.4, 0.64, 0.88 |
| + survival | 250, 160, −122, 0.18, 0.52 | 318 (22), 329, −37, 0.23, 0.73 | 109, 206, +37, 0.50, 0.94 | 33, 1.5, +1.2, 0.79, 0.97 |
| + queues | 250, 61, −21, 0.36, 0.82 | 309 (31), 254, +274, 0.56, 0.84 | 109, 214, −71, 0.40, 0.81 | 33, 5.9, +7.8, 0.82, 0.00 * |
| + leases (all) | 250, 61, −4, 0.36, 0.93 · 247, 54, +21, 0.57, 0.94 · 252, 65, −9, 0.49, 0.89 | 275 (65), 267, +772, 0.64, 0.96 | 109, 207, +42, 0.52, 0.91 | 14, 2.7, +2.4, 0.71, 0.29 * |
| all but arrivals | 250, 61, −9, 0.38, 0.88 | 340, 268, +54, 0.52, 0.66 | 109, 203, −85, 0.46, 0.73 | 33, 11.5, +2.8, 1.00, 1.00 |

(The owner's case's middle rows are its first truth's.) In the owner's case the full set is unbiased (the mean within ±21 min against a 54–65 min error, about half finished
by their p50) with the p90 covering 89–94%. In the overloaded record the queue grows past every cut and the mean is
carried by the long tail (+772 min, with 65 items still open at the record's end); the p50 is about right (0.64).

\* **The ticket-factory record's anomaly.** Its `work` step's runs are mostly give-backs: 194 of its 250 attempts are
"nack, after 10 s, not counted", the step waiting for a free workspace (the pool `code`, size 3, held from `work` to
`close`: a capacity no block declares). The simulation replays each as an attempt that holds the agent's one seat
and puts the ticket off for ten seconds, so tickets queue behind each other's give-backs and every estimate is late
(without arrivals: all finish before their p50, the error ×10 the path's). With arrivals at the record's rate as well,
the queue at `work` outgrows what it drains, the runs are slow, and the five-second budget cuts them: under 20 runs no
p90 is said (counted as misses: 0.00), and at cuts where no run finished the items are not worked out (14 of 33 left).
Declaring the workspace pool as a capacity (a gap: a block's `workspace:` pool is not read as one) is what would fix
it; dropping uncounted give-backs from the attempts would hide the wait instead.

**Size: 958 net lines, 158 over the 800.** The review's fixes added 72 (the tail, the run-time draw and TTL, the worker
and its LRU, the pages' words on runs, limits, assumed blocks and dates). Nothing is left to cut without dropping a
fix or part of the definition of done.

### The workspace pool as a capacity

A block's `workspace:` pool (SPEC §12k) is now read as a capacity held across states: a workspace is taken at the item's
first run of a block that uses the pool and held, whatever state the item moves through, until it finishes (or is a
dead letter); who holds one at the moment estimated is read from the workspaces' own events (`ergostat.workspace.*`).
An item that needs one while every one is held waits in its queue, holding nothing (not the agent's seat); a run of
a workspace block that was given back uncounted without acquiring one (the record's "put off ten seconds" for want of a
workspace) is that wait, so it is dropped from the block's attempts instead of replayed as a run. A block with fewer
than five runs takes its state's stay curve as its runs, where there is one, instead of an assumed ten minutes (the
first cut of this record had a block with three runs). Test:
`test_a_workspace_pool_is_held_from_its_take_until_the_item_finishes` (a pool of 3 held across dev and review).

**The ticket-factory row now** (items (unresolved), MAE min, bias of the mean min, by p50, by p90):

| components | ticket-factory record |
|---|---|
| path | 33 (0), 1.0, +0.4, 0.64, 0.88 |
| + survival | 33 (0), 1.5, +1.2, 0.79, 0.97 |
| + queues | 33 (0), 1.5, +1.0, 0.70, 0.94 |
| + leases (all) | **33 (0), 2.1, +2.6, 0.91, 1.00** (was 14 worked out, 2.7, +2.4, 0.71, 0.29) |
| all but arrivals | 33 (0), 2.1, +2.5, 0.88, 1.00 (was 11.5 min: the anomaly is gone) |

Every item is worked out and the p90 covers all of them; arrivals no longer change it. The estimates are still a little
late (0.91 finish by their p50, the path's error being 1.0 min): in this 15-minute demo record most tickets end as dead
letters at review once the fake reviewer starts refusing, after the early cuts, so the early estimates hold
workspaces through reviews that in fact ended at once.

The owner's case is unchanged (no workspace pool): 250 items, MAE 61, bias −4, 0.36, 0.93.

**Size: 1,015 net lines, 215 over the 800 budget.** The workspace capacity adds 57 lines on the 958:
reading the holders from the workspaces' events, holding and freeing in the simulation, and waiting without holding.
It stands as the reason given above: every piece is part of the definition of done or a fix the gate asked for.
