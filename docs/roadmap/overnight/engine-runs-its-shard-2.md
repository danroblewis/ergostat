# engine-runs-its-shard-2: each owner ask in the record is followed only by the engine whose shard owns what it names, and only the lead shard does the once-only duties
depends-on: [engine-runs-its-shard-1]

## Definition of done
- This builds on `Engine(project, shard=NAME)` and `Engine.own` from `engine-runs-its-shard-1`. That work must be on `main` before this branch starts. This clone's `main` (0216e0e5) does not have it yet. The branch must not carry shard-1's commits itself (lesson-7).
- With `shard=None` nothing changes: the existing unit suite passes and no existing test is edited. With `most=1`, the lead engine follows every ask and does every duty, the same as `shard=None`.
- **Owner asks.** In `_follow`, each ask is acted on by exactly one engine of a plan: the one whose shard `Plan.of` gives for what the ask names. No second rule decides this.
  - `block.approved`, `block.denied`, `trigger.reset` and `block.stop.requested` belong to `block.NAME`.
  - `daemon.restart.requested` belongs to `daemon.NAME`.
  - `steptest.approved` belongs to `goal.NAME`. `steptest.resume` at start resumes only this shard's goals.
  - `ergostat.action.approved` belongs to the shard of the block whose run asked for the action (its record's `block`).
- **Nothing is dropped, nothing is doubled.** When an ask names something the current model does not have (a removed block, an unknown daemon, an action with no block), the lead acts on it, as `shard=None` does today. The other engines ignore it. One exception: a stop for a removed block whose run is still held in a non-lead engine's `procs` is stopped by that engine.
- **Which model decides.** Each ask is judged against one model, read once for that event. After a `swap` moves a part to another shard, the next ask about it is followed by the new owner only.
- **Guard at start.** A shard engine never starts a run of a block outside its shard. `start` refuses one, says so, and returns False.
- **Once-only duties.** These run only in the lead shard engine, and still run with `shard=None`: the `ergostat.started` event, `history.note` (at start and on swap), `_sweep` (the messages sweep, the workspace-lease sweep, the actions sweep, notify delivery), the roll-up prune (`Runner._prune`) and the transcript ingester. The watchdog and the calls socket stay per engine. One socket per shard process belongs to `shard-supervisor`.
- **Docs.** SPEC §9.8's "Not yet by shard" sentence is rewritten to match. It keeps only what is still not done: wires, a moving flow's sensors read wherever they are, and one socket per state directory. GAPS "Left:" is updated.

## Relation to other work
- gap/engine-runs-its-shard-1: waits for it on main; this is its declared second half.
- gap/shard-supervisor: avoids its files (`runner.py`, `load.py`, `shard_supervisor.py`). Running shards as processes and one socket per shard are left to it.
- gap/shards-measured: comes after shard-supervisor; no overlap.
- gap/rs-adopt, gap/external-event-logs-continued: also edit `ergostat/spec/engine.py`. Merge origin/main before review.
- gap/upkeep-record-loops: changes `_prune`/roll-up in `runner.py`. This gap only gates where the engine starts it.

## Files to touch
- `ergostat/spec/engine.py`
- `ergostat/control/steptest.py`
- `tests/test_engine_shard_asks.py` (new)
- `docs/SPEC.md`
- `docs/GAPS.md`

## Risks
- lesson-3: an ask whose name `Plan.of` cannot place (`KeyError`) gets treated as no one's (dropped) or as everyone's (run in every shard). It must go to the lead alone.
- lesson-1: `_follow` reads `self.spec` for ownership, then `swap` replaces it before the act. Ownership and the act must use the same model.
- lesson-8: SPEC claims "followed by one engine" for some ask types while another type (actions, step tests, stops of removed blocks) still runs in every engine.

## Acceptance tests
- `tests/test_engine_shard_asks.py::test_block_asks_followed_by_owner_only`: two shard engines read the same record. An approval, a denial, a breaker reset and a stop for a block in each shard act (monkeypatched `start`/`triggers`/`stop_run`) only in that block's engine.
- `tests/test_engine_shard_asks.py::test_restart_and_steptest_by_owner_only`: a daemon restart and a step-test approval are acted on only by the shard that owns the daemon or goal. `steptest.resume` resumes only that shard's goals.
- `tests/test_engine_shard_asks.py::test_action_run_by_asking_blocks_shard`: an approved program action runs once, in its block's shard. One whose block is gone runs in the lead only.
- `tests/test_engine_shard_asks.py::test_unplaced_ask_goes_to_lead_once`: a stop for a removed block, a restart for an unknown daemon and an approval for an unknown block are each acted on by exactly one engine, the lead. A removed block's run held in shard B's `procs` is stopped by B.
- `tests/test_engine_shard_asks.py::test_ask_after_swap_goes_to_new_owner`: the test asserts that `Plan.of` moved for the block, then shows the next approval is followed by the new shard only. A `swap` monkeypatched in between reading the event and acting does not split the decision.
- `tests/test_engine_shard_asks.py::test_start_refuses_other_shards_block`: `start` of a block outside the shard returns False and records no run.
- `tests/test_engine_shard_asks.py::test_once_duties_only_in_lead`: with the sweeps, `history.note`, `_prune` and the ingester monkeypatched to count, the engines of a plan do each exactly once between them, all in the lead, and write one `ergostat.started`. A `shard=None` engine does each once.
- `tests/test_engine_shard_asks.py::test_one_shard_follows_like_whole`: with `most=1`, the lead engine acts on every ask type the same as `shard=None`.

## Size budget
110 net lines
size: M (confidence: medium)
