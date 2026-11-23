# regression-template-docs-demo: SPEC and the agent guide describe regression guarantees, and a demo uses the template

depends-on: [regression-template]

## Problem

Once the `regressions` template exists, nothing tells a user or an agent when to offer it, and no demo shows it working (proposal milestone gap 7: "SPEC gains a section on regression guarantees, and the agent guide a paragraph on when to offer the template").

## Change

- docs/SPEC.md gains a short section next to 12g (claims and trust) and 12r (repair). It covers the four parts of a guarantee (measured quantity, setpoint, a loop that acts, seen broken on the diagrams), the template's parts, and what holding does not promise (proposal section 6c).
- docs/AGENT-GUIDE.md gets one paragraph: offer the template when a model declares `claims: tests` or uses `repair`, never add it unasked.
- examples/image-squeeze, which declares `claims:` (examples/image-squeeze/lab.yaml:43), uses the template.

## Definition of done

1. The SPEC section and the guide paragraph exist and match the template's parts.
2. image-squeeze uses it and passes `demo_check`.
3. Its goals hold in the healthy demo.

## Files to touch

docs/SPEC.md, docs/AGENT-GUIDE.md, examples/image-squeeze/lab.yaml, tests (the demo's own check, if one names its goals).

## Acceptance tests

- `scripts/demo_check.py image-squeeze` passes.
- `ergostat check` on the example: no errors.

## Size budget

20 net lines outside docs/ and examples/.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
