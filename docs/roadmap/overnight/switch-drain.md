# switch-drain: an approved switch drains the runs under way instead of killing them, and older switch requests are withdrawn

depends-on: []

Today `switch-instance` stops the engine at once (live.py switch), which kills every session under way (9 implementors
at a time now), so the coordinator holds switches for a quiet moment that never comes. And each green merge asks its own
switch: older ones stay waiting in the inbox after a newer version supersedes them.

## Definition of done

- **When it switches** (owner: "daily or something, or when load is low enough"): an approved, newest switch waits for
  a **quiet moment** - at most `[upgrade] quiet_runs` (default 1) AI runs under way - or, at the latest, the **daily
  window** (`[upgrade] daily_at`, default 04:00 local), whichever comes first; then it drains as below. The
  coordinator may approve switches standing (an approval policy for `switch-instance` of the newest version), so
  upgrades run without a person once the health check and revert have proven themselves.
- An approved switch first **drains**: the AI blocks take no new item (a drain flag the dispatch reads), the runs under
  way finish or reach a bound (`[upgrade] drain_minutes`, default 45), then the switch runs as today (health check,
  revert). Runs still going at the bound are stopped as today, and each is given back uncounted (not a failure of its gap).
- A switch asked for a version older than one waiting, or than the one running, is **withdrawn** from the inbox
  (its action closed, saying which version supersedes it); only the newest waits.
- The drain and the switch are drawn in the model (a drain state, its time measured with a goal) and shown by `status.py`.

## Acceptance tests

- `tests/test_factory.py::test_a_switch_waits_for_the_runs_under_way`
- `tests/test_factory.py::test_a_drain_past_its_bound_gives_the_runs_back_uncounted`
- `tests/test_factory.py::test_an_older_switch_request_is_withdrawn`
- `tests/test_factory.py::test_a_switch_waits_for_a_quiet_moment_or_the_daily_window`

## Size budget

200 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built in round 1; all four acceptance tests pass. Nobody was there to answer questions, so each choice below is the
one easiest to undo.

**What was built.** `dev/bin/drain.py` is the switcher, a program block that runs every minute. It does every step
under `run/switch.lock`:
- It reads the approval of `switch-instance` from the record. The upgrader now keeps the action's id on the upgrade
  as `switch_action`.
- It withdraws older requests: a held action is denied `--as switcher` with the note "withdrawn: superseded by ...",
  and the upgrade moves to `withdrawn`.
- It waits for a quiet moment or the daily window. Then it writes `run/drain.json`. While that file exists, every AI
  run gives its item back uncounted (`fac.drain_holds`, called first in implement, review, plan, plan review,
  research and the pipeline manager).
- At the bound it gives back each run still going with `ergostat lease --nack --no-count`, using that run's own
  item, fence and run id. Then it starts `live.py switch --detach`, which removes the flag whatever the outcome.

The action's command is now `drain.py approve SHA`, which does nothing: the approval only arms the switcher. A
standing approval means `gate: auto` on the action in the instance's model. The model gains:
- the states `approved`, `draining` and `withdrawn`;
- the stocks `upgrades-approved` and `upgrades-draining`;
- the flows `switches-approved`, `switches-withdrawn`, `drains-begun` and `upgrades-switched` (now from draining);
- the auxiliary `drain-minutes`, measured by `drain.py minutes`, with the goal `drains-within-bound`;
- the block `switcher`.

`status.py` prints a line on the switch.

**Choices to look at.**
- *A withdrawal is a denial by the switcher.* The inbox's ladder therefore counts it against the `switch` class, which
  holds back the "ready for gate: auto" suggestion. The other option was denying as `gate`, which would hide that a
  person was asked. A "withdrawn" answer in the gate itself would be a core change, outside this gap.
- *An approved action that is withdrawn has still run.* An approval cannot be undone, but its command does nothing,
  so it arms nothing.
- *ergostat's own modelling AI blocks are not drained.* These are `improver`, `modeller` and `redesigner`, from the
  modelling template. They cannot read the flag without a core change, so the switch's stop ends them as before. The
  test checks that `drain.AI` names every other `type: ai` block.
- *A drain flag that cannot be read counts as a drain under way* (fail closed). A switch started more than 30 minutes
  ago whose process never cleared the flag is given up, so a dead switch process cannot stop the factory for good.
- *"Newest" is decided by git ancestry, never by time.* If two waiting versions are not ancestors of each other
  (impossible on a main that only fast-forwards), nothing is switched, and the switcher says so.
- *The bounds are refused when set outside them, not clamped:* quiet_runs 0-10, drain_minutes 1-240, daily_at HH:MM.
- *The 46-minute hold of `drains-within-bound` repeats the default 45 by hand.* Changing `[upgrade] drain_minutes`
  means changing it too.

**Size: over budget.** This gap's code lives in `dev/` and the root model: about 250 net Python lines in `dev/bin/`
(`drain.py` is 214) plus about 70 lines of model YAML and TOML. That is over the 200 if dev/ counts. The factory's
own count (`fac.net_lines` excludes `dev/` and `ergostat.yaml`) is 0. Why it is over:
- withdrawal, the quiet-or-window wait, the drain, the uncounted give-back and the stale-switch guard each need a
  read-decide-write under the lock;
- the definition also asks for the model's drain state, the goal and `status.py`.
No core code changed.

**Not done or not run.**
- origin/main is not merged: this clone has no remote, and local `main` is already in the branch. The factory's
  queue merges it.
- The unit suite and the browser files were not run here, only `tests/test_factory.py` (45 passed, 2 Docker tests
  skipped) and the other factory files plus `test_local_settings.py` (56 passed). Ruff is clean.
- `ergostat check` on the root model was not run, because this session's shell refused it. The model loads with no
  errors (`test_the_factory_model_loads`), but warnings were not read.
- Lesson-9 checks, each run and then reverted. Every test failed with its code broken:
  - `give_back` doing nothing, and the daily window never passing: the bound test and the window test failed;
  - no withdrawal, and `drain_holds` always False: the withdrawal test and the runs-under-way test failed;
  - the drain ending at once with runs still under way: the runs-under-way test and the bound test failed.

## Where it stopped (after the factory's fast suites, round 1)

The factory's `unit` run failed three tests in `tests/test_leases.py`: `test_a_lease_held_by_a_run_survives_a_model_edit`,
`test_the_watchdog_renews_from_what_the_holder_does_elsewhere` and `test_leases_survive_a_restart_the_fold_is_the_truth`
(3 failed, 1932 passed, 69 skipped). No code was changed for them here, per lesson-13. These are the reasons:
- This branch does not touch the code they test. `git diff main -- ergostat/` is empty, so `ergostat/leases/` and
  `ergostat/runner.py` are main's. The tests build their own models in `tmp_path` and do not read `ergostat.yaml`,
  `dev/` or `run/drain.json`. Those are the only things this branch changes, apart from its own tests.
- This branch's tests start no engine and stop none. The one real `live.py switch` they call exits on "not installed"
  before `stop()`.
- The failures depend on timing under load. Each test has a lease TTL of 1-1.5 s and a CLI start-up per event. Two of
  them are already recorded as main's own flakes: the restart test in `main-broken.md` (the engine's shutdown race)
  and the watchdog test in `continue-branch2.md` (the TTL against a CLI's start-up).
- Run alone here, with nothing else running, they pass: the three named (3 passed), and all of `tests/test_leases.py`
  (20 passed in 36 s). A run under `-n` load to reproduce them was not allowed in this session.

Left: the factory's fast suites run again; the next step, if they fail again on these, is a gap of its own on
`ergostat/leases` (the watchdog's expiry and the engine's give-back on stop under load).

## Where it stopped (after the factory's fast suites, round 2)

The factory's second `unit` run shows one `F` on the third line of progress (about 10%). The tail it gave ends at 50%
with no summary, so it names no failed test. This session could not find which test it was, so **no code was
changed**. Fixing something here without a failure to point at would be a guess.

What was run here, one invocation at a time, all on the branch's code as of 8fcb4107:
- `tests/test_factory.py`: 45 passed, 2 skipped (Docker).
- `tests/test_factory_sessions.py`, `test_factory_resources.py`, `test_factory_manager.py`,
  `test_factory_knowledge.py` and `test_local_settings.py` together: 56 passed.
- `tests/test_leases.py`: 20 passed. This is where round 1's three failures were, all main's timing flakes.
- `test_coherence.py`, `test_spec_structure.py`, `test_daemon_docs.py`, `test_guide.py` and `test_architecture.py`:
  73 passed.
- To look for order or sys.modules effects between files: test_factory_resources, sessions, factory and manager in
  one process gave 76 passed, 2 skipped. `-n 4 --dist worksteal` over test_factory, resources, sessions and knowledge
  gave 80 passed, 2 skipped.
- The whole suite was not run here: this session refused it, serially and in parallel.

These are the only tests that read this branch's files: `dev/`, the root `ergostat.yaml` and `run/drain.json`. Each
one passes, alone and mixed. That makes the `F` most likely another of main's load flakes (lesson-10, lesson-13), as in
round 1, but that is not proven.

Left: the failing test's name, from the factory's full log or `suites_fast.tests` on the item. If it is in a file
listed above, it is this branch's to fix. If it is not, it is main's and needs its own gap.

## Where it stopped (round 2, second session)

This session's brief again names no failed test and no review finding, so **no code was changed**.

Checked again, on b8d25fb:
- A search of `tests/` finds no test outside the files listed above that reads `dev/`, the root `ergostat.yaml`,
  `dev/README.md` or `run/drain.json`. Every other test builds its model in `tmp_path` or reads `examples/`, which
  this branch does not touch.
- `tests/test_factory.py`: 45 passed, 2 skipped (Docker).
- `test_factory_knowledge.py`, `test_factory_manager.py`, `test_factory_resources.py`, `test_factory_sessions.py` and
  `test_daemon_docs.py` in one run: 82 passed.
- `uv run ruff check ergostat tests scripts`: clean.
- Not run: the whole unit suite and the browser files (this session's shell refused a loop over files, and the house
  rules leave the full suite to the factory), and the merge of origin/main (this clone has no remote).

Left: the same as above. The factory has to run the fast suites again and give the failing test's name.
