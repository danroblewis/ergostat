# Milestones: the kind and its lifecycle

The factory moves to development by milestones (the owner, 2026-11-22). A milestone is a group of gaps that is finished together.

## What done means

- A new item kind `milestone` in the factory's model, with the states `waiting`, `active` and `completed`. `completed` is final: no event moves a milestone out of it.
- A milestone may depend on other milestones (`depends_on: milestone`, a precedence relation). A gap names its milestone by a `milestone` relation declared with `group: true`, so the Items page's Graph can group by it. The existing free-text `milestone` field on gaps holds names of the 21 old labels; keep those values readable until the coordinator has moved them.
- A small block, `dev/bin/milestones.py`, runs every minute and applies these rules:
  - A `waiting` milestone becomes `active` when every milestone it depends on is `completed`, while fewer than 3 milestones are active. Past that limit the rest wait in rank order. The limit is read from `[milestones] active_max` (default 3).
  - An `active` milestone with at least one gap, all of them `merged` or `closed`, becomes `completed`. A `parked` gap keeps it open. An empty milestone never completes.
  - A milestone marked `upkeep: true` is for the factory's own repairs: it is always active and does not count toward the limit. It completes at the end of its cycle (`[milestones] upkeep_days`, default 7), its unfinished gaps move to a new upkeep milestone, and that one becomes active.
- `milestones.py` has the coordinator's commands: `add`, `depends`, `assign GAP MILESTONE`, `pull GAP`, `unpull GAP` and `status`. `assign` refuses a completed milestone. `depends` refuses a cycle.
- `status` prints each milestone with its state, what it waits on, and its gaps by state.

Do not change which gaps the implementor takes: that is `milestone-limits-what-is-built`. Do not add a page or panel.

## Tests

Each rule above: activation, the limit, completion, a parked gap holding it open, an empty one, no way out of `completed`, the upkeep cycle, and the refusals.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 17:03).

Stopped on its last attempt by RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 678, in session
    out = agents.session(cfg, role, brief, work, keep=kept)
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 204, in session
    egress(cfg)
    ~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 117, in egress
    _egress(cfg)
    ~~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 124, in _egress
    docker("network", "create", "--internal", NET)
    ~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 106, in docker
    raise RuntimeError(f"docker {args[0]}: {r.stderr.strip()[-300:]}")
RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 17:04).

Its runs failed past their attempts (a dead letter):
- attempt 1: ack
- attempt 2: nack exited 1
- attempt 3: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 4: nack the run ended with gap/milestone-kind-and-lifecycle still parked

## Where it stopped

Built (implementor, 2026-11-23), round 1 carried on from the parked branch. Nothing of the definition is left.

What is built: the kind `milestone` in ergostat.yaml (waiting, active, completed; `depends_on: milestone`, precedence;
`messages: done` counts completed), a gap's `milestone` relation (`group: true`, `inverse: gaps`),
dev/model/milestones.yaml (three stocks, three flows, the block `milestones`, every 1m), `[milestones] active_max` and
`upkeep_days` in dev/factory.toml, dev/bin/milestones.py (`pass`, `add`, `depends`, `assign`, `pull`, `unpull`,
`status`), the section *Milestones* in dev/README.md, and tests/test_milestones.py (25 tests).

Choices made alone, each the most reversible I saw:
- "completed is final" needed a way to say so in YAML. The item fold already honours `ItemKind.final` (the built-in
  action kind uses it), so the compiler now reads a kind's `final: [STATE, ...]` (ergostat/spec/compile.py; error code
  `bad-final`; SPEC §5a's key table and the schema say it). A move out of a final state is ignored and recorded in the
  item's `refused`. `final` also joins the item index's kinds key, so a model that adds it refolds once.
- The gap's `milestone` relation folds by `replace` (a fold relations allow), not the default set-union. The old
  free-text labels stay exactly as written (a string), a later label still replaces an earlier one as before, and
  `assign` replaces a label with the milestone's id, keeping the old value in `milestone_was`. `status` lists the labels
  not yet assigned. A label is a link to no item; nothing refuses or reports it.
- `pull GAP` / `unpull GAP` are not defined anywhere I could find. I built them as a mark only (`pulled: true` with
  `pulled_at`, cleared by unpull), shown in `status`. Nothing here acts on it, since what the implementor takes is
  `milestone-limits-what-is-built`'s work. That gap should read the mark, or redefine it.
- Limits: `active_max` 1-20, `upkeep_days` 1-90. Anything else (not a number, a bool, NaN, a fraction for active_max)
  refuses the run; nothing is clamped. A dependency that is no milestone keeps its dependent waiting.
- An upkeep milestone is activated whatever it depends on. Its cycle's end is `upkeep_ends`, written when the pass
  activates it (one activated by hand has it pinned once, from when it entered active). Its successor is
  `milestone/upkeep-<date>` (the first free name, then `-2`, ... up to 20), marked `follows`. A pass that stopped part
  way reuses the successor already made for it. The successor has no rank and no dependencies.
- `depends` also refuses a completed milestone (final) and a self-dependency. `add` refuses a name already used (an id
  is never made again) and checks for a cycle too (an existing milestone may already name the new one).
- Within one pass, completions come first, so a milestone whose last dependency completes is activated in the same pass.

Limits of the claims: the lock (run/milestones.lock) makes the pass and the commands wait for each other. Other blocks
move gaps' states without it, so a pass sees them as they were when it read them (a gap leaving merged or closed between
the read and the completion is not seen; the factory's flow never leaves either state). Grouping gaps under a
milestone makes it a summary in the Items page's critical path, as the definition asks. Suppose gap X (in milestone A)
depends on gap Y, and Y's milestone depends on A. Then the three form a cycle there, and precedence leaves such items
untaken. Only assignments the coordinator makes can do that.

Tests run here, one file at a time: tests/test_milestones.py (25 passed). Each rule was seen to fail with its code
broken: final removed from the compiler, the lock removed, `room > 0` removed, the empty-milestone guard removed with
parked counted as done, the cycle check removed, assign's completed check removed, the successor reuse removed, the
carrying of gaps removed. Also passing: tests/test_spec_schema.py, tests/test_spec_structure.py,
tests/test_item_index.py, tests/test_relations.py, tests/test_spec_items.py, tests/test_precedence.py,
tests/test_item_search_gaps.py, tests/test_interface_stability.py, test_factory.py's two model-loading tests and
test_factory_join.py's first. Not run here: the unit suite and the four browser files (the factory runs them). Ruff is
clean. main had no commits past this branch's base, so there was nothing to merge.

Size: 32 net lines outside tests/, docs/ and dev/ (ergostat.yaml 18, compile.py 6, itemindex.py 1, the schema 7), and
about 430 more in dev/ (milestones.py, its model file, the settings, the README section).

## Where it stopped

Answering `ergostat check`'s three new findings (implementor, 2026-11-23). The definition has no `allows-findings` line.
- `system-splits system.planning`: the milestone parts linked to nothing else in planning, so they were a loose cluster
  there. They are now a system of their own, `milestones`, within `factory` (dev/model/milestones.yaml). No part is in
  `factory` directly, so no loose cluster is left there. Making it a system raised a `purpose` note (its block acted for
  no goal inside it), answered by the goal `milestones-within-limit` (`milestones-active <= 4`: the default limit of
  3 and the upkeep one). The 4 is fixed in the model and does not follow `[milestones] active_max`.
- `no-equation` on both flows: `milestones-activated` is `MIN(waiting, MAX(active-max - active, 0)) / activate-time` and
  `milestones-completed` is `active / finish-time`. The parameters `active-max` (3, the setting's default),
  `activate-time` (1d, estimate) and `finish-time` (7d, estimate) are guesses, used only for projecting. The block does
  not read them.
- Pinned by tests/test_milestones.py::test_the_milestone_model_raises_no_check_finding. With one equation removed it
  fails on no-equation. Before the goal was added it failed on purpose.

## Where it stopped

Round 2 (implementor, 2026-11-23): the merge queue's two failures were this branch's own, and both are fixed.
- tests/test_library_trust.py::test_every_compile_key_classified: the new item key `final` was not classified in the
  library trust table. It is now allowed to a template, as a list (`L`) like `states` (ergostat/library/trust.py's
  `ITEM`). It only names states the kind already has, and it runs nothing. That made the file pass (48 passed);
  before, it failed with `['items.final'] == []`.
- tests/test_factory_sessions.py::test_a_kept_session_folds_into_its_conversation_by_cores_reader: the test builds a
  model from a fixed set of the root model's kinds. The gap kind's new `milestone` relation names a kind that was not
  in that set, so compiling it failed with "'milestone' is not a kind of item". `milestone` is now added to the
  test's set of kinds, as was done for the other kinds gap relates to. That made the file pass (5 passed). No other
  test copies only some of the root model's kinds.
- main has no commits past this branch's last merge (69ed1030), so there was nothing to merge.
- Run here: tests/test_library_trust.py, tests/test_factory_sessions.py, tests/test_milestones.py (all passed). Ruff is
  clean. Not run here: the unit suite and the four browser files.
