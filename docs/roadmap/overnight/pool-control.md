# pool-control: the pools are sized by measured risk against the operator's risk tolerance

depends-on: []

Branch `pool-control`, from main. Asked by the owner: the worker pools are set by the level of risk, an estimated,
measurable quantity combining the risk of damaging the factory and the risk of low-quality work reaching the git
repository, weighed against the pressure for velocity; the operator sets an exogenous tolerance for risk and may raise
it to grow the pools. Today `pool-tuner` (dev/bin/pools.py) raises after three gaps in a row approved within one fix
round, which measures the work's review results, not risk.

## Definition of done

**Risk, in expected interventions per day** (a unit the operator feels: each harm ends in someone stepping in):
- *factory damage*: factory-caused interventions per gap processed (any outcome), from `intervention.recorded` events
  whose `class` marks the factory itself (environment-defect, self-reference, factory-missing-capability, queue
  interleaving, or `factory: true`); review findings and a reviewer's park are not harm;
- *low-quality production*: escapes per merged gap: a revert (`gap.reverted`), main failing its suites after a merge
  (the queue's next green-on-main check), or a later gap or intervention naming a merged gap as its cause (`caused_by`);
- `risk(n) = (factory rate + escape rate) × gaps per day at pool size n`, where each rate is estimated from the record
  with its uncertainty (e.g. a Beta or Gamma posterior with a weak prior), gaps per day from the measured cycle time, and
  a pool size never run gets a wider prior (more concurrency, paths not exercised), so its upper bound is high until
  evidence narrows it.

**Tolerance**: an exogenous parameter `risk-tolerance` (interventions per day, default 2) in the factory model, with
the owner's name on it: raising it is the operator's decision to trade risk for velocity.

**Control law**: the target pool is the largest n whose risk upper bound (e.g. the 90% bound) is within the tolerance
and with n not above the ready demand (ready + fix gaps); the pool moves toward it one step at a time, with a probation
of a few gaps after each raise (a setting); it drops by one at once when the current risk bound crosses the tolerance.
Raises stay gated (the coordinator approves) and each decision is an event carrying its evidence (the rates, their
bounds, the demand, the tolerance). The model draws it as a loop: risk an auxiliary from the intervention and escape
stocks, the tolerance a constant, the pool a stock adjusted toward its target with a delay, so it shows on the Dynamics
and Blocks diagrams. `dev/bin/status.py` prints risk, its bound, the tolerance and the target. README says how the
operator sets the tolerance and how to record an intervention so it counts.

## Acceptance tests

- `tests/test_factory.py::test_risk_counts_factory_caused_interventions_and_escapes_not_review_findings`
- `tests/test_factory.py::test_an_untried_pool_size_has_a_wide_bound_and_is_not_jumped_to`
- `tests/test_factory.py::test_target_is_the_largest_pool_within_tolerance_and_demand`
- `tests/test_factory.py::test_raising_the_tolerance_raises_the_target`
- `tests/test_factory.py::test_risk_over_tolerance_lowers_the_pool_at_once`
- `tests/test_factory.py::test_probation_after_a_raise`

## Size budget

350 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1: `dev/bin/risk.py` (new: the estimator and the control law, pure functions), `dev/bin/pools.py tune`
on top of it, the loop in `dev/model/pools.yaml`, the line in `dev/bin/status.py`, `dev/README.md`. About 284 net
lines outside `tests/` and `docs/` (within 350). The six acceptance tests pass, and each was seen to fail with the
code it guards broken (the allowlist widened to `review-finding`, the untried widening removed, demand ignored, the
tolerance not read, a drop held by probation, probation removed, a stale raise accepted).

Choices made with no one to ask (each the more reversible one):
- Both rates are Gamma posteriors (escapes per merged gap as a Poisson rate too), prior shape 0.5. A size's prior mean
  is the other sizes' evidence (not its own, to avoid counting it twice) times (1 + steps above the largest size
  tried). The bound adds the two rates' 90% bounds (conservative). The quantile is computed exactly (series and
  bisection), no approximation.
- The target counts only sizes whose bound, and every smaller size's, is within the tolerance, so each step up on the
  way is. When the target falls below the pool (the demand fell), the pool steps down by one too, ungated.
- The reviewer pool follows the implementor's, up to its own most; the risk is attributed to the implementor pool.
- Evidence is attributed to the pool size in `run/pools.json`'s history at its time (verdict, merge, intervention).
  This compares wall times (lesson-2) because nothing else ties an event to a pool size; an intervention with no time
  counts against the pool now (the worst case).
- The model's time is hours, so a unit of `interventions/day` is refused; the risk's units are `interventions` with
  "a day" in their descriptions, as `interventions-trend` does. `risk-tolerance` is read from `dev/model/pools.yaml`
  by the tuner (as `fac.daily_cap` reads the budget); unreadable, it is 0 and the pools go down to 1.
- A raise is approved through `pools.py raise ROLE WAS TO`, which refuses unless the pool is still WAS (a drop in
  between voids it), under a lock that the tuner's drops also hold. `[pools] streak` is replaced by `probation` (3)
  and `cycle_hours` (2, used until a cycle time is measured); pools are capped at 8 whatever `[pools]` says.

Not built, or not checked:
- "Main failing its suites after a merge (the queue's next green-on-main check)": the queue has no such check today.
  An escape is counted from a `broke_main` field said of the merged gap (README says how); the check itself would be
  its own gap.
- The queue's own interventions (`class: queue`, the queue stopped) are not counted: that class is not in the list
  above. Adding `factory: true` to `queue.py`'s `block()` would count them, if wanted.
- The owner's decision text in `dev/knowledge/decisions.md` ("pools rise only after a streak of good results") is
  left as the owner wrote it.
- The Dynamics and Blocks diagrams were not looked at: the model loads with no problem from `pools.yaml`, which the
  model test now asserts. The full unit and browser suites were not run here (the factory runs them); there is no
  remote in this clone, and the branch is already on the local main.

Round 1, after the factory's fast suites: `unit` was reported failed, but the output given names no failing test. It
ends at about 36% (all dots and skips, no `F` or `E`), with no pytest summary and no `suite_watch` JSON line, so the
run looks cut off from outside (a timeout or a kill), not failed by a test. The two test files this branch changes
pass on their own here: `tests/test_factory.py` (41 passed, 2 skipped) and `tests/test_factory_knowledge.py` (22
passed). No other test loads `dev/bin/pools.py`, `dev/bin/risk.py`, `dev/model/pools.yaml` or the repo's own
`ergostat.yaml`. `risk.py` has only bounded loops (series at most 100,000 terms, bisection 80 steps). This session
could not run the whole suite (only single files were allowed), so no code was changed blindly. The next step is a
full `unit` run with its whole output (or `-o faulthandler_timeout=300` to show what hangs), to name the test.

Round 2 (main 9244618, the $300 cap, merged in; no review findings were given to answer): no code changed. Running
the whole unit suite was refused in this session again, serial or under `suite_watch`, so the failing or hanging test
is still not named. After the merge, `tests/test_factory.py` (41 passed, 2 skipped) and
`tests/test_factory_knowledge.py` (22 passed) pass, and ruff is clean (`ergostat tests scripts dev/bin`). A search of
`tests/` again finds only those two files that load `dev/bin`, `pools.yaml`, `risk.py`, `status.py` or the repo's own
`ergostat.yaml`. If the cut-off run comes from load (lesson-10) or from a test this branch does not touch (lesson-13),
it belongs outside this gap. Left: one full `unit` run (and the browser files) by the factory, with the whole output,
or with `-o faulthandler_timeout=300` if it hangs again.

Round 3: the `unit` tail given this time ends right after `uv` installed the package. There is no pytest output at all
(not a dot, not a collection error) and no `suite_watch` JSON line. `suite_watch` prints that line on any exit it
lives through, SIGTERM included. So the run was killed from outside its container (a timeout or SIGKILL) before the
xdist workers reported; no test failed it. Here, collection is clean (`pytest --collect-only`: 1953 tests in 15 s, no
errors), `tests/test_factory.py` and `tests/test_factory_knowledge.py` pass (63 passed, 2 skipped), and ruff is clean
(`ergostat tests scripts dev/bin`). This session refused the whole-suite run again, so no code was changed: nothing
names a fault to fix. Left, as before: one full `unit` run by the factory that lasts long enough to print pytest's
summary, and the browser files. If the run is killed at the start again, the cause is the suite container or its
slot (lesson-13), not this branch.

Round 4, answering review/pool-control-1, every finding (lesson-12):
- Demand (risk.py `step`, pools.py `measured`; blocking): both changes. The demand now counts the gaps the implementor
  pool is building as well as those ready and at fix (`pools.DEMAND`), and the pool is never lowered for want of
  demand: when the target is below the pool for that reason alone, `step` holds (an idle slot costs nothing; only the
  risk bound crossing the tolerance drops it at once). Holding is the more reversible choice: no ungated move, no
  re-approval each time the backlog refills. `test_risk_over_tolerance_lowers_the_pool_at_once` now asserts the hold
  (pure, and through `pools.py tune` with nothing ready: demand 0, target 1, pool kept at 2). The model draws
  `pool-target` from `gaps-building` too; its `implementor-pool-steps` stays the smoothed `(target - pool) / probation-time`
  (a stock-and-flow view, not the step-by-step law), and its description says demand alone never lowers it.
- The factory's own interventions (risk.py `FACTORY`; blocking): `queue` (the merge queue stopped, `queue.py block()`)
  and `switch` (the upgrader could not bring the instance back, `live.py intervene()`) are in the allowlist, rather
  than `factory: true` written in two other files (fewer files touched, one list to read). Tested: the pure test counts
  both and their bound is higher; the tune test records a real `queue.block()` intervention and the pool drops for it.
- An approved raise decided again (pools.py `raise_pool`, lesson-1): under the lock, besides the pool still being WAS,
  the implementor's bound at TO must still be within the tolerance and the probation over; else it refuses (exit 1,
  nothing done). New test `test_an_approved_raise_is_decided_again_under_the_lock`.
- The reviewer pool (pools.py `tune`): it now follows independently of the implementor's decision: up with an approved
  implementor raise (in the same lock, up to its own most), down at once whenever it is above the implementor pool,
  each drop its own `pool.lowered` event with the evidence (asserted: two events, one per pool). A reviewer raise is
  still asked on its own only when the implementor holds and is above it (a raised `reviewer_max`), and refused above
  the implementor pool.

Seen to fail with the code broken (lesson-9): `step` lowering on demand again; the bound re-check removed; `queue` and
`switch` out of the allowlist; the reviewer not raised with the implementor. Each restored. `tests/test_factory.py`
and `tests/test_factory_knowledge.py`: 64 passed, 2 skipped; ruff clean (`ergostat tests scripts dev/bin`). About 300
net lines outside `tests/` and `docs/` (within 350). Not run here: the whole unit suite and the browser files (left to
the factory, as in rounds 1 to 3).

Round 4, after the factory's fast suites: the `unit` tail given ends at about 3% (all dots, no `F` or `E`) with no
pytest summary and no `suite_watch` JSON line, the same shape as rounds 1 and 3: the run was cut off from outside, not
failed by a test. This session refused the whole-suite run once more (serial, `-x`, `faulthandler_timeout=300`, under
`suite_watch`), so no test is named and no code was changed blindly. Here, after the round-4 changes:
`tests/test_factory.py` 42 passed, 2 skipped; `tests/test_factory_knowledge.py` 22 passed; ruff clean (`ergostat
tests scripts dev/bin`). A search of `tests/` again finds only those two files loading `dev/bin`, `dev/model`,
`pools.py`, `risk.py` or `status.py`. Left: one full `unit` run that lives to print pytest's summary (with
`-o faulthandler_timeout=300` if it hangs), and the browser files; if it is killed early again, the cause is the
suite's container or slot (lesson-13), not this branch.

## Where it stopped

Parked by the factory (implementor, 2026-11-20 14:05).

Its fast suites failed 2 times (the kill rule); the last: the fast suites failed (unit: tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth).

```
     from ergostat import runner as old
        old.kill_all()
        held = item(p, "ticket/1").fields["lease"]
        second = start(Project(mdl.load(tmp_path)))
        try:
            time.sleep(0.6)
            assert item(p, "ticket/1").fields["lease"]["holder"] == held["holder"], "the new engine reads the lease, and keeps it"
            assert item(p, "ticket/2").state == "ready", "the pool is full: the lease held counts"
            assert wait_for(lambda: item(p, "ticket/1").fields["lease"]["history"][0].get("how") == "expired", 5), \
                "expired on its TTL"
            assert wait_for(lambda: item(p, "ticket/2").state == "leased" or item(p, "ticket/1").state == "leased", 5)
        finally:
            second.close()
            old.STOPPING.clear()
        for i in (1, 2):                                         # stopped with ergostat: given back, not counted
            lease = item(p, f"ticket/{i}").fields["lease"]
>           assert lease["holder"] is None
E           AssertionError: assert 'fdf992014daa491082a945683c51c915' is None

tests/test_leases.py:434: AssertionError
=========================== short test summary info ============================
FAILED tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth
1 failed, 1890 passed, 69 skipped in 266.10s (0:04:26)
{"rc": 1, "wall_s": 266.8, "peak": {"threads": 356, "rss_mb": 1570.7, "procs": 124, "worker_mb": 500.4}, "killed": null, "workers_killed": 0, "left_behind": 0}

```

Round 5 (main bccf2e5 merged in): the one conflict, `dev/bin/status.py`, is resolved keeping both sides: main's
`status.py session GAP [ROLE] [N]` (and its `import sessions`) and the branch's `Pools` line (`pool_line`, `import
pools`), the docstring naming both. No other code changed.

The unit run that parked the branch is the first to reach pytest's summary: 1890 passed, 1 failed,
`tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth`. That failure is outside this gap
(lesson-13): the test builds its own model in `tmp_path` and exercises `ergostat/leases` and the engine, and this
branch changes nothing under `ergostat/` (its files: `dev/bin/{pools,risk,status}.py`, `dev/model/pools.yaml`,
`dev/factory.toml`, `dev/README.md`, the comment and `pools` system in `ergostat.yaml`, docs and tests). It is the
fixed 0.6 s sleep against a 1.5 s TTL that review/lease-shutdown-race-2 already named as load-dependent (lesson-10); its
fix belongs to that gap. No lease change is made here.

Here, after the merge: `tests/test_factory.py` 42 passed, 2 skipped; `tests/test_factory_knowledge.py` 22 passed; ruff
clean (`ergostat tests scripts dev/bin`). `tests/test_factory_sessions.py` (new from main) gives 4 passed, 1 failed:
`test_the_container_mounts_only_the_sessions_own_folder`, at line 179 only (`str(Path.home())` found inside a mount
path), while line 178's exact mount list passes. That looks like this container's HOME/tmp layout and is main's code
(`agents.py`, `sessions.py`), untouched by this branch; this session could not look at HOME to confirm. Left: the
factory's unit run on the merged tree (expected to pass once the lease test is fixed in its own gap, or on a quieter
run), and the browser files.
