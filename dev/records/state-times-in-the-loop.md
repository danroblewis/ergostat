# state-times-in-the-loop: the time-in-state goals are read by something that acts

depends-on: [manager-sessions]

Audit 2026-11-21: `state-times` (merged) added goals and auxiliaries that `ergostat check` reports as unfinished: 47 `missing-feedback` (no block reads the goal), 45 `auxiliary-without-causes`, 45 `collector-undescribed`. That is 137 of the 168 open modelling requests, and they bury the real ones. The owner wants these times as setpoints, so keep them and close the loops.

## Definition of done
- Each time-in-state goal in `dev/model/times.yaml` is read by a block that acts when it is off. The pipeline manager's trigger is the expected reader: a time goal off past its tolerance is part of what its next session sees.
- Goals nothing should act on become plain measures. Say which and why in the file's header. Prefer fewer goals: median and p90 for every state is not needed where one would drive the same action.
- Each auxiliary names its causes and each collector has a description.
- `ergostat check` reports none of the three findings for `times.yaml`.

## Files to touch
`dev/model/times.yaml`, `dev/model/manager.yaml`, `dev/bin/watch.py`, `tests/test_factory.py`.

## Risks
- lesson-3: a time that cannot be read is unknown, never on target.

## Acceptance tests
- `tests/test_factory.py::test_the_time_goals_have_no_check_findings`
- `tests/test_factory.py::test_a_time_goal_off_reaches_the_managers_session`

## Size budget
100 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built (round 1); nothing in the definition is left. Choices made alone (the most reversible, each a line of YAML or
code to undo):

- Twelve goals stay, all medians, each read by `pipeline-watch` (`in:` in manager.yaml): ready, fix, built, approved,
  queued, replan, planned, leased, building, in-review, queue-failed, and loop-short. The other 34 became plain
  measures (every p90, in-open-hours, in-split-hours, in-dead-hours, loop-rounds and the seven gates); the header of
  times.yaml says why for each. Their auxiliaries and sensors are kept, so a goal can be put back with one line.
- Each goal's auxiliary is driven by its stock (or the running suites, for leased) and by `-flow.situations-handled`:
  the manager's handled sessions are what moves it, and the acceptance test holds each loop to close through that flow
  (without it ready-short closed only by an accidental path through ai-spend and the implementor).
  gate-push-wait-minutes is `exogenous: true` (the coordinator's approval of the push).
- The watch reads the goals from times.yaml itself (`watch.TIME_GOAL`) and computes each reading from the gaps it has
  already read (times.values / times.reading, measure.WINDOW). It does not use the engine's goal state. A goal off by
  more than its tolerance is a trigger (`time`, subject `goal.NAME`), and its fingerprint includes how many whole
  tolerances it is off, so after an answer it is raised again only if the reading moves by at least one tolerance.
  Each goal's reading goes on the situation as `times`. An unknown reading (no gap in the window, an unreadable time_in,
  a non-finite value) is None there: never on target, and not a trigger either, since an empty window is not a fault
  (the stuck trigger covers a gap waiting now). A goal line the watch's pattern cannot parse, or no goal at all, is a
  trigger.
- Not changed, noted for its own gap: `times.reading` (and so the measures' own sensors, which the engine reads) still
  gives 0 for an empty window, as state-times shipped it (tests/test_factory_times.py asserts it). The watch never
  relies on it.
- Touched beyond the listed files: `tests/test_factory_times.py` (it asserted a goal on every median and p90; now every
  goal is on a median) and `dev/README.md` (*Time in each state*).
- Not run here: `ergostat check` itself (the shell refused `uv run ergostat check`). The acceptance test reads the
  model with the reader check runs (`read(..., extremes=False)`), and that reader produces all three findings. On the
  unchanged branch it found 138 of them in times.yaml; now it finds none. The clone has no `origin/main`; local
  `main` has no commit the branch lacks.

### The check findings sent back (round 1, after the build)

`ergostat check` found five architecture notes on the branch that main lacks: `interface` for managing and times
(12 goals read by pipeline-watch across the boundary: 14 and 12 information links), `systems-merge` for times (24
links to managing against 24 inside) and load (12 links from suites-running against 5 inside), and `system-splits`
for times (the p90s and the gates a second cluster). The model was changed so each goes; none is allowed by the
definition (it has no `allows-findings` line, and it was not edited). This supersedes the goal list above:

- Seven goals now, not twelve: ready, queued, replan, planned, leased, queue-failed and loop-short. fix, built,
  building and in-review became plain measures (loop-short holds the build-review loop they add up to; the manager's
  act is the same), and approved (merge-pipeline-flowing already raises approved gaps waiting with no merge). The
  header says so. Reversible: a goal line and its `in:` entry put back.
- Each p90 is driven by its own median, not by the stock outside (it moves with it); only in-queued-hours and
  in-leased-hours read suites-running; the queue's unit, browser and demo gates are `exogenous: true` (their length
  is their tests', which nothing in the model sets), and the fast gate is driven by loop-rounds alone.
- `test_the_time_goals_have_no_check_findings` now also runs check's own architecture findings and holds none of
  them on system.times, system.managing or system.load (time-scales aside, which this branch did not raise). It failed
  with exactly the five before the model change and passes after. `test_a_time_goal_off_reaches_the_managers_session`
  reads queued-short on target and planned-short unknown in place of fix and built; test_factory_times.py's
  setpoints check keeps in-queued-hours' hold in place of in-fix-hours'.
- Not run: `uv run ergostat check` itself (refused by the shell, as before); the test calls the same
  `architecture.findings` check runs. The other architecture notes it prints (intake, landing, building, oversight,
  knowledge) do not touch times.yaml's links and were not among the ones sent back.

### Round 2: the review's findings, each answered

- Blocking (watch.py time_goals, lesson-3): a reading that fails is now a trigger (`time`, subject `goal.NAME`, why
  "goal NAME cannot be read: AUX: ERROR", fingerprint the error) with None on the situation. "Fails" means
  times.values raising (a malformed time_in such as a string `hours` or a missing `left`; a name it refuses, which
  is SystemExit), any one value not finite, or an auxiliary that is not one of `times.measures()`. That last case
  was found while writing the test: `in-nowhere-hours` fits values()' pattern and reads as an empty window, so it
  would have stayed silent. An empty window is still a silent unknown (None, no trigger). Tested in
  `test_a_time_goal_off_reaches_the_managers_session`: a string `hours`, a missing `left`, one NaN beside a good
  goal, `in-nowhere-hours`, and `nowhere`. With the old reading put back, the test failed at the malformed time_in
  (KeyError: no `goal.ready-short` trigger). With only the measures() check removed, it failed at `in-nowhere-hours`.
- Minor (NaN in the median): each value is checked before the median (the NaN case above), not only the result.
- Wording (lesson-8): the watch's docstring, time_goals' docstring and dev/README.md (*Time in each state*) now say
  that an empty window's None is on the situation and raises nothing, and that a reading that fails is a trigger.
- Outside the listed files (tests/test_factory_times.py, dev/README.md): kept. Both follow from the change, as the
  review said. This round touches dev/README.md again, for the wording above.
- Refused by the shell this round: `cp dev/bin/watch.py /tmp/watch.fixed.py && git show HEAD:dev/bin/watch.py >
  dev/bin/watch.py && ...` and `git checkout -- dev/bin/watch.py`. The revert and restore for the fail check were
  done with the editor instead, and the tree matched the commit afterwards (`git status` clean).
- Run: both acceptance tests, tests/test_factory_manager.py (33) and tests/test_factory_times.py (7) all pass.
  `uv run ruff check ergostat tests scripts` is clean. Not run: the unit suite and the browser files (the merge
  queue's job), and `ergostat check` itself. `ruff check dev/bin` reports B023 in plan.py and E501 in review.py,
  files this branch does not touch. The clone has no `origin/main`; local `main` has no commit the branch lacks.

### Round 3: the review's findings, each answered

- Blocking (watch.py time_goals, lesson-5 / lesson-3): each time trigger's fingerprint now also holds when its
  episode began: since when the goal has been off (`NAME/off`) or unreadable (`NAME/unreadable`) without a break.
  The starts are kept in `run/manager.json` under `episodes`, read, decided and written with `manager.lock` held
  across all three (`watch.kept`, which `broken()` now uses too for its `since`; each keeps the other's part). A
  goal on target, unknown or read again with no error ends its episode, so when it next goes off or becomes
  unreadable it begins again with a new start and a new fingerprint, even at the same reading or with the same
  error. The episodes are brought up to date on every state_now: the `watch.py broken` sensor's pass as well as the
  block's, so a flip while a session is under way is still seen at the sensor's interval. The fingerprint keeps the
  tolerance step (off) and the error text (unreadable), so a worse reading or another error is raised within one
  episode as before. Tested in `test_a_time_goal_off_reaches_the_managers_session`: answered, the same reading is not
  raised again; then on target, then off again by as much: raised with a new fingerprint; then unreadable, answered,
  on target, then unreadable with the same error: raised again. With the episode start replaced by a constant, the
  test failed at the off-again step (no trigger); with only the unreadable one replaced, it failed at the
  unreadable-again step.
- Wording (times.yaml header): it now says that an empty window is None on the situation and raises nothing, and that
  one that cannot be read is None and a trigger. Reflowed.
- Wording (dev/README.md, *Time in each state*): the paragraph is reflowed to the wrap width (no short line, no orphan
  "as a table"), and says when an answered time trigger is raised again.
- Refused by the shell this round: a `python3 - <<'EOF' ... EOF` script that would have made these edits to watch.py
  (done with the editor instead), and `grep -n ... dev/model/times.yaml ...; sed -n 598,625p dev/README.md | awk ...`
  (read with the reader instead).
- Run: both acceptance tests and tests/test_factory_manager.py (35 together), and tests/test_factory_times.py (7):
  all pass. `uv run ruff check ergostat tests scripts dev/bin/watch.py` is clean. Not run: the unit suite and the four
  browser files (the merge queue's job), and `ergostat check` itself. Local `main` has no commit the branch lacks;
  there is no `origin/main` in the clone.
