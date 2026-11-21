# a-block-s-pool-set-by-the-model: `pool: {now: stock.NAME, most: N}`, a block's pool read from a stock at each dispatch, capped by its most
depends-on: []

## Definition of done

1. **The model language.** A block that takes items may write `pool:` as a whole number (unchanged) or as
   `pool: {now: stock.NAME, most: N}`. In the second form, `most` is the hard ceiling. It is required and must be a
   whole number of 1 or more (a bool is refused). `now` must be a `stock.` reference to a stock of the model that has
   at least one sensor. Each mistake is a compile error with where it was written:
   - `most` missing or not a whole number of 1 or more: code `bad-number`.
   - `now` not a reference, or a reference to another kind: `bad-ref` or `wrong-kind`, through `Compiler.ref`.
   - a stock that does not exist: `unknown-ref`, with a suggestion.
   - a stock with no sensor: a new code `pool-unmeasured` ("nothing reads its level").
   - an unknown key in the mapping: `unknown-key`.

   The existing `pool-without-takes` check also fires for the mapping form on a block that takes nothing.
   In `ergostat/spec/ir.py`, `Block.pool` stays an `int` and is the most (the number, or `most`). A new field
   `pool_now: Ref | None` names the stock (None for the number form). Code that reads only `b.pool` still sees a
   correct ceiling.
2. **One function says what the pool is now:** `ergostat/leases/poolnow.py::now(b, value) -> int`. With no
   `pool_now`, it returns `b.pool`. Otherwise it maps `value` (the stock's level) to `floor(value)` clamped to
   `[0, b.pool]`. A `None`, NaN, infinite or non-numeric value gives 0. The same module has
   `read_at(p, spec, b, at) -> float | None`: the stock's newest reading at or before `at`, over all its sensors'
   series, as `engine.measure` picks it (`p.measurements.latest(series, before=at)`).
3. **Dispatch reads the pool now at every tick.** In `leases/dispatch.py::tick`,
   `room = poolnow.now(b, self.e.get(b.pool_now)) - in flight`. The read happens inside the same `with self.lock:`
   that counts the leases held and takes the new ones, after `items_of`.
   - A raised stock starts more runs at the next tick, with no model reload.
   - A lowered stock drains: no new lease until fewer than the pool now are held. Nothing running is stopped,
     exactly as a lowered `pool:` number behaves (SPEC §9.5).
   - A stock with no reading (or a non-numeric one) gives a pool of 0. No new lease is taken, and the engine says
     once per block, until it is read again: "BLOCK: its pool (stock.S) has no reading: it takes nothing new".
   - `once` (`block NAME --now`) is unchanged: it runs whatever the pool is.
   - The daemon's room still caps it: `min(room, daemon free − handing)`.
4. **The completion estimates read the pool now.** `numbers/etamodel.py::read` gives each `BlockIn` the pool now at
   `at` (`poolnow.now(b, poolnow.read_at(p, spec, b, at))`), not the most.
   - At a pool now of 0 or no reading, the simulation already holds capacity at 1 or more. `eta.reasons` must then
     say so on the items waiting at that block, so the estimate is never silent about it: "its pool (stock.S) is 0
     now / has no reading: estimated at 1 run at once".
   - The owner's what-if `block.NAME.pool=N` still overrides the pool now.
5. **The Blocks view reads the pool now.** `numbers/blockmodels.py` sets `m.servers` from the pool now at the end of
   the record it identifies on, with the same reason text in `m.basis` when the pool is 0 or unread (servers then 1).
   So the what-if field that `numbers_api` serves (`"pool"`) starts at the pool now. In `blockdiagram.py::block_fn`,
   the box of a block that takes items gets a row `["pool", ...]`:
   - the stock form: `"N now, at most M (stock.S)"`, with the stock's value from the snapshot, or `"no reading, at most M (stock.S)"`;
   - the number form: `"M"`.

   No new page, panel or UI element.
6. **The factory uses it.** In `dev/model/building.yaml`, the implementor is `pool: {now: stock.implementor-pool,
   most: 4}` and the reviewer is `pool: {now: stock.reviewer-pool, most: 2}`. The comments "the most: the pool now
   is …" are replaced by what is now true. `dev/model/pools.yaml`'s header comment and `dev/bin/pools.py`'s docstring
   now say that the engine holds the blocks to the pool now. The gates' `pool:` inputs and `my_turn` (which also
   holds the machine's headroom) stay as they are.
7. **Docs are current:**
   - SPEC §9.5: the `pool` row of the key table, the example, and the Dispatch paragraph give the stock form: read at
     each dispatch, clamped to its most, no reading takes nothing new, lowering drains.
   - SPEC's estimates paragraph (~l.840) and its Blocks-view sentence say "the pool now".
   - `ergostat/help/blocks.md`, and the agent guide's line on pools if it has one, give the stock form.
   - In `docs/GAPS.md`, the entry is marked done.
8. **The house checks pass:** the unit suite and the four browser files pass with rc 0 (no page test skipped for
   want of a port), ruff is clean, and `demo_check` passes on any example touched (none is planned). Then origin/main
   is merged in and the suites run again.

## Files to touch

- `ergostat/spec/ir.py` (`Block.pool_now`)
- `ergostat/leases/compile.py` (`pool()` returns the most and the ref; the checks above)
- `ergostat/spec/compile.py` (passes `pool_now` into `Block`)
- `ergostat/leases/poolnow.py` (new: `now`, `read_at`)
- `ergostat/leases/dispatch.py`
- `ergostat/numbers/etamodel.py`, `ergostat/numbers/eta.py` (the reason line)
- `ergostat/numbers/blockmodels.py`
- `ergostat/blockdiagram.py`
- `dev/model/building.yaml`, `dev/model/pools.yaml` (comment), `dev/bin/pools.py` (docstring)
- `docs/SPEC.md`, `ergostat/help/blocks.md`, `docs/AGENT-GUIDE.md` (only if it describes `pool:`), `docs/GAPS.md`
- `tests/test_pool_now.py` (new), `tests/test_factory.py`

## Risks

- **lesson-1 (check, then write, without the lock).** The dispatcher could read the stock, then count the leases and
  take them under the lock: a decision on a pool read before the leases it counts. The read must happen inside
  `self.lock` after `items_of`, in the same block as the count and the take. A change of the stock between ticks is
  only seen at the next tick, by design (it drains; it never revokes).
- **lesson-3 (failing open).** The stock may be missing a reading, have a stale one, hold a NaN or a string, or name
  a stock with no sensor. Each of these must not read as the most:
  - dispatch: 0, nothing new taken;
  - compile: a sensorless stock is refused;
  - estimates and Blocks view: 1, said in the reason.

  The estimates are a projection, not an act. Reading 0 there would make the simulation never finish, so they read 1
  and say why (honest numbers), while the dispatcher, which acts, fails closed.
- **lesson-4 (a floor and no ceiling).** A controller stepping the stock up without bound would spawn sessions
  without bound. `most` is required at config time, and the read is clamped to it at run time. In-flight counting
  includes held leases from any engine, as now. (The integer form's lack of a global maximum is not changed here; it
  is outside this gap.)
- **lesson-6 (work that keeps running after it was cancelled).** Lowering is a drain, not a cancel. The claim is
  "nothing running is stopped, nothing new taken". A test shows both halves, so the docs claim no more than that.
- **lesson-7 (merged branches conflict).** `dispatch.py` and `building.yaml` are busy files (main-broken, resources).
  Merge origin/main and run the suites again before saying built.
- **lesson-8 (claims wider than the code).** "Read at each dispatch", "never above its most", "drains when lowered",
  "no reading takes nothing new" and "the estimates and the Blocks view read the pool now" each have a named test
  below. SPEC says nothing that is not tested.
- **lesson-9 (a test that can't fail).** Each test below asserts a number that differs between the most and the pool
  now (most 4, pool now 1 or 2), so reading `b.pool` instead fails it. The implementor breaks each guarded line in
  turn and reports that the test failed:
  - the read moved outside the lock;
  - the clamp removed;
  - `None` mapped to the most;
  - `b.pool` used in etamodel, blockmodels and dispatch.
- **lesson-10 (load flakes).** The dispatch tests wait on conditions (poll the record with a deadline), never on
  fixed sleeps, and run under `-n 8`.

## Acceptance tests

In `tests/test_pool_now.py` unless said otherwise:

- `test_pool_from_a_stock_compiles_with_its_most`: `pool: {now: stock.p, most: 4}` gives `b.pool == 4` and
  `b.pool_now == Ref("stock", "p")`. `pool: 3` gives `pool_now is None`.
- `test_pool_from_a_stock_refuses_what_it_cannot_hold` (parametrized), each by its error code:
  - no `most`;
  - `most: 0`, `most: true`, `most: 2.5`;
  - `now: flow.x` (`wrong-kind`);
  - `now: stock.nope` (`unknown-ref`);
  - a stock with no sensor (`pool-unmeasured`);
  - an extra key;
  - the mapping on a block without `takes:` (`pool-without-takes`).
- `test_pool_now_clamps_and_fails_closed`: `poolnow.now` maps None, NaN, inf, `"x"` and -2 to 0, 2.7 to 2, and 9 to
  4 (most 4). For a block with no `pool_now` it returns `b.pool` whatever the value. (lesson-3, lesson-4)
- `test_dispatch_reads_the_pool_now_at_each_tick`: 6 ready items, a stock read from a file at 1 and most 4. At most
  1 run is going at once. The file is written to 3 with no reload, and then 3 are going at once, never 4.
- `test_a_lowered_pool_drains_and_stops_nothing`: 3 runs held, the stock lowered to 1. None of the 3 runs is killed,
  and they all end on their own signal. No new lease is taken until fewer than 1 are held, then exactly 1. (lesson-6,
  lesson-8)
- `test_the_pool_now_never_passes_its_most`: stock 50, most 2. Never more than 2 held at once over 6 items. (lesson-4)
- `test_an_unread_pool_takes_nothing_new`: a sensor that fails. No lease is taken and the engine says "has no
  reading" once. When the sensor reads 1, exactly 1 lease is taken. (lesson-3)
- `test_the_pool_is_read_under_the_dispatch_lock`: monkeypatch the engine's `get` to record whether
  `dispatcher.lock` is held when the pool's stock is read, and write a held lease of another engine into the record
  in that moment. The read happens with the lock held, and the take counts the competing lease (the pool is not
  passed). (lesson-1)
- `test_estimates_read_the_pool_now`: a record where the stock reads 1 until t1 and 3 after, most 4.
  `etamodel.read(..., at=before t1)` gives the block's `BlockIn.pool == 1`, and `at` after t1 gives 3.
  With no reading, it gives 1 and the reason says "has no reading". `block.NAME.pool=2` still overrides.
- `test_the_blocks_view_servers_are_the_pool_now`: `blockmodels.identify` gives the block `servers == 2` for a stock
  at 2 with most 4. The numbers API's block `"pool"` is 2.
- `test_the_block_box_shows_the_pool_now_and_its_most`: the `block_fn` rows of that block include
  `["pool", "2 now, at most 4 (stock.p)"]`, and `"no reading, at most 4 (stock.p)"` when it is unread. A number-form
  block shows `["pool", "3"]`.
- `tests/test_factory.py::test_the_factory_blocks_take_their_pools_from_the_pool_stocks`: the compiled factory model
  has implementor `pool_now == stock.implementor-pool`, `pool == 4`, and reviewer `pool_now == stock.reviewer-pool`,
  `pool == 2`.
- Existing tests that must still pass unchanged: `tests/test_leases.py::test_one_run_per_item_bounded_by_the_pool`
  and `tests/test_eta.py::test_whatif_pool_and_failure_change_the_estimates`.

## Size budget

180 net lines of code outside `tests/` and `docs/`:

| Part | Lines (about) |
|---|---|
| compile | 35 |
| `poolnow.py` | 35 |
| dispatch | 10 |
| etamodel and eta | 20 |
| blockmodels | 12 |
| blockdiagram | 10 |
| ir | 2 |
| `dev/` YAML and docstrings | 10 |

## Notes from the plan review (answer each)

- Stale readings: Risks says a stale reading must not read as the most, but nothing defines or tests staleness; read_at and e.get take the newest reading of any age. Add an age limit with a test, or drop 'stale' from the claim and the docs (lesson-8).
- e.get under self.lock must return the engine's stored value and never run a sensor, or a slow or hung sensor stalls every dispatch; say which it does, and include a hanging sensor in test_an_unread_pool_takes_nothing_new.
- Call e.get only when pool_now is set; for the number form do not pass None to the engine.
- poolnow.now must refuse a bool reading (True is a number in Python and would give 1); add it to test_pool_now_clamps_and_fails_closed.
- most has a floor and no upper limit at config time (most: 5000 compiles); add an upper limit for the mapping form or state plainly why not (lesson-4).
- read_at picks the newest reading across several sensors by timestamp; confirm it decides exactly as engine.measure does, including equal stamps (lesson-2), and test two sensors that disagree.
- The lock test shows the read happens under this engine's lock; another engine's lease is counted because of the record, not this lock. The docs should claim no more than that.

## Where it stopped

Built: points 1 to 7, and the house checks in point 8 that this session is allowed to run. Not done here: the merge of
origin/main (see the end).

**The plan review's notes, answered:**
- *Stale readings.* No age limit was added. The pool is the stock's newest reading whatever its age, and SPEC §9.5
  says that plainly ("its newest reading, whatever its age"). The word "stale" is claimed nowhere in the docs or the
  code. Only a missing or non-numeric reading reads as 0 (tested). This is the more reversible choice: an age limit
  would need a setting and its own test, and a gap of its own. GAPS.md records it under "Not done".
- *e.get under the lock.* `Engine.get` returns the value the engine's pass stored (`self.signals`). It never runs a
  sensor (a dict lookup). `test_an_unread_pool_takes_nothing_new` uses a sensor that hangs (`sleep 30`, killed by its
  1 s timeout) while the level file is missing. The dispatcher still counts 8 ticks, takes nothing, and says
  "has no reading" exactly once. Once the file reads 1, it takes exactly 1.
- *e.get only when pool_now is set.* `Dispatcher.pool_now` returns `b.pool` for the number form before calling `get`.
  `etamodel` and `blockmodels` call `read_at` only when `b.pool_now` is set.
- *A bool reading.* `poolnow.unread` refuses a bool. `True` and `False` are in `test_pool_now_clamps_and_fails_closed`.
- *An upper limit on most.* None was added. `most` is the owner's written ceiling, the same number `pool: N` is today,
  and the definition puts a global maximum for both forms outside this gap (lesson-4 bullet). A ceiling only on the
  mapping form would make `pool: 5000` legal while `most: 5000` was refused. So that hole stays exactly as wide as
  before, and the stock can never raise a block above what the owner wrote.
- *read_at decides as engine.measure does.* Both loop over the stock's sensors in model order and keep a reading only
  when its stamp is strictly later (`got[0] > best[0]`), so on equal stamps the sensor first in the model wins.
  `read_at` passes `before=at` to `latest`. `test_read_at_picks_as_the_engine_measures` has two sensors that disagree,
  checks the later stamp wins and the equal-stamp tie, and compares `read_at` with `Engine.measure` + `get`.
- *What the lock covers.* SPEC §9.5 says: "The lock is this engine's: a lease another engine writes after the count
  is held to the pool only by the record (the fold refuses a second lease on one item), as for a `pool:` number."
  `test_the_pool_is_read_under_the_dispatch_lock` writes the other engine's lease on the item this engine would take
  first. On another item, two engines could each take within their own room. That race is not new: it exists for
  `pool: N` too, and fixing it is outside this gap.

**A choice the definition left open:** `pool: {now: stock.S.port}` (one sensor's port) is refused (`bad-ref`). The
pool reads the stock's level, as `read_at` and the engine pick it.

**lesson-9, each guarded line broken in turn (then restored):**
- the pool read moved before `with self.lock:`: `test_the_pool_is_read_under_the_dispatch_lock` failed;
- the clamp removed (`max(0, floor(v))`): `test_pool_now_clamps_and_fails_closed` and
  `test_the_pool_now_never_passes_its_most` failed;
- an unread value mapped to the most: the clamp test, `test_an_unread_pool_takes_nothing_new`,
  `test_estimates_read_the_pool_now` and `test_the_blocks_view_servers_are_the_pool_now` failed;
- `b.pool` in dispatch: `test_dispatch_reads_the_pool_now_at_each_tick`, `test_a_lowered_pool_drains_and_stops_nothing`
  and `test_an_unread_pool_takes_nothing_new` failed. In etamodel and blockmodels: the estimates and Blocks-view
  tests failed.

**Size:** about 113 net lines of code under `ergostat/` (budget 180), plus the `dev/` YAML comments and docstring.

**Run, one file at a time, serially:** `tests/test_pool_now.py` (24 passed), `tests/test_leases.py` (20),
`tests/test_eta.py` (13), `tests/test_closedloop.py` (15), `tests/test_blockdiagram.py` (67), `tests/test_factory.py`
(42 passed, 2 skipped, neither of them this gap's), `tests/test_spec_compile.py` (26) and `tests/test_spec_schema.py`
(17). `uv run ruff check ergostat tests scripts` is clean.

**Not run here:**
- The whole unit suite under `-n 8` and the four browser files: this session may not run suites in parallel. The
  factory runs them after it, under the watchdog.
- The dispatch tests under `-n 8` load (lesson-10). They wait on counted dispatcher ticks and on the record, never on
  fixed sleeps.
- The merge of origin/main: this clone has no `origin` remote. The local `main` (3adf48a) is already in the branch.
  The factory's merge step (`implement.merge_main`) must merge origin/main, and the suites must run again before this
  is called built (lesson-7).
- No example was touched, so `demo_check` was not needed.

### Round 2

**The merge of main (2b101c6).** It conflicted in eight files. Each keeps main's change and the branch's:
- `agents.py`, `fac.py`, `factory.toml`: main's groomer next to the pipeline manager.
- `building.yaml`: main's `order: rank` on the implementor's `takes:`, with the branch's `pool: {now: …, most: 4}`.
- `ergostat.yaml`: main's `rank`, `value` and `size` columns; `parked` moved from done to paused, as main has it,
  with the branch's `situation` kind; the closed comment names both who closes.
- `leases/compile.py`: main's `order` key and `re`, the branch's `POOL_KEYS` and `Ref`.
- `numbers/etamodel.py`: `BlockIn` gets main's `order` and `off` and the branch's pool now and `pool_said`.
- SPEC: the estimates paragraph has main's `order:` and switched-off text, then "its pool now"; the key table has
  main's `order` on `takes` and the branch's `pool` row.

**Round 1's findings, each answered (lesson-12):**
- *The schema (blocking).* `schema/ergostat.schema.json`'s `pool` is now `oneOf` two forms: an integer of 1 or more,
  or `{now: "^stock\.NAME$", most: integer ≥ 1}` with both keys required and no others.
  `docs/spec-examples/relations.yaml` gains a `reviewer` block using the mapping form (and a `reviewers` stock with a
  manual sensor). So both `test_each_example_in_the_spec_is_valid` and `test_spec_compile`'s example compile cover
  it. The new `tests/test_spec_schema.py::test_a_block_s_pool_is_a_number_or_a_stock_with_its_most` checks that the
  schema takes both forms and refuses these: `0`, no `most`, no `now`, `most: 0`, `most: true`, `flow.x`,
  `stock.S.port`, an extra key.
- *The lock test's claim.* The competing lease stays on `ticket/0`. The assertion's message now says what holds it:
  the fold refuses a second lease on one item. The acceptance line's "the take counts the competing lease" cannot
  hold for another engine's lease taken after this engine's count, because that engine holds its own lock. SPEC §9.5
  now says exactly this: such a lease is counted at the next look. On the same item the fold refuses the second
  lease. On another item both stand, as for a `pool:` number. Closing that race needs a lock across engines (the
  record's), for both forms, and is outside this gap.
- *The start-up "no reading".* The dispatcher's first tick can come before the engine's first pass has loaded the
  readings. `Engine.measured` (set by a full `measure`) now gates the message. Before it, the pool is still 0 and
  nothing new is taken (closed), but nothing is said. `test_no_reading_is_not_said_before_the_first_pass` checks
  this: a recorded reading, no pass yet, so 0 and silence; then 2 after `measure`; and an unread stock is still said
  once after `measure`. With the gate removed, the test failed (lesson-9). This adds 3 lines to `engine.py`, which
  is not in the files list; that is the smallest place to know "the readings are loaded".
- *on-stale and the pool's stock.* SPEC §9.5 now says that the pool's stock is not one of the block's reads, so its
  `on-stale` does not watch it. Nothing in the code changed for this.

**Run in round 2, one file at a time:** `tests/test_pool_now.py` (25 passed), `tests/test_leases.py` (20),
`tests/test_eta.py` (13), `tests/test_take_order.py` (4), `tests/test_closedloop.py` (15),
`tests/test_blockdiagram.py` (67), `tests/test_spec_compile.py` (26), `tests/test_spec_schema.py` (27),
`tests/test_factory.py` (42 passed, 2 skipped, as before), `tests/test_backlog.py` with
`tests/test_factory_knowledge.py` (35). Ruff is clean.

**Not run here:** the whole unit suite under `-n 8` and the four browser files. This session may not run them;
the factory runs them after it. No example under `examples/` was touched.

## Where it stopped

Parked by the factory (dead-letters, 2026-11-20 18:11).

Its runs failed past their attempts (a dead letter):
- attempt 8: ack
- attempt 9: nack exited 1
- attempt 10: nack exited 1
- attempt 11: nack exited 1

### Round 3

**The merge of main (7b39bc9).** It conflicted in three files. Each keeps main's change and the branch's:
- `dev/bin/agents.py`: main gives the plan reviewer the reviewer's read-only tools; the branch's groomer keeps them too.
- `dev/model/knowledge.yaml`: the planner's `takes:` drops `planned` from `to` (main: the plan review is advice, not a
  gate) and keeps the branch's `unblocked: true, order: rank`.
- `tests/test_factory_knowledge.py`: main's `[plan] review = "all"` with the branch's `groomer` role.

**The queue's failure.** `tests/test_relations_asof.py::test_an_item_of_no_kind_changed_since_has_no_links_and_the_rest_answers`
(both params) came from main (relations-as-of) and asserted the status `ready`. This branch carries the backlog merge
(2b101c6), which renames that status to `unblocked` (`precedence.status`), and the branch's `tests/test_relations.py`
already says `unblocked`. So the failure was the two merged changes meeting (lesson-7), not this gap's code. The fix
is only the two asserts renamed to `unblocked`, as `test_relations.py` has. Nothing under `ergostat/` changed for it.

**Still open, outside this gap (lesson-13).** main (7b39bc9) does not hold 2b101c6. So a diff of this branch against
main still carries the backlog feature as well as this gap. Other branches' reviews have raised the same thing. Only
the coordinator can settle it, by landing the backlog merge on main first or by choosing what this branch may carry.

**Run in round 3, one file at a time:** `test_relations_asof.py` (9), `test_relations.py` (18), `test_pool_now.py`
(25), `test_factory_knowledge.py` (34), `test_factory.py` (42, 2 skipped as before), `test_leases.py` (20),
`test_eta.py` (13), `test_take_order.py` (4), `test_backlog.py` (13), `test_spec_schema.py` (27),
`test_spec_compile.py` (26), `test_blockdiagram.py` (67), `test_closedloop.py` (15), `test_graph_cli_web.py` (29),
`test_resilience.py` (24). Ruff is clean. `test_items_page.py` was skipped here because this container has no
browser. The whole suite under `-n 8` and the four browser files were not run: the factory runs them.

## Where it stopped

Parked by the factory (review/a-block-s-pool-set-by-the-model-3, 2026-11-20 20:21).

Done, judged by reading: DoD points 1-7 for the pool-now feature itself. Compile with both forms and every error code, poolnow.now/read_at/said, dispatch reading the stock under self.lock and failing closed with one 'has no reading' message, estimates and the Blocks view at the pool now (held at 1 and said why), the block box's pool row, the factory's implementor and reviewer on implementor-pool and reviewer-pool, and SPEC/help/GAPS updated. The acceptance tests exist and assert numbers that tell the pool now from the most. Left: the branch is built on a local main holding the unreviewed backlog merge (2b101c6), which is not on origin/main, so merging it would land the backlog feature too, and building.yaml and the relations-as-of test now depend on it. It stops because this is round 4 and the rule parks after two failed reviews. Resolving the base is the coordinator's call: either the backlog is reviewed and lands on main first and this branch is rebuilt on it, or the gap's commits (d1532eb4, ae5e4563, 251058f4 and the pool parts of 578cc5ad) are carried onto a fresh branch from origin/main, without `order: rank` in building.yaml and without the test_relations_asof.py rename. Then the full unit suite and the four browser files are run.

### Round 4 (continued)

**The base is settled.** main (a1d1b94) now holds the backlog merge (2b101c6 is its ancestor). So `git diff
a1d1b94 HEAD` carries only this gap: the files of the definition, plus `schema/ergostat.schema.json`,
`docs/spec-examples/relations.yaml`, `tests/test_spec_schema.py` (round 2's schema finding) and the 2 lines in
`ergostat/spec/engine.py` (round 2's start-up gate). The `order: rank` in building.yaml and the relations-as-of
rename are main's now, not the branch's.

**The merge of main (a1d1b94).** It conflicted in five files. Each keeps main's change and the branch's:
- `dev/factory.toml`: main moved the pipeline manager's lines after the groomer's, so the branch's copy was dropped.
- `dev/model/knowledge.yaml`: main's planner `where: {continues: null}` and `pool: 12`.
- `ergostat.yaml`: main's `parked_for`, `loop_rounds` and `loop_hours` columns and its closed comment, and main's
  `denied` among the lessons that are done.
- `docs/GAPS.md`: the branch's done entry for this gap, and main's done entry for `mode: advise`.
- `dev/model/building.yaml`: the branch's mapping form, with **main's ceilings**: main's operator raised the
  implementor's `pool:` to 9 and the reviewer's to 6 (with `[pools] implementor_max = 9`, `reviewer_max = 6` in
  factory.toml and in pools.yaml's stock descriptions). So the factory is `pool: {now: stock.implementor-pool, most:
  9}` and `pool: {now: stock.reviewer-pool, most: 6}`, not the definition's 4 and 2. Writing 4 and 2 back would have
  undone the operator's change on main. Keeping main's numbers is the more reversible choice, and only a number
  differs. `tests/test_factory.py::test_the_factory_blocks_take_their_pools_from_the_pool_stocks` asserts 9 and 6.
  The comments in building.yaml and pools.yaml and the docstring in `pools.py` say 9. The acceptance tests in
  `tests/test_pool_now.py` still use most 4 with a pool now of 1 or 2, so they still tell the pool now from the most.

**Run after the merge, one file at a time:** `test_pool_now.py` (25 passed), `test_factory.py` (71, 2 skipped),
`test_leases.py` (29), `test_eta.py` (13), `test_spec_schema.py` (27), `test_spec_compile.py` (26),
`test_factory_knowledge.py` (54), `test_take_order.py` (4), `test_blockdiagram.py` (67), `test_closedloop.py` (15),
`test_relations_asof.py` (9), `test_backlog.py` (13). `uv run ruff check ergostat tests scripts` is clean.

**Not run here:** the whole unit suite under `-n 8` and the four browser files. This session may not run them; the
factory runs them after it. No example under `examples/` was touched.
