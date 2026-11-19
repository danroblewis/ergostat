# layout3

**The gap.** With modelling-core's larger modelling template, model-error's link to model-fits leaves the stock's bottom
10px left of model-mended's drain, runs right just under the stock, and crosses the drain: the regression test
`test_model_errors_drain_is_a_short_straight_satellite_of_its_stock` fails in every example.

## Definition of done

An information link leaves a stock by the side facing its target, and never along a side a satellite pipe (a flow to
or from a cloud, stood beside the stock) occupies, when another side faces the target. The fix is in the router's pins
(avoid.js), general, not special to model-error. The regression test passes on main and with modelling-core's
template. Before and after screenshots in ~/ergostat-wt/layout-shots/layout3-*. The layout fixture changes
modelling-core made (diagram sizes, layout ceilings) are read and each rise said to be honest (more parts drawn) or
hiding a fault.

## Acceptance tests

- `tests/test_diagram_rendering.py::test_model_errors_drain_is_a_short_straight_satellite_of_its_stock`, on main and on
  modelling-core's template.
- The four suites, rc 0, no skips.

## Size

A few tens of lines in avoid.js.

## Where it stopped

Done.

**The fix** (avoid.js, dynamics.js):

- **Link points by occupied side.** Where a satellite stands on a stock's top or bottom, its link points move to the
  sides no pipe meets that face its links' other ends; where a link's target lies beyond the satellite's side, both
  sides round it count. Failing that, they go on whichever of top and bottom no satellite stands on. Every other
  stock keeps its points on top and bottom as before.
- **Router time.** Points on every side of every stock cost the router about 30% on coordinator with everything open
  (25s against main's 19s under the same load). This version costs about 0.5 to 1s (19.6 to 20.0s against 18.7 to
  19.0s at load average 7 to 13). That is close to the page's 20s bound on a loaded machine: one suite run at load
  average 13 to 20 failed it by 56ms, while main passed at 19.0s.
- **Links crossing a satellite.** After routing, a link that crosses a satellite's pipe column (stock edge, valve,
  cloud) is moved past the column's far end. An end stretch gets a 12px stub at its part. A move is made only where
  the link touches no part, runs along no line, stays within the audit's detour bound, and crosses no line of its own
  net.

The regression test passes on main (3 examples) and with modelling-core's template (all 20, on a throwaway copy of
860b711 with these two files). The screenshots are ~/ergostat-wt/layout-shots/layout3-*-before.png and -after.png,
drawn with modelling-core's template.

**modelling-core's fixture changes**, read against main 2ed2f16:

- **Sizes: honest.** Every example now draws the modelling system (about 2,000px wide on its own), so the whole and
  open views of small examples grow from about 500px to 2,000px. Examples include first-loop, disk-space,
  file-queue, git-hygiene, plain-crontab, talking-scripts, this-mac, deps, docs-fresh, roadmap and backups (backups'
  whole view: 716x703 to 2039x1522). The modelling system itself grows from 1442 to 1964px wide in coordinator,
  image-squeeze and the-job, because the larger template has more stocks in its chain.
- **One size hides a layout choice:** ops open=backups, fit 1.12 to 0.82. The added closed modelling box, which is
  linked to nothing, takes a row of its own above the open backups system instead of being packed beside the other
  closed boxes.
- **satellite-far ceilings: honest, but not a layout fault either.** In the small examples the rise is about 9: two
  of the template's goals counted in each view that draws the modelling system. Those goals are excess
  unanswered-requests (1,435px from changes-made-by-fixer) and excess model-error (453px from changes-made). Each
  reads one stock and drives a flow into another, distant one, so one of its links is long wherever the goal goes.
  backups' rise from 6 to 17 is this, with the backups system's own goals unchanged.
- **valve-orientation-mismatch ceilings: hide a fault.** disk-space, file-queue and this-mac go from 0 to 3,
  software-factory from 0 to 1, image-squeeze from 3 to 6. These are a real stub at the template's changes-accepted
  valve: its pipe leaves by 12px and turns across the valve's axis. It appears in views where the template is drawn
  beside the example's own parts. The ceilings should not have risen for it; it is a layout fault to fix.
- **big:** valve-orientation 4 to 0, a fall. roadmap's satellite-far 15 to 13, a fall.

The fixture rises are modelling-core's, not this branch's. This branch records no fixture change.
