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
