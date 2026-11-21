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

Round 6 (main bccf2e5 already merged in 37a7827; no conflict left in `dev/bin/status.py`): the factory's unit run
failed only on `tests/test_factory_sessions.py::test_the_container_mounts_only_the_sessions_own_folder`, line 179.
Confirmed here: the suite container's `HOME` is `/home/dev`, and the mount's container side is `sessions.Session.HOME`
= `/home/dev/.claude/projects` (the agent image's user), so `str(Path.home()) in m` matches the path inside the
container, not a host folder; the host side (`keep.raw`, under tmp) is not in the home. `dev/bin/agents.py`,
`dev/bin/sessions.py` and the test are unchanged by this branch (`git diff main...HEAD` is empty for them), so main's
own tree fails the same way in this container. Following lesson-13, it is not fixed here. The fix (check only the host
side of each `-v`, before the last `:`) belongs in its own gap. Left, as before: a unit run on the merged tree once
that test (and the lease restart test) is fixed on main, and the browser files.

## Where it stopped

Parked by the factory (implementor, 2026-11-20 14:18).

Its fast suites failed 2 times (the kill rule); the last: the fast suites failed (unit: tests/test_factory_sessions.py::test_the_container_mounts_only_the_sessions_own_folder, tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth, tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere).

```
ner', 'implementor_model': 'opus', 'implementor_session_usd': 5.0}})

    def test_the_container_mounts_only_the_sessions_own_folder(tmp_path, mods):
        fac, sessions, cfg = mods
        agents = module("agents")
        keep = sessions.Session(cfg, "reviewer", None)
        args = agents.run_args({**cfg, "ai": {"reviewer_model": "opus", "reviewer_session_usd": 1}}, "reviewer",
                               tmp_path / "work", "n", keep)
        mounts = [args[i + 1] for i, a in enumerate(args) if a == "-v"]
        assert mounts == [f"{tmp_path / 'work'}:/work:ro", f"{keep.raw}:/home/dev/.claude/projects"]
>       assert not any(str(Path.home()) in m for m in mounts) and "run" not in keep.raw.parts
E       assert (not True)
E        +  where True = any(<generator object test_the_container_mounts_only_the_sessions_own_folder.<locals>.<genexpr> at 0xffff775cd1c0>)

/work/tests/test_factory_sessions.py:179: AssertionError
=========================== short test summary info ============================
FAILED tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere
FAILED tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth
FAILED tests/test_factory_sessions.py::test_the_container_mounts_only_the_sessions_own_folder
3 failed, 1893 passed, 69 skipped in 254.63s (0:04:14)
{"rc": 1, "wall_s": 255.8, "peak": {"threads": 356, "rss_mb": 1665.1, "procs": 124, "worker_mb": 467.7}, "killed": null, "workers_killed": 0, "left_behind": 0}

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-20 14:18).

Its runs failed past their attempts (a dead letter):
- attempt 4: ack
- attempt 5: ack
- attempt 6: nack the run ended with gap/pool-control still parked
- attempt 7: nack the run ended with gap/pool-control still parked

## Where it stopped

Continued (gap/pool-control-continued, round 1): main 39d47bf merged in (64c1848). Seven files conflicted. Each is
resolved keeping main's changes and the branch's:
- `dev/bin/pools.py`: main's merge-queue batch (`BATCH_MOST`, `wait_off`, `tune_batch`, `batch`/`batch_since` in
  `run/pools.json`) sits beside the risk tuner. `tune` runs the risk law for the role pools, then `tune_batch`.
  The batch goes through the same `raise-pool` action, so its ask now carries `was` and goes through `raise batch WAS
  TO` (stale unless the batch is still WAS, under the lock; no risk check for it). `set` and `read` take `batch` too.
  Main's streak tuner (`outcomes`, `decide`, `PAUSED`) stays removed, since this gap replaces it.
- `dev/factory.toml`: main's operator values are kept (`implementor_max = 9`, `reviewer_max = 6`, `batch`,
  `batch_max`), along with the branch's `probation` and `cycle_hours`. `HARD` goes from 8 to 9 so the operator's 9
  (the block's `pool: 9` in `building.yaml`) is not cut short. It is still a hard ceiling (lesson-4).
- `dev/model/pools.yaml`: the `queue-batch` stock and its flow sit beside the risk loop. The tuner's `in` takes
  `goal.queue-wait-short.error` too and its `out` takes `flow.queue-batch-steps`. The action's args name `batch`.
  The tuner runs every 10m again, not main's 7d pause.
- `dev/bin/status.py`: main's backlog, switch, resources and times lines, plus the branch's `Pools` line.
- `ergostat.yaml`, `dev/README.md`, `tests/test_factory.py`: both sides' text. In the test Factory, `streak` becomes
  `probation` and `batch_max` is kept.

The operator's pause, a choice made with no one to ask: main paused the role pools' tuning (operator, 2026-11-20:
"it lowered the owner's pools on parks caused by main; pool-control replaces it"). Its test,
`test_the_pool_tuner_is_paused_and_never_lowers_the_owners_pools`, failed on the merged tree. The risk tuner does
not count parks, but it lowered the hand-set pool of 3 because 3 had never been run (the wide prior). On the live
instance it would step the owner's hand-set pools down in the same way, with no gate. The more reversible option
keeps the pause as a setting: `[pools] hold = true` in `dev/factory.toml`. While it is on, the tuner measures and
says what it would do (`held` on `pool.measured`) and never moves the implementor or reviewer pool. The batch is
still tuned. Setting `hold = false` is the operator's move that turns the control law on. A missing key counts as
not held (the test Factory and the acceptance tests run the law). Any value other than `false` holds. Main's test
now asserts the repo's `hold = true`, sets the hold in its Factory, and checks that the tuner says `lower` but does
not do it. Unheld, the same record lowers 3 to 2. With `held()` broken (always false), the test was seen to fail,
then restored (lesson-9). The README says how to lift the hold.

Size: 328 net lines outside `tests/` and `docs/` against main (within 350; this counts `dev/README.md` and the YAML).
Here: ruff clean (`ergostat tests scripts dev/bin`); `tests/test_factory.py` 90 passed, 2 skipped;
`tests/test_factory_knowledge.py` 61 passed. Not run here: the whole unit suite and the four browser files (the
factory runs them). The earlier unit failures (`tests/test_leases.py` restart and watchdog tests,
`tests/test_factory_sessions.py` mount test) are main's code, which this branch does not touch (lesson-13).

Continued, round 1, after the factory's fast suites: the `unit` tail named no test (one `F` at about 25%). Run here
in full as the factory runs it (`suite_watch.py`, `-n 8 --dist worksteal`): 2228 passed, 2 failed.
- `tests/test_factory_resources.py::test_my_turn_respects_headroom` was this branch's fault. The test loads
  `dev/bin/pools.py` by file path, with only `fac` registered and `dev/bin` not on `sys.path`, so pools.py's new
  top-level `import risk` raised `ModuleNotFoundError`. Fixed in the code, not the test: `risk` is now imported inside
  `measured` and `tune`, the two functions that use it (the way pools.py already imports `measure` and `resources`).
  The file now passes (10 passed).
- `tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere`: main's code (`ergostat/`),
  which this branch does not touch. It was already named in the parks above as load-dependent (lesson-10, lesson-13).
  Not fixed here.
- In an earlier `-x -n 4` run, `tests/test_index_files.py::test_two_processes_one_tidying_never_corrupt_an_index_another_has_open`
  failed once and passed alone (8 passed). Its spawned child imported `dev/bin/queue.py` as the stdlib `queue`, because
  main's tests insert `dev/bin` into the worker's `sys.path` and never take it out (`tests/test_backlog.py:24`,
  `tests/test_factory.py` `test_two_gaps_editing_gaps_md_merge_cleanly`, `tests/test_factory_knowledge.py:116,600`,
  `tests/test_factory_times.py:36`). Whether it fails depends on which tests share a worker. That is main's code
  (lesson-13), and its fix (`monkeypatch.syspath_prepend`, or renaming `dev/bin/queue.py`) belongs in its own gap.

Here: `tests/test_factory_resources.py` 10 passed; `tests/test_factory.py` and `tests/test_factory_knowledge.py` 151
passed, 2 skipped; ruff clean (`ergostat tests scripts dev/bin`). Not run here: the four browser files.

Continued, round 1, after the factory's next fast-suite run: the merge of main 39d47bf was already committed
(64c1848c; no conflict markers left, main an ancestor of HEAD). The `unit` tail given names no test (one `F` at about
12%). Run here in full as the factory runs it (`suite_watch.py`, `-n 8 --dist worksteal`, on e88e2055): 2229 passed,
1 failed, rc 1, killed null. The one failure is
`tests/test_warm.py::test_the_owners_stop_is_said_only_on_the_run_it_stopped`, at a `wait_for(..., 10)` on
`agent.ran`/`agent.failed` after `stop_run`. It builds its own model in `tmp_path` and exercises the warm runner under
`ergostat/`, which this branch does not change; alone it passes (`tests/test_warm.py` 21 passed). Load-dependent and
main's code (lesson-10, lesson-13): not fixed here. `test_my_turn_respects_headroom`, this branch's fault last round,
passed in this full run. No code changed in this round. Ruff clean (`ergostat tests scripts dev/bin`). Not run here:
the four browser files.

## Where it stopped

Continued, round 2: main 979c53ca is merged in (fe9a4711; main an ancestor of HEAD, no conflict markers left). There
were no review findings to answer. No code changed this round: the only failures since round 1 were main's
load-dependent tests (`tests/test_warm.py`, `tests/test_leases.py`), and nothing names a fault in this branch.
Here, on fe9a4711: ruff clean (`ergostat tests scripts dev/bin`); `tests/test_factory.py`,
`tests/test_factory_knowledge.py` and `tests/test_factory_resources.py` 193 passed, 2 skipped; `tests/test_backlog.py`
16 passed; `tests/test_factory_times.py` 7 passed; `tests/test_factory_sessions.py` 5 passed (the mount test that
failed in round 6 passes now). Size: 329 net lines outside `tests/` and `docs/` (within 350). This session refused the
whole-suite run (`suite_watch.py`, `-n 8 --dist worksteal`), so the factory has to run it, along with the four browser
files, on this tree. If it fails only on main's lease or warm-runner timing tests, that belongs outside this gap
(lesson-10, lesson-13).

Continued, round 2, after the factory's fast suites: the `unit` tail given ends at about 99% (only dots, skips and
the one known `x`), with no `F` or `E`, no pytest summary and no `suite_watch` JSON line. So the run was cut off from
outside before it finished. No test failed it. Run here in full as the factory runs it (`suite_watch.py`, `-n 8
--dist worksteal`, on 24dc5dda): 2339 passed, 69 skipped, 1 xfailed in 524.7 s, rc 0, killed null, 0 left behind.
The suite has grown to about 2,400 tests, and its wall time here (525 s) is about twice the 255 to 266 s of the
earlier runs. If the factory's `unit` slot has a time limit near that, the limit stops the run, not this branch.
That limit (or the suite's length) belongs to its own gap (lesson-13). No code changed. Ruff clean (`ergostat tests
scripts dev/bin`). Not run here: the four browser files.

Continued, round 3: main c5eb54e6 merged in (be5c85c0). The two conflicts, `dev/bin/pools.py` and
`dev/model/pools.yaml`, were in the header comments only. Main's text says the blocks take their pools from the stocks
(`pool: {now: stock.implementor-pool, most: 9}`), the engine holds each block to the pool now at every dispatch, and
the gates and `my_turn` hold them to the headroom. That text is kept, along with the branch's risk wording. No code
changed: `HARD = 9` already matches the blocks' `most: 9` and `most: 6`. Here: `tests/test_factory.py` 132 passed,
2 skipped; `tests/test_factory_knowledge.py` and `tests/test_factory_resources.py` 85 passed; `ruff check ergostat
tests scripts` is clean. With `dev/bin` added, ruff finds B023 at `dev/bin/plan.py:315` and E501 at
`dev/bin/review.py:41`. Both files are identical to main's, so the fix is outside this gap (lesson-13). Not run
here: the whole unit suite and the four browser files (the factory runs them).

Continued, round 3, after the factory's fast suites: main c5eb54e6 was already merged (be5c85c0, main an ancestor of
HEAD, no conflict markers in `dev/bin/pools.py` or `dev/model/pools.yaml`). The `unit` tail given shows one `F` at
about 19% and is cut off at about 61%, with no pytest summary and no `suite_watch` JSON line, so it names no test.
This session refused the whole-suite run (`uv run python scripts/suite_watch.py -- uv run python -m pytest -q -n 8
--dist worksteal -p no:cacheprovider`), and a shell loop over single files (each file was then run by its own command). So
the failing test is still not named, and no code was changed blindly. Every test file that loads `dev/bin`, `dev/model`
or the pools passes here: `tests/test_factory.py` 132 passed, 2 skipped; `test_factory_knowledge`,
`test_factory_resources`, `test_factory_sessions`, `test_factory_times` and `test_backlog` 116 passed; `test_queue`,
`test_factory_manager`, `test_agents_drop`, `test_workspaces`, `test_slowjudge`, `test_scale_caches`,
`test_leased_workspaces`, `test_extremes_closed`, `test_eta`, `test_code_health_coverage` and `test_closedloop` 147
passed (`-n 4`). Main's load-dependent files named in earlier parks (`test_leases`, `test_warm`, `test_index_files`)
pass too: 66 passed (`-n 4`). Ruff is clean (`ergostat tests scripts`). Left: a full `unit` run whose output reaches
pytest's summary, so that the `F` gets a name. If it names a test outside this branch's files, it belongs to its own
gap (lesson-13). Also left: the four browser files.
