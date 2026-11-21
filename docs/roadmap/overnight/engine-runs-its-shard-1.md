# engine-runs-its-shard-1: `Engine(project, shard=NAME)` works only on its shard's blocks, goals, clock, item work, triggers, joins, daemons, observer and readings
depends-on: [shards-from-systems]

## Definition of done
- `Engine(project, say=print, shard=None)`. With `None` nothing changes: the existing unit suite passes and no existing test is edited.
- A shard name that is not in `shards.plan(spec)` raises `ValueError` when the engine is built. It never runs nothing quietly, and it never runs everything.
- With a shard, the engine keeps its plan and its `Shard`. Which shard a part belongs to is decided only by `Plan.of`; there is no second rule. The engine then works only on its own:
  - built-ins (`builtins`), machine blocks (`machines`) and the goals worked out in a pass (`goals`);
  - clock (`_plan`): timed sensors, sensor crons, timed and cron blocks, judges;
  - item work: `Dispatcher.blocks`, plus the kinds whose leases it watches (`Dispatcher.kinds`). These are the kinds `Plan.of("kind.X")` puts in this shard: the kinds a block takes go to that block's shard, and any other kind goes to its system's shard, else to the lead;
  - `Triggers` and `Joins`: only blocks and join kinds in this shard. `Supervisor.sync` starts only daemons used by this shard's blocks or sensors;
  - `Observer`: tracks and estimates only this shard's stocks;
  - `measure`: reads the newest values of its own stocks, flows and auxiliaries. It also reads measured parts in other shards that its parts read (a goal's `of`, a block's reads, an equation's refs, an observed stock's flows). It reads nothing else.
- Across the shards of one plan, each of the lists above is a partition of what the `shard=None` engine works on: disjoint, and together equal to it.
- `swap` works the plan out again from the new model under the same lock it holds now. A part that moved to another shard is no longer worked on here, and it leaves no state behind (built-in, status, setpoint, track, daemon slot). If the shard's name is gone from the new plan, `swap` refuses the change and the old model keeps running.
- Out of scope (this is `engine-runs-its-shard-2`): owner asks through the record (`_follow`), the lead shard's one-time duties, and wires. Until that gap lands, a shard engine still runs `_follow` as it does today. SPEC §9.8 says this, and nothing in the docs claims that shards run as processes.
- SPEC §9.8 and GAPS ("Left:") are updated to match.

## Relation to other work
- gap/engine-runs-its-shard-2: comes after this one; owner asks and the lead's once-only duties are left to it.
- gap/shard-wires: waits for this; wires carry the values this branch leaves unread across shards.
- gap/rs-adopt, gap/lease-kill-detached, gap/run-budget-trip: also edit `ergostat/spec/engine.py`/`dispatch.py`. The edits here are confined to filters, so merge origin/main before review.

## Files to touch
- `ergostat/spec/engine.py`
- `ergostat/spec/shards.py`
- `ergostat/leases/dispatch.py`
- `ergostat/spec/triggers.py`
- `ergostat/spec/joins.py`
- `ergostat/daemons/supervise.py`
- `ergostat/spec/observer.py`
- `tests/test_engine_shard.py` (new)
- `docs/SPEC.md`
- `docs/GAPS.md`

## Risks
- lesson-3: a part missing from the plan, or an unknown shard, is treated as "everyone's" or "no one's". `Plan.of` raises, and an unknown shard is refused.
- lesson-5: after `swap`, state for a part that moved shards (a built-in, a track, a daemon slot) survives here.
- lesson-8: the claim "each shard works on its own parts only" holds for some lists but not others, for example the dispatcher's kinds or the observer's stocks.
- lesson-1: `swap` replans outside `self.lock`, so a pass can run with the new spec and the old shard.

## Acceptance tests
- `tests/test_engine_shard.py::test_one_shard_lead_is_whole_engine`: with `most=1`, the lead shard engine's lists all equal the `shard=None` engine's.
- `tests/test_engine_shard.py::test_shards_partition_the_work`: on a model with two systems and a shared daemon or kind, each list (builtins, machines, goals, `_plan`'s parts, dispatcher blocks and kinds, observer stocks) is disjoint across shards, and together they equal the whole engine's.
- `tests/test_engine_shard.py::test_trigger_and_join_only_in_owning_shard`: one event that matches blocks in both shards starts a run only in the engine that owns each block, and a join moves its parent only in the join kind's shard.
- `tests/test_engine_shard.py::test_sync_starts_only_own_daemons`: with spawning monkeypatched, `Supervisor.sync` in shard A starts only A's daemons.
- `tests/test_engine_shard.py::test_measure_reads_own_and_read_parts`: shard A sets its own signals and the other-shard measured stock its goal reads. It sets no signal for B's other parts.
- `tests/test_engine_shard.py::test_swap_moves_part_out`: a block moved to another system by `swap` is no longer in this shard's builtins, machines or clock, and none of its signal or status remains.
- `tests/test_engine_shard.py::test_unknown_shard_refused`: `Engine(..., shard="nope")` raises `ValueError`, and a `swap` that removes the shard is refused with the old model still running.

## Size budget
180 net lines

## Notes from the plan review (answer each)

- ergostat/spec/shards.py:108-115 only merges systems on a daemon shared by blocks, but Supervisor.sync (ergostat/daemons/supervise.py:124-125) also starts daemons named by sensors (spec.sensors(), s.daemon). A daemon used by sensors in two systems, or by a sensor in A and a block in B, would be started by both shard engines. That breaks the 'partition' claim and spawns the same daemon twice. Plan.where also has no daemon key, so 'decided only by Plan.of' cannot cover daemons. Instead: in shards.plan, add sensor daemons to the 'daemon' merge (union the sensor's part seed with the daemon's block seeds), record a `daemon.NAME` key in `where`, and have Supervisor.sync filter by Plan.of(f'daemon.{n}'), along with its push/observers maps (supervise.py:145-146). Add the Supervisor's wanted set to test_shards_partition_the_work, using a daemon shared only by sensors in two systems, plus a test_shards.py case for the new merge.
- swap calls self.daemons.sync(new) after releasing self.lock (engine.py:1738). If the shard-filtered sync reads self.plan or self.shard there, a second swap could slip in between. Pass the plan worked out under the lock into sync as an argument instead of re-reading the engine's fields.
- Today swap clears state only for parts removed from the spec (signals for builtins, status/stale for goals, setpoint, outputs/commands). It does not clear parts that are still in the spec but moved to another shard: status, stale, setpoint, the observer track carried by Observer(carry=...), outputs/commands, and agent slots. Filter each of those by the new plan's shard, not by 'in new.goals/blocks'. test_swap_moves_part_out should also move a goal and an observed stock, not only a block.
- test_swap_moves_part_out moves a block 'to another system', but if both systems already share an agent, kind or daemon they sit in one shard and nothing moves. Assert plan.of(...) changed before checking that the state is gone.
- A 180 net-line budget for filters in seven source files, a new swap path, docs, and seven tests that each build a two-system model is tight. Use one small fixture model shared by all tests.
- rs-adopt and lease-kill-detached are building in engine.py and dispatch.py. Merge origin/main before review, as the plan says, and before writing the swap changes, since those gaps may touch the same lines.
