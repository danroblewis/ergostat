# ui-the-headline-counts-the-system-s-goals-and-the-m: The headline counts the system's goals, and the model's upkeep apart

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q14 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** header on all pages; project switcher

**The problem:** '2 loops off' in red on software-factory and the-job is entirely modelling's own two goals; every demo is permanently red, so red stops meaning anything.

**The change:** Header reads '0 goals off · model upkeep 2' (the second part in the muted colour, not red). The switcher uses the same definition, and states unknown goals separately ('7 off, 1 unknown') instead of adding them.

**User stories it serves:** A2, B2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796 with only requests-handled and model-fits off the header's first figure is 0 and is not red, and the text 'model upkeep 2' is present; the switcher entry for a demo read from another demo shows the same first figure as that demo's own header at that moment.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built (35c0bb01), about 23 net lines outside tests. The choices made alone, each the most reversible:
- "Model upkeep" is the goals in the system of the model's `use: modelling` (`state.upkeep`, one definition read by
  `/api/status` for the header and by `projects.py` for the switcher). A model without that use has no upkeep.
- The switcher now counts as the header does: goals with status `off`, not `off` or `open` as before. It shows
  "N off, K unknown, model upkeep M" (unknown and upkeep counted only among the goals they belong to). Its row gets
  three new fields (`goals_off`, `goals_unknown`, `upkeep_off`); the existing `off` and `unknown` are kept unchanged,
  so the CLI's `ergostat projects` listing is untouched (outside this gap).
- The header's upkeep part is its own span (`#upkeep`, the muted runstate colour) after `#running`, so it is never red;
  the header reads "Running" when nothing is off, and "0 goals off · model upkeep 2" (", not running" when stopped).
- The acceptance runs on two copies of examples/first-loop that share one home, each served on a free port rather than
  :8796, with the two modelling goals' stocks read off and inbox-short holding:
  tests/test_items_page.py::test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart.
  Seen to fail under three breaks: the header not excluding upkeep ("2 goals off"), the switcher counting the old `off`
  ("2 off" against the header's 0), and the header turned red for upkeep alone.
Run: that test file whole (22 passed, rc 0, under the watchdog), tests/test_projects_listing.py,
tests/test_graph_cli_web.py, tests/test_resilience.py (73 passed), ruff clean. Main merged (already up to date). The unit
suite and the other three browser files were not run here (left to the factory and the merge queue).
