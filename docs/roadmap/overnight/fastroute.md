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

## Where the time went, and what changed

Coordinator open=* with modelling-core's template (187 lines), per pass, idle machine:

| pass | before | after |
|---|---|---|
| ELK (first draw) | 0.19s | 0.20s |
| the spec | 3ms | 2ms |
| the first pass (each flow through its valve) | 0.15s | 0.15s |
| building the router(s) | 6ms | 17ms |
| libavoid's routing | 17.7 to 18.1s | 9.2s (5 groups) |
| the spacing pass (new) | | 0.15s |
| the page's passes after routing | 51ms | 50ms |
| **routed, end to end** | **18.1 to 18.5s** | **9.75s** |

Almost all of the time was libavoid weighing crossings: with the crossing penalty at 0 the same view routes in 0.3s.
That weighing grows fast with the lines routed together, so a view past 150 lines (GROUP_OVER) is routed in groups:
each open system's own lines (both ends in it), and the lines between systems together with the systems they reach
most, up to 100 lines (GROUP_CAP). A net (the lines from one point, or to one) is never split. Every part is in every
group's way. A crossing is weighed only within a group; the cross-system lines are weighed against the systems they meet most.

Lines of different groups can land on one track (no group sees the other), and the page's untangling trades the
stretches of a net's lines that cross. So a last pass routes every line together with no crossing weight: each line
keeps its group's way (its corners as checkpoints) except the ones that share a track with another line, are bent
past five times (BENT), or cross a line of their own net, which go free and are spaced from the rest. Only those
lines take the new way. A drag still reroutes in the groups.

Views up to 150 lines are routed as before (one group, no spacing pass): the generated corpus never reaches it.

## Results

- Coordinator open=* routes in 9.75s with modelling-core's template (was 18.1s), and in the page test 9.8 to 11.1s
  under load (bound 20s); image-squeeze open=* 8.9 to 10.8s (was 15.6s).
- Examples corpus against main (141 views): line-bends 6 to 3; label-collision minor 582 to 583 (a polarity sign
  over a line: eight such signs moved, seven went); every other rule equal. Only coordinator open=* and
  image-squeeze open=* changed.
- Crossings between lines (the audit's count; no layout rule counts them) rise: coordinator open=* 151 to 165,
  image-squeeze open=* 194 to 211. The lines the spacing pass takes free are routed with no crossing weight;
  weighing crossings there costs label collisions and bends (tried: label-collision major +2, line-bends +3).
  Through, overlap, detour, net crossings and part overlaps stay at 0, and the fit is unchanged.
- Generated corpus (80 models, 405 views): every rule equal.
- Screenshots: `~/ergostat-wt/layout-shots/fastroute-{coordinator,image-squeeze}-open-all-{before,after}.png`.
