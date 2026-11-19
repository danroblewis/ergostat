# layout

**The gap.** The diagrams' layouts made comically bad choices: a stock right next to its cloud with the flow's valve
placed under ten other parts, so that a fat pipe ran down through them and back up; a valve an unreasonable distance from
its stock with the cloud off in a corner (model-error's drain in every modelling system); a valve kept level while its pipe
ran up or down, so the line zig-zagged through it. There were no common-sense rules written down, nothing to detect the
antipatterns, and no tests over many models to keep them from coming back.

(This file was written after the branch's first commits, when the overnight gates arrived: the work was already under way.)

## Definition of done

The rules are written down, each with its rationale and a measurable form, ordered by how bad a violation looks
(`docs/layout-rules.md`). Each rule has a detector over the drawn geometry (`tests/layout_rules.py`, reading what
`scripts/layout_geometry.js` takes off the page). A corpus of the examples and several hundred generated models runs every
detector in every view, and reports counts per rule and crops of the worst instances (`scripts/layout_corpus.py`, opt-in).
The layout engine is fixed for the worst rules:

- a flow between a stock and a cloud is a satellite of its stock, placed beside it on the natural side;
- a valve is placed as a point on its flow's route, then turned to the way the flow runs there, after the layout and
  after a drag;
- a valve between two stocks is put between them;
- rework runs back, so the chain reads left to right;
- a chain is wrapped into rows only when the rows fit clearly better.

The rendering suite fails on any critical instance of the rules. Recorded sizes are re-recorded only where layouts changed.

## Acceptance tests

- `tests/test_diagram_rendering.py::test_model_errors_drain_is_a_short_straight_satellite_of_its_stock`: the owner's case,
  on every example with a modelling system.
- `tests/test_diagram_rendering.py::test_a_valve_dragged_over_its_stock_stands_upright_on_its_top`
- `tests/test_diagram_rendering.py::test_generated_models_of_every_shape_draw_with_no_critical_layout_fault`
- `tests/test_diagram_rendering.py::test_every_view_draws_cleanly_and_in_time`: now also no critical layout-rule instance.
- The corpus before and after, per rule (in the report).

## Size

About 450 net lines of JavaScript in `ergostat/web/static` (satellites.js, avoid.js's first pass, places.js, valves.js,
layouts.js, diagram.js), within the 600 budget. The detectors, the corpus generator and runner, and the geometry reader
are tests and scripts.

## Where it stopped

Landing early, at the coordinator's request, with the engine fixes above. The remaining rules continue on this
branch.

**Size, corrected.** The estimate above was low. The branch is 1,049 net lines outside `tests/` and `docs/`:

- 585 in the engine (`ergostat/web/static`: satellites.js 224, avoid.js's first pass and routing fixes 199, places.js
  77, valves.js 52, layouts.js 15, diagram.js 13, interact.js 4, index.html 1);
- 464 in the opt-in corpus tools (`scripts/layout_corpus.py` 409, `scripts/layout_geometry.js` 55).

The overrun is the corpus tools. They are test infrastructure (the opt-in run of the detectors over several hundred
models the task asked for), kept in `scripts/` beside `diagram_audit.py`, which they extend. The engine itself is
within the 600.

**Left for this branch:**

- `label-collision` and `marker-collision` in dense views (loop markers' names over lines);
- `satellite-far` and `stranded-part` (a goal or auxiliary joined only through a satellite valve drifts);
- `signal-backwards` in the Blocks view;
- two critical instances main already had (recorded in `tests/fixtures/layout_known.json`): small-requests'
  regressions system and alert-triage with everything open;
- the router's time on the largest views is close to the page's 20s bound under load.
