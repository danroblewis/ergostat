# remote-and-libraries-declared-law-projected: A declared law runs in the closed-loop projection and its risk

depends-on: [remote-and-libraries-known-controller-laws]

Problem: the closed-loop projection runs an external block only as its identified law (ergostat/numbers/external.py:155-171 models(); closedloop.py:14, :431 'identified model'). A declared law (known-controller-laws) is the owner's statement of what the controller does and is all there is when the record is too short to identify one, but the projection ignores it, so a what-if on an HPA's target cannot be projected.
Change: external.models prefers a declared law, else the identified one.
Definition of done:
1. For an external block with `law:`, models() returns an ExternalModel with form 'declared', basis 'its declaration', the declared Law, started from the record as settle() starts an identified one; with no law the identified path is unchanged.
2. The projection's notes and Run.how say 'declared law' for its flow, and the risk samples none of a declared law's numbers (they are stated, not estimated).
3. A what-if may change a declared law's parameter (`block.B.target=0.5` in parse_whatif's form) and the projection runs with it; an unknown parameter is refused naming the law's parameters.
4. external-not-run applies to a declared law as to an identified one.
5. SPEC §12c and §12d say it.
Files: ergostat/numbers/external.py, ergostat/numbers/closedloop.py, docs/SPEC.md, tests/test_known_laws.py.
Acceptance tests: test_projection_runs_declared_law (a short record with no identifiable law: replicas projected by the HPA rule under rising load reach the ceiling at max); test_declared_wins_over_identified (both present: how says declared); test_whatif_changes_declared_target (lower target: more replicas projected); test_no_law_unchanged.
Size budget: 90 net lines.

Area: remote-and-libraries. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
