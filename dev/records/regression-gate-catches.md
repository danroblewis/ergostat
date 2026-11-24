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

## Where it stopped

Built, round 1: every item of the definition of done; nothing is left. Net lines: 85 counting dev/ (times.py +49,
simplify.py +3, simplify.md +6, guarantees-gates.yaml +17, dev/README.md +9, ergostat.yaml +1), inside the 90.

Choices made alone, each the most reversible I could see:

- `gap.timed` carries `catches: {gate: n}` as asked, and also `catch_times: {gate: [time, ...]}`. A count alone
  cannot be windowed "by the event's time", so the measure reads the times. A gap rolled up before it was timed with
  them has both unknown (`null`). The measure leaves those gaps out and counts them on stderr, never as 0 (lesson 3),
  and the brief says "unknown" when no gap's catches are known yet, never "every gate quiet".
- `lint` comes from `gap.plan-sent-back` by `plan_sent_back_by` (plan.py writes no `gap.sent-back` for it).
  `strays` comes from the implementor's `gap.measured` whose `suites_fast.stray` is set. Only the last try in a round
  is recorded that way, so a stray refusal fixed by a later try of the same round is not counted.
- `CATCHING` is exactly the definition's list plus `strays`. stack.py's `sent_back_by: stack-forward` (a conflict
  carried forward, not a gate) is not listed. It is counted under `unlisted` and named on stderr. Add it to
  `CATCHING` if the owner counts it as a gate.
- The brief's quiet gates are filled in by dev/bin/simplify.py's `definition()`, through a `{quiet_gates}` placeholder
  in dev/prompts/simplify.md. simplify.py is not in Files to touch, but the brief is a template that only it fills.
- The auxiliaries are in system `guarantees` and marked `exogenous: true`, so check asks for no cause.

Not run here: `ergostat check` from the CLI (that command was refused in this session). The acceptance test reads the
whole factory model through `ergostat.spec.read` and asserts no error and no finding on any gate-catches part, and
tests/test_factory.py::test_ergostat_check_on_the_factory_model_reports_no_new_finding passes.
