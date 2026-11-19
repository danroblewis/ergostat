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

## Where it stopped

Done. Measured on main, and on a throwaway copy of modelling-core 860b711 with this branch's engine files (diagram.js
as a patch):

**1. The stub at changes-accepted, and stubs like it.** Four causes, four fixes:

- **A pipe point a pixel off the valve's line.** A stock's pipe point is moved onto the line of a valve facing it,
  rather than left a pixel or two off it (a pipe jogs on the valve to reach such a point). The first routing pass
  gets these points too.
- **Jogs.** A short jog on the valve's point counts as a turn there, so the pass tries both axes.
- **Ties.** A tie between the two axes goes to the one the flow's two ends lie along.
- **A valve between two stocks one over the other** may stand upright between them with its name beside it. This
  applies only where it lies within both stocks' widths. Its goal goes with it, beside it, or past the stocks level
  with it. A place where the goal fits is tried first; the valve goes alone only where its goal stays within 160px.

**2. The closed box given a row of its own.** A closed system linked to nothing, in a view with an open system, is left
out of ELK's layout. It goes in the free place, among the other parts or round them, that leaves the drawing fitting
the screen best.

**Ceilings, with modelling-core's template.** valve-orientation-mismatch is back to main's ceiling or under it, and
satellite-far is within modelling-core's recorded ceilings:

| example | valve-orientation-mismatch: modelling-core | now | main's ceiling |
|---|---|---|---|
| disk-space | 3 | 0 | 0 |
| file-queue | 3 | 0 | 0 |
| this-mac | 3 | 0 | 0 |
| software-factory | 1 | 0 | 0 |
| image-squeeze | 6 | 1 | 3 |

**Fit.** ops open=backups goes back from 0.82 to 1.119, which is main's fit before the template. On main, no ceiling
rises and no recorded size worsens: every view test passes with main's fixtures. Coordinator open=observer is at 0.852
against the recorded 0.866, within the size test's slack.

**Router time.** Coordinator with everything open takes 18.4s against main's 19.5s (load average 8): no worse.

**Screenshots.** ~/ergostat-wt/layout-shots/layout4-{disk-space-whole, file-queue-whole, ops-open-backups}-{before,after}.png,
drawn with modelling-core's template.
