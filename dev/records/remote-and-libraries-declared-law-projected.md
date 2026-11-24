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

## Where it stopped

Built, round 1: all five items, the four acceptance tests in tests/test_known_laws.py, and one more
(test_a_declared_law_whose_output_cannot_be_moved_is_external_not_run, item 4). 65 net lines of code (budget 90).
Each test was seen to fail with its code broken: models() ignoring `law:` fails the first three; `how` always
'identified model', the what-if not applied and the old `elif` in findings fail the projection, wins, what-if and
not-run tests. The risk check (no `hpa.` name in `sampled`) can fail only if a declared model carries `se`; the risk
code samples `m.se`, which a declared model leaves empty. main had not moved since the branch was made: nothing to merge.

Choices made without anyone to ask, each the most reversible:
- A declared law is started from the record, so it needs at least one reading of its input and two of its output;
  with none it is not run (the generic stand-in moves the flow, as before), and external-unidentified says why.
- The record's grid (the output sensor's period) is resampled at the law's own period (an HPA's `every`) before
  `settle`, so its stabilization window counts the law's samples, not the sensor's.
- A declared block whose record is too short still says external-unidentified (it is not identified); it is no longer
  the only thing said about it, since the projection runs the declared law.
- What-if values are flattened to `"BLOCK.PARAMETER" → value` in `WhatIf.laws` so `WhatIf.key()` stays hashable. A
  value tried on a block whose law is not run ahead adds a note saying it changes nothing, so it is not silently dropped.

Round 2 (the one finding, blocking): parse_whatif checked each declared-law parameter alone, so `block.hpa.min=8` with
`block.hpa.max=5` (each valid alone) built a law with min above max. Now, after the loop, each block's tried values are
checked together with its declared parameters by laws.check, once, and refused with its reasons (`block.hpa: the
values tried together: max: at least min`). Test: test_whatif_values_tried_together_are_checked_as_one_law, seen to
fail (DID NOT RAISE) with the check disabled. SPEC §12c says values are checked alone and together. 72 net lines of
code (budget 90). main had not moved: nothing to merge.

Round 3 (the queue's finding: conflicts with main in docs/SPEC.md, ergostat/numbers/external.py,
tests/test_known_laws.py): main 666d65d6 merged in. Main added a declared law tested against the record
(`external.declared`, external-law-disagrees); both kept. In SPEC §12d main's "it is not yet run in the projection"
and the branch's "It is not yet tested against the record" are each dropped, since both are now true; the module
docstring names both; the test imports keep both sides' (pytest, ergostat.model). test_known_laws, test_extlaw,
test_closedloop and test_remote_analysis pass after the merge; ruff clean. Still 72 net lines of code against main.
