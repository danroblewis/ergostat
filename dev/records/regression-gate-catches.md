# regression-gate-catches: How often each gate catches something, as evidence for keeping or changing it

depends-on: [regression-guarantees-model]

## Problem

A gate that fails is a finding, not a measure. Nothing counts how often each gate catches something, so nobody can see a gate that never does (proposal section 3, F7/F8 row; section 4, `gate-catches`; the refactor path, CLAUDE.md:35-37).

## Change

- dev/bin/times.py already reads each gap's events incrementally (dev/bin/times.py:3-5, :132-160). Its per-gap output (`gap.timed`) gains `catches: {gate: n}`, counted from the gap's `gap.sent-back` events by `sent_back_by`, from `queue`, `triage`, `review`, `lint` and `measure-runs` (the writers found in dev/bin/queue.py, triage.py, review.py, plan.py, manage.py), and from the implementor's refusals for strays.
- Each gate is in an allowlist `CATCHING` (lesson 8). An unlisted sender is counted under `unlisted` and named on stderr.
- `measure.py gate-catches-GATE` gives the catches in the last 14 days, by the event's time in the window.
- dev/model/guarantees-gates.yaml: one auxiliary per listed gate, with no goal. A gate never off is not a regression: this is evidence (proposal section 6c).
- The simplifier's brief (dev/prompts/simplify.md) names each gate with no catch in 30 days as a candidate to question, never to remove unasked.

## Definition of done

1. The catches per gate equal the sent-back events of a fixture.
2. An unlisted sender is counted and named.
3. The auxiliaries exist with no goal.
4. The simplifier's brief carries the quiet gates.
5. `ergostat check`: no errors.

## Files to touch

dev/bin/times.py, dev/bin/measure.py, dev/model/guarantees-gates.yaml (new), dev/prompts/simplify.md, tests/test_factory_times.py.

## Acceptance tests

- `test_catches_counted_per_gate_from_sent_back`
- `test_an_unlisted_gate_is_counted_and_named`
- `test_a_quiet_gate_reaches_the_simplifier_brief`

## Size budget

90 net lines outside tests/.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
