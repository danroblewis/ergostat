# ui-a-system-alone-at-its-level-opens-whatever-model: A system alone at its level opens, whatever modelling does

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q15 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram top level (the-job)

**The problem:** The-job's README says the page opens with 'job' open; it opens as two closed boxes because modelling counts as a sibling. The stock-and-flow diagram is three levels down.

**The change:** When the level holds one system besides modelling, start with that system open.

**User stories it serves:** A1, H2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8792/ at first load the 'job' system is open (its ten domains are drawn as boxes) and modelling is closed; a stock of 'incidents' is reachable in at most two clicks.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built.

- **The change** is in `ergostat/fold.py` `default_open` (2 net lines of code and a docstring line), not under
  `ergostat/web/` as "Files to touch" guessed. The server decides which systems a first load opens, and the page asks
  it with no `open=`. Changing the rule where it is kept was the smallest and most reversible choice (no page script
  overriding the server). A `once` library template's system (`use: modelling`, as other modules already tell it
  apart: `(spec.uses.get(s) or {}).get("once")`) no longer counts beside another system at its level. A level whose only
  system is modelling still opens it, as before (plain-crontab, backups and the rest). Blocks uses the same rule, so
  its first view opens `job` too. No page, panel or view was added.
- **Other examples it changes:** deps, docs-fresh, roadmap and small-requests have the same shape (one system plus
  modelling), so their first view now draws that system open too. In `tests/fixtures/diagram_sizes.json`, each one's
  `""` record (240x232, two boxes) is set to its existing `open=<system>` record, the same drawing. In
  `tests/fixtures/layout_known.json`, the `satellite-far` ceilings rise for deps (9 to 10), docs-fresh (9 to 10) and
  roadmap (13 to 15). The added instances are that same open-system drawing counted again under the default view, not
  a new layout fault: with the fix taken out, the old ceilings hold.
- **Tests:** `tests/test_diagram_rendering.py::test_a_system_alone_at_its_level_beside_modelling_opens_at_first_load`
  is the acceptance check. It loads the-job at `/` and checks that exactly the ten domains and modelling are drawn as
  boxes and that `S.graph.open == ["job"]`. One click on incidents' Open then draws a stock of incidents.
  `tests/test_spec_systems.py::test_modelling_is_not_counted_beside_a_system_alone_at_its_level` covers the-job's
  `{"job"}` and plain-crontab's `{"modelling"}`. Breaks seen to fail: going back to the old rule (counting modelling)
  fails both tests; dropping the "modelling alone still opens" fallback fails the unit test.
- **Runs:** `tests/test_spec_systems.py` 8 passed. Ruff is clean. The whole of `tests/test_diagram_rendering.py`, run
  serially under the watchdog: 196 passed, 5 failed, none skipped. Each failure was rerun:
  - `test_every_view_draws_cleanly_and_in_time[coordinator]` and `[image-squeeze]`: routing `open=*` took 25-42 s
    against a 20 s bound. They fail the same way with the fix taken out, and `open=*` does not use the default.
  - `test_a_big_tangled_model_lays_out_in_time_and_cleanly`: `open=*` first draw took 2.8-4.1 s against 2.5 s, on a
    generated model. It also fails with the fix taken out.
  - `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`: 'Nothing waiting.' missing on
    /model. It fails the same way with the fix taken out, so it is on main.
  - One `BLOCKS_DOM` check (48 `... outside frame:delivery` entries, software-factory's blocks) could not be named
    from the run's output. Rerun alone, every test that uses BLOCKS_DOM passed, including software-factory's and the
    changed examples' Blocks views. It did not reproduce (lesson-10: not found, and not dismissed).
  - Not run here: the unit suite, the other three browser files, demo_check. There is no `origin/main` in this clone,
    and local `main` is the branch's base, so there was nothing to merge.
