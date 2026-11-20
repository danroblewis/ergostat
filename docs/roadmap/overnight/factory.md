# factory: ergostat on ergostat, the factory that develops ergostat itself

Branch `factory`, from origin/main (8ff0f12). The owner, 2026-11-20: "I want ergostat to be the full factory... move
the work we are doing in this chat over to ergostat... I want it to be able to benefit from its own development...
regularly upgrade the version it's running, and have the ability to revert." What the coordinator (a Claude session)
has done by hand through the overnight runs (`docs/roadmap/overnight-2026-11-19.md`: definitions first, an implementor
per gap, a disagreeable reviewer, a merge queue behind the four suites, the kill rule) becomes a model at the root of
the repository, `ergostat.yaml`, with everything it needs under `dev/`. It replaces the observe-only `~/ergostat-dev`.

## Definition of done

**The model.** `ergostat.yaml` at the repository's root includes `dev/model/*.yaml`. Its items: `gap` (open, ready,
building, built, in-review, approved, queued, merged, or parked), `review` (a verdict of merge, fix or park, with its
blocking and non-blocking findings), `flake`, `intervention` (recorded by the coordinator with a reason) and `upgrade`
(available, installed, switched, healthy, or reverted). Gaps are read from `docs/GAPS.md` on main and from requests
submitted as events (`gap.requested`). Its blocks: the **implementor** (an `ai` block: a headless `claude -p` in the
gap's own worktree `~/ergostat-wt/<branch>`; the definition file committed first; its fast suites run; pool 2), the
**reviewer** (an `ai` block, a fresh session that is given the definition, the diff and the rules, never the
implementor's reasoning; it records a `review` item; on fix the gap goes back to the implementor with the findings;
the second failed gate parks the gap with where it stopped), the **merge queue** (a program, pool 1: what the
coordinator's `queue-fast.sh` does, under the same lock file, its path configurable; the push to origin main a gated
action), **flake triage** (a program: a queue failure re-run alone; passing alone, it is a `flake` and the branch is
retried), the **upgrader** (a program: the new main installed into `~/ergostat-live/<sha>`, the instance switched by a
gated action, health-checked, and reverted to the previous on failure; the instance never runs from `~/ergostat`),
and the **load interlock** (sensors of the running suites, their threads and memory, and a goal that holds the
suite-running blocks while the machine is busy). Each implementor and reviewer run records the context it was given
(files, guides, findings, brief size); briefs are assembled by a program from templates in `dev/prompts/`. `uses:
modelling` with `ai: true` on haiku. Measures and goals: cycle time per gap by phase, first-pass review yield, fix
rounds, queue wait and run time, suite durations against a time budget, flake rate, interventions, cost per merged
gap, and a **daily dollar cap** on the implementor and reviewer that fails closed, in one place.

**Shipped off.** The implementor takes nothing until the coordinator opens the intake (a reading of `intake-open`):
the factory starts no real work on its own. Nothing outward-facing but the gated push.

## Acceptance tests

- `ergostat check` on the root model reports no errors.
- `tests/test_factory.py`:
  - `test_the_factory_model_loads`: the root model loads with its kinds, blocks and goals;
  - `test_intake_reads_gaps_and_requests`: the intake collector on a fixture repository: GAPS entries found, a
    definition file makes a gap ready, a done entry is not taken in;
  - `test_load_sensor_counts_suites`, `test_budget_fails_closed`: the interlock's reading, and the cap refusing when
    the spend cannot be read or is over;
  - `test_dry_run_one_gap`: one fake gap through the implementor, the reviewer and the queue with stand-ins (no AI,
    no push) on a fixture repository: the definition committed first, a review recorded, merged into the fixture's
    main, the push asked for and not made;
  - `test_fix_then_park`: two failed gates park the gap with where it stopped;
  - `test_flake_retried`: a failure that passes alone is a flake, and the gap goes back to the queue.
- The unit and browser suites under `scripts/suite_watch.py`, rc 0.

## Size budget

600 net lines of ergostat-core changes (outside `tests/`, `docs/`, `dev/` and the model), which should be few or
none. `dev/` and `ergostat.yaml` are not counted.
