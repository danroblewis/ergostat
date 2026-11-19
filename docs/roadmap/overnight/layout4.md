# layout4

**The gap.** Two layout faults hidden behind ceilings that modelling-core raised:

1. A stub at the modelling template's changes-accepted valve: its pipe leaves by 12px and turns across the valve's
   axis. It appears when the template is drawn beside an example's own parts. valve-orientation-mismatch ceilings went
   0 to 3 in disk-space, file-queue and this-mac, 0 to 1 in software-factory, 3 to 6 in image-squeeze.
2. A closed system box linked to nothing takes a row of its own above an open system, instead of being packed beside
   the other closed boxes (ops open=backups: fit 1.12 to 0.82).

## Definition of done

Both are fixed in the layout engine, generally, not for these names. With modelling-core's template (a throwaway copy
of 860b711 with this branch's engine files), the valve-orientation-mismatch ceilings stay at main's values in those
examples, and ops open=backups fits about as well as before the template came (fit at least 1.0). On main, no ceiling
rises and no recorded size worsens. The router's time on coordinator with everything open does not grow. There are
before and after screenshots in ~/ergostat-wt/layout-shots/layout4-*.

## Acceptance tests

- `tests/test_diagram_rendering.py::test_every_view_draws_cleanly_and_in_time` (ceilings, sizes, routing time), on main
  and on the throwaway modelling-core copy, for disk-space, file-queue, this-mac, software-factory, image-squeeze and
  ops.
- The four suites, each under scripts/suite_watch.py, one at a time, rc 0, no skips.

## Size

A few tens of lines in the engine.
