# switch-without-draining: a version switch leaves running agents alone

depends-on: [engine-adopts-runs-from-their-journals]

Problem. `dev/bin/live.py switch` drains: it waits for runs to end or stops them, which delays every upgrade and throws away agents' work.

Change.
- Turn on `[runs] outlive_engine` for the factory.
- A switch stops the engine, swaps the version and starts it; runs under way carry on under the version they started with and are adopted by the new engine. Remove the drain wait, `drain_minutes` and `quiet_runs` where nothing needs them any more.
- A journal or run record written by the previous version must be readable by the next: state the format's version in the journal and refuse, visibly, one it cannot read.
- A switch that is reverted adopts runs the same way.

Definition of done.
1. A test switch with runs under way: none is stopped, none loses an attempt, all finish and are recorded.
2. A reverted switch: the same.
3. A journal of an unknown format version is refused and named, and its run's lease is released uncounted.
4. The upgrade documentation says what a switch does to running work.

Files: dev/bin/live.py, dev/bin/drain.py, tests for them, docs/SPEC.md.

## Where it stopped

Built, round 1. 34 net lines outside tests, docs and dev (budget 600): `ergostat/spec/runrecord.py`,
`ergostat/spec/adopt.py`, `ergostat.yaml`. Each done item has a test:
1 `tests/test_switch_without_draining.py::test_a_switch_with_runs_under_way_stops_none_and_each_finishes_and_is_recorded`:
two versions in `live/`, each the real engine on a small model with `runs: outlive_engine`, three runs under way
at a real `live.py switch`. It checks that each run's process lives through the switch, that no lease ends and no
`agent.ran` is written during it, and that the upgrade is `healthy`. Then each run finishes: one start, one
`agent.ran` (`taken_up: true`, exit 0), its line after the switch still from version a's code, its lease acked once,
attempts 0, and no `run.refused`.
2 `test_a_reverted_switch_with_runs_under_way_stops_none_and_each_finishes_and_is_recorded`: the same, the new version
started (its engine takes the runs up) but unhealthy (no sensor), so it is reverted and the old version's engine
takes them up again. Same checks, the upgrade `reverted`.
3 `tests/test_runs_adopted.py::test_a_journal_of_an_unknown_format_is_refused_named_and_its_lease_released_uncounted`:
a record stating `journal: 2` is not taken up and none of its lines are read. `run.refused` names the run, its journal and the
format, once over two starts, and the engine's log says it. The lease is nacked with `count: false` (attempts 0, the
item `ready`), and the keeper stops the run. Also `test_a_run_record_that_states_no_format_is_read_as_the_first`: a record
written by the version before (no `journal`) is taken up and ended as ever.
4 `dev/README.md`, *Upgrade and revert*: "What a switch does to running work: nothing", with its limits. The factory's
upgrade documentation is there, not in `docs/`. SPEC section 9.1 (*Runs taken up again*) states the format and the
refusal.
`test_the_factory_keeps_its_runs_going_past_its_engine` pins `runs: outlive_engine: true` in the factory's model.

Seen to fail with the code they guard broken: done 1 and 2 with `live.py stop` passing `--runs` (the runs stopped at
the switch); done 3 with the format check off (the run taken up), with the nack counted (`count` missing), and with
the keeper's stop file not written (the run never stopped).

What changed besides the switch:
- The switcher (`dev/bin/drain.py`, the name kept: the model's block and action run it) starts an approved switch in
  the step that sees the approval (`upgrade.switch-begun`, flag `run/switch.json`). Gone: the quiet-moment wait,
  the daily window, the drain flag `run/drain.json` and the give-back. Also gone: `[upgrade] quiet_runs`, `daily_at`
  and `drain_minutes` (the whole `[upgrade]` table in `dev/factory.toml`), the `drain.py minutes|overrun` sensors,
  the stock `upgrades-draining`, the flow `drains-begun`, the goal `drains-within-bound` and the parameters
  `quiet-wait` and `drain-time`. `upgrades-switched` now flows from `upgrades-approved` (parameter `switch-time`).
  The switcher reads `goal.upgrades-switched-to` as its `in:`, and kept the withdrawal rules and the failed-switch
  rule.
- `fac.drain_holds` and `fac.draining` held AI runs during a drain and while the AI was held. They are now
  `fac.ai_holds` and `fac.ai_held` (the AI hold alone), with their seven callers renamed.
- `live.py` touches the version it switches from (and, on a revert, the one reverted), so `cleanup.py` keeps that
  version's folder `session_keep_hours` past its last run. Without that, a version neither current nor previous
  could be removed while a run started under it still uses its `$ERGOSTAT_CMD`.
- The test of the drain's nacks (`test_ai_limit_hold.py`) and the drain tests in `test_factory.py` are replaced by
  tests of the switch at once, the wait for approval only, the failed switch, the withdrawals, and an upgrade left
  `draining` by the switcher before this one.

Choices made with nobody to ask (each the more reversible one):
- "State the format's version in the journal": stated in the run's record (`runs/RUN.json`, `"journal": 1`). The
  engine writes the record as the run starts, beside the journal. The journal itself is the run's own standard
  output, byte for byte (SPEC 9.1), so a header line in it would change what both engines read. A record with no
  `journal` is format 1, so runs started by the version before this one are still taken up.
- A refused run is stopped (its keeper's stop file), not left going. Its lease is released, so its item is taken
  again, and a run still going would work beside the new one with a fence the record refuses. Its files are left
  for a person to read. It is refused again (said, not recorded twice) at each start until they are removed.
- The record's `upgrade.draining`/`upgrade.drained` events and the `draining` state stay in `ergostat.yaml`, so the
  record the switcher before this one wrote still folds. An upgrade it left `draining` is read like one approved:
  failed if its switch began (`drained_at`) with no outcome, else switched.
- The first switch onto this version is still run by the previous version's switcher, which drains as before.

Known limits, said in dev/README.md: a run keeps its process, its `$ERGOSTAT_CMD` and what it has loaded. A module
it imports late, or a `dev/bin` script it starts after the switch, comes from the instance's `dev/`, which the switch
replaces with the new version's. Making the instance's `dev/` per version would change how ergostat keys the model's
folder, which is outside this gap.

Not run here: the unit suite and the four browser files (the factory runs them); `ergostat check` on the root model
was refused as a command, so `test_check_on_the_root_model_reports_no_errors` stands in for it (passes). Run one
file at a time, all pass: test_switch_without_draining.py (3), test_runs_adopted.py (23), test_runs_outlive_engine.py
(11), test_ai_limit_hold.py (5), test_factory_resources.py (12), test_milestones.py::test_the_milestone_model_raises_no_check_finding,
test_code_health_measures.py::test_check_on_the_root_model_reports_no_errors, and test_factory.py (RESULT). ruff is
clean. Local `main` has nothing the branch lacks.
