# fastroute

**The gap.** The coordinator example's view with everything open routes in 18.0s on main, and in 19.1 to 20.0s with
modelling-core's larger modelling template (debaf83). The page test's bound (ROUTED_BOUND_MS) is 20s, so the view
fails some runs and blocks modelling-core's merge.

## Definition of done

Large views route faster, without raising the bound. Coordinator open=* with modelling-core's template (a throwaway
copy of debaf83 with this branch's engine files) routes in under 14s on this machine. Its per-pass timings are
reported before and after: ELK, the first pass, libavoid's routing, the passes after routing. No layout rule's count
is worse on the corpus (the examples, and the generated models). The drawing changes only where routing changes it;
if it changes, there are before and after screenshots.

## Acceptance tests

- `tests/test_diagram_rendering.py::test_every_view_draws_cleanly_and_in_time` (routing within its bound) on main and
  on the modelling-core copy.
- The corpus run (`python -m tests.layout_corpus`), before and after, compared per rule.
- The fast suites under scripts/suite_watch.py, one at a time, rc 0, no skips.

## Size

Within the default budget.
