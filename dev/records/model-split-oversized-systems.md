# model-split-oversized-systems: landing, times and intake become smaller systems

The modelling loop asked (four requests) because these systems are too large to redesign in one pass:
- `landing` has 45 parts in 3 clusters joined by 2 links: the merge queue and gaps, upgrade draining, and upgrade availability with the upgrader.
- `times` has more than 40 parts and no subsystems.
- `intake` has 2 clusters joined by 1 link, 131 times apart in time scale: open-gap dependencies, and join/split handling.

Change. In `dev/model/`, split each into named subsystems along those clusters. Change no equation, setpoint, limit or behavior: only which system a part belongs to. Every part keeps its id or is renamed with its references updated.

Definition of done.
1. `ergostat check` passes on the factory's model, with the same parts, flows and goals as before (a test compares them).
2. No system has more than 40 parts.
3. The Dynamics and Blocks diagrams render with the new systems (tests/test_diagram_rendering.py).

## Where it stopped

Built, round 1. Entry: the factory's `landing` is now `merging` (31 parts: the merge queue, the gaps waiting for it,
flake triage, the push, main-mend and browser-daily), `upgrading` (7: main-watch, the upgrader) and `switching` (12:
the coordinator's approval, the switcher and the switch); `times` is `state-times` (34), `loop-times` (11: the loop's
span and rounds, and the implementor's, fast suites' and review gates that run in it) and `gate-times` (8: the queue's
gates), with the timer left in `times`; `intake` is `open-gaps` (19) and `split-and-join` (10). Each part kept its id;
only its `system:` changed (parameters moved with the flows that use them). Net lines outside tests, docs and dev: 0.

What was decided alone (each a one-line change back):
- Item 2 is read as a system's parts of its own (`system:` directly on them), as the redesign's units take a system
  of more than 40 a subsystem at a time; counted at any depth, landing still holds 50 (and factory holds all). Now no
  system holds more than 34 of its own, none is too large to redesign, and landing, intake and times hold 0, 0 and 1.
- `times` had no clusters named: it is split by what the parts measure (states, the build-review loop, the queue's
  gates), loop-times taking the three gates driven by loop-rounds, so that no two subsystems are more linked to each
  other than inside (systems-merge stays silent).
- main-mend, flakes-main-broken and flakes-mended (in no cluster) went to `merging`, beside the queue they mend for.
- landing.yaml keeps `defaults: system: landing`, each part naming its subsystem, so the `batch` item kind and the
  `landing.merge-pipeline` dashboard keep their names; backlog.yaml's default became `open-gaps` (it has neither).
- In times.yaml the goals' `system:` is written last on each line: the pipeline watch (`watch.TIME_GOAL`) and
  `times.py setpoints` read a goal's line from its start, and with it first the watch read no time goal
  (test_factory.py::test_the_time_goals_have_no_check_findings checks this).

What check says differently (tests/test_factory_split_systems.py pins it): `system-splits` on landing and intake and
`time-scales` on intake are gone; new are three notes of the new subsystems, `time-scales@system.switching` (the 2 h
approval against the 2 min switch), `time-scales@system.split-and-join` and `purpose@system.split-and-join` (its
blocks act for no goal in it). The intake request's "131 times apart" is gaps-split (65 h) against gaps-joined
(0.5 h), both in the join/split cluster, so splitting along the clusters moves that note into split-and-join rather
than removing it. Making it go would need a goal or a further split, which this gap does not ask for.

Tests: tests/test_factory_split_systems.py (the model compared with the split undone, field by field and by
version; where each part went, pinned; check passes; no system over 40 parts of its own) and, in
tests/test_diagram_rendering.py, test_the_factorys_split_systems_are_drawn_in_dynamics_and_blocks (each parent's view:
Dynamics frames each subsystem with its parts; Blocks draws each as a block closed and a frame open). In Blocks
`gate-times` (no block) and `split-and-join` (split-watch and join-judge, in no goal's loop) are drawn as nothing,
the same as before the split (seen on the unsplit model), and the test says so. Tests that named the old system
of a moved part (test_factory.py, test_factory_join.py, test_factory_knowledge.py, test_landing_goal.py) now name
the subsystem and check it is inside the old one.

Seen to fail: moving the upgrader into gate-times failed the pin test and the check test (the comparison with the
split undone does not see it: it is built by the same mapping, which is why the pins exist); moving
upgrades-switching into upgrading failed the diagram test. A one-off scratch test (not committed) found main's
dev/model files equal to the split undone, comments and the explicit `system: landing`/`system: times` aside, and
ergostat.yaml unchanged.

Not run here: the whole of test_factory.py (a serial run was stopped by the session's 10-minute limit after about 20
tests; its 18 tests that read the factory's model were run and pass), the rest of test_diagram_rendering.py and the
other browser files, the unit suite. Fails here, unrelated: tests/test_queue_batch_item.py::
test_the_items_page_draws_the_batch_and_one_timeline_bar_per_run (the page never lists the batch in 60 s, twice). Its
model is landing.yaml's `items:` slice alone, which a scratch test found identical to main's, and the branch changes
no ergostat code; it was not run on main here.
