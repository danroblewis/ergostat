# conformance-discovery-list: ergostat's conformance list: discovery algorithms, eleven cases from identification to residuals

depends-on: [conformance-list-files]

Problem: the proposal's section 6 discovery list is not written. Change: dev/conformance/discovery.yaml (`list: discovery`, 11 cases, all asked: true) and dev/conformance/checks/discovery.py CASE. Expected met: prometheus-draft and unwritten-loop (ergostat/spec/discover.py:60, :154), process-fopdt and process-integrating (ergostat/control/ident.py:310), law-onoff, law-proportional, law-pi and law-stepper (ergostat/numbers/extlaw.py:26). Expected unmet: law-changed (docs/GAPS.md:79-82) and law-kubernetes-hpa (GAPS.md:82-83). structure-from-residuals must be measured, not assumed, since finding-structure-from-residuals merged after the proposal (ergostat/numbers/structural.py). Each met check runs its algorithm directly on a seeded simulation, not a pytest node, with a stated tolerance (K within 5% and tau within 15%; k within 10%; the right law family). law-changed: a controller retuned halfway must be said changed with at most 1 false alarm over 30 unchanged seeds; law-kubernetes-hpa: `law: kubernetes-hpa` accepted and fitted to a simulated record (met once remote-and-libraries-known-controller-laws and remote-and-libraries-hpa-ratio-family merge; not a dependency, the case is simply unmet until then); prometheus-draft uses a fake Prometheus on loopback started and stopped by the check. Done: results on main recorded with each difference explained; each met check exits 1 with its tolerance at zero or a wrong family; every check gives the same result three runs in a row; the whole list runs under 10 minutes. Files: the list, the checks, tests/test_conformance_lists_ergostat.py. Budget: 260 net lines, dev/ counted.

Area: conformance. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 14:17).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 669, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 14:18).

Its runs failed past their attempts (a dead letter):
- attempt 3: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 4: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 5: nack exited 1
- attempt 6: nack the run ended with gap/conformance-discovery-list still parked

## Where it stopped

Built, round 1 (continued): dev/conformance/discovery.yaml (`list: discovery`, 11 cases, all asked) and
dev/conformance/checks/discovery.py, with acceptance tests in tests/test_conformance_lists_ergostat.py.

Results on main (each check run three times as its own process, the same result each time):

| Case | Expected (section 6) | Measured | Tolerance |
|---|---|---|---|
| prometheus-draft | met | met | the draft compiles; one stock (the gauge), one flow in and one out of it |
| unwritten-loop | met | met | the loop is unknown; its delay within 180 s (one grid step) of the true 270 s |
| process-fopdt | met | met | form fopdt; K within 5%, tau within 15% |
| process-integrating | met | met | form integrating; k within 10% |
| law-onoff, -proportional, -pi, -stepper | met | met | the law kept is the true family |
| law-changed | unmet | unmet | extlaw has no change test (`changed`) |
| law-kubernetes-hpa | unmet | unmet | `law: kubernetes-hpa` compiles, but `extlaw.fit` has no `ratio` family (FAMILIES, extlaw.py:29) |
| structure-from-residuals | unmet | **met** | a `residual-hidden-stock` adding a stock; tau within 50% |

Differences: structure-from-residuals is met, not unmet. Section 6 was written before finding-structure-from-residuals
merged. On a chain missing its first-order stock in transit (true tau 6 min), the finder now proposes
`residual-hidden-stock` with tau 8 min. The tolerance is 50% because the finder tries tau only at ½, 1 and 2 times
the lag it finds. law-kubernetes-hpa is unmet for a different reason than the proposal gives: the declared law is now
accepted (remote-and-libraries-known-controller-laws merged), and what is missing is the fit (the hpa-ratio-family gap
is not on main). The test reads both features, so each case reads as met once its feature lands.

Choices made with no one to ask, each the more reversible one:
- Each check takes `--scale=S` (it multiplies each tolerance; 0 means none) and `--family=F` (a family or form other
  than the truth's). The tests show each met check exits 1 with either. prometheus-draft has no number to tolerate.
  Its test breaks the stem match instead, and the check exits 1.
- law-changed assumes the change test will be `extlaw.changed(xs, us, dt) -> bool`. The gap that builds it
  changes the check's one call. A fake that always says changed (30 false alarms) and one that never does are both
  unmet.
- law-kubernetes-hpa reads "fitted" as `extlaw.fit` keeping the `ratio` family for a record of the HPA's documented rule,
  with its target within 10%. A fake ratio fit shows the check can say met.
- The `from:` lines moved since the definition was written. They are now extlaw.py:29 (FAMILIES), docs/GAPS.md:99-102
  and :102-103, and structural.py:833 (from_residuals).
- The 10-minute bound is asserted as each run under 54 s (11 × 54 s < 10 min). The whole test file, 33 runs of
  the checks among its tests, took 96 s.

Not run: the unit suite and the browser files (no page changed). Running the check script directly
(`uv run python dev/conformance/checks/discovery.py prometheus-draft`) was refused in this session, so every
measurement here comes from the acceptance tests run through scripts/named_tests.py. One probe I used while
measuring had to live in tests/, because the file tools refuse /tmp. It was deleted and never committed.

Overrun reason: 356 lines in dev/ against 260, because each of the 11 cases needs its own seeded simulation written apart from the code it checks (five truths: a process, an integrator, four controller laws, an HPA, a chain with a stock in transit), and the prometheus case needs its own loopback server.
