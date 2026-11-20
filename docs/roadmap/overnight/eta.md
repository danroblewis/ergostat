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
