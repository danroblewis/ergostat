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
