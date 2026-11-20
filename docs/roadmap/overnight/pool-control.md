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
