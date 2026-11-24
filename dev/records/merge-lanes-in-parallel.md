# merge-lanes-in-parallel: Batches are tested in parallel lanes, split by the paths they touch

The queue runs one batch at a time while approved work waits. Allow several lanes: batches whose changed paths do not overlap are tested at once, and a speculative lane may test the next batch on top of the current one, discarded if the current one fails. Lanes are bounded by measured CPU and memory, since the machine is CPU-limited.
Done: 1. Tests: non-overlapping batches land in parallel; overlapping ones are serialised; a failed base discards its speculative lane. 2. A fixture replay shows merges per hour against one lane. 3. Lanes never exceed the declared resource bounds.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.

## Where it stopped

Round 1. The general part is built in the core; the factory's queue does not use it yet (see Left).

- **What it is.** A declared option on a block's queue, `takes: {lanes: {apart: FIELD, most: N, within: {cpu, memory},
  each: {cpu, memory}, ahead: K, passed: [STATE]}}` (SPEC §9.5, *Lanes*), off unless declared. The one rule is
  `ergostat/leases/lanes.py`'s `plan`: an item whose FIELD list shares nothing with any lane under way starts apart.
  One that shares entries only with lanes on one lane's chain starts on top of it when the chain is less than K deep.
  Its lease and its run's input carry `on`, the chain. Any other item waits, and so does every later item that
  overlaps a waiting one. The dispatcher calls it at each look (`lanes.choose`, under its lock). The fixture replay
  calls it too (`lanes.replay`).
- **Discard.** A lane that does not pass stops every lane on top of it (`lanes.discard`, through `leases/kill.py`), and
  each ends given back uncounted. Not passing means: its run gave it back, its lease expired, or it left its item
  outside `passed`. A lane on top that goes red while a lane it is on has not passed is given back uncounted too
  (`lanes.unproven`).
- **Resource bound.** The lanes held at once (leases held and runs draining) are at most `most` (≤ 16) and at most the
  pool. They are also at most as many as `within` holds, each lane costed at the larger of `each` and the block's 20
  newest ended runs (CPU seconds over wall seconds, peak memory, read at most once a minute). A cost that cannot be
  read allows one lane, and this is said. Every number has a ceiling at compile time (`bad-lanes`) and again at run
  time (`plan` clamps `ahead`, `room` clamps `most`).
- **Done items.**
  - 1: `test_non_overlapping_batches_land_in_parallel`, `test_overlapping_batches_are_serialised_in_order`,
    `test_a_failed_base_discards_its_speculative_lane`. Also `test_an_expired_base_discards_its_lane_on_top`,
    `test_red_on_top_of_a_base_under_way_is_not_counted`, and `test_a_look_after_the_base_failed_puts_nothing_on_it`
    (lesson-1: a look whose index still shows the failed base held puts nothing on it, because the base is marked
    failed under the dispatcher's lock).
  - 2: `test_fixture_replay_merges_per_hour_against_one_lane`. `tests/fixtures/lanes_replay.json` has 24 batches, a
    batch every 12 minutes, about 40 minutes a run, 3 red. One lane: 21 merged in 958 min, **1.315 merges/h**. Three
    lanes, one deep on top, within 12 cores at 4 a lane: 21 merged in 367 min, **3.433 merges/h**, 2 runs discarded,
    at most 3 held. The fixture is made up, shaped like the factory's queue. It is not measured from the live
    instance (not to be read in the session), and three lanes there are bounded by the arrival rate.
  - 3: `test_lanes_never_exceed_the_declared_resource_bounds` (4 lanes at the declared cost, 2 once runs measure 3
    cores and 3g, held at 2 as runs end and start, 1 when unreadable), `test_the_bound_holds_for_any_queue` (400
    random queues through `plan`), `test_lanes_checked_with_their_bounds`. Also `test_off_by_default_existing_models_unchanged`.
- **Seen to fail** (each mutation reverted):
  - `room` ignoring the measured cost fails the bounds test and the replay's tight case.
  - `plan` ignoring overlap fails the serialisation, discard, race, random-bound and replay tests.
  - `finish` not calling `discard` fails the discard test.
  - `_finish` not reading `lanes.out` fails the discard test at the given-back reason.
  - `expire` not calling `discard` fails the expiry test.
- **Run here:** tests/test_merge_lanes.py, test_frozen_window, test_spec_schema, test_take_order, test_lease_end_turns,
  test_faults_hold_by, test_leases, test_lease_kill, test_lease_watch_slices, test_gaps_doc, test_gapsdoc,
  test_spec_structure, test_daemons. All pass, and ruff is clean. Not run
  here: the whole unit suite and the four browser files (no page changed). No example touched. main merged: already up
  to date.
- **Size:** about 350 net lines outside tests, docs and dev (budget 600).

Decisions taken alone (each the more reversible):
- **Lanes belong to the dispatcher, not to dev/bin/queue.py.** A lane is a leased item run. The core names no merges:
  FIELD is any list of what an item touches, and `passed` is any state.
- **One lane always runs**, even when one measured lane costs more than `within`. Holding to 0 would stop the block
  for good, since nothing new would be measured. SPEC says so. The claim is that lanes beyond the first never exceed
  the bound.
- **A discarded item goes back behind those waiting**, as any item back in its state does (`ready()` sorts by entry).
  The replay does the same.
- **The blocking order.** An overlapping item waits behind an earlier waiting item it overlaps, even one it could have
  gone on top of, so overlapping work keeps its order.
- **Not modelled:** `ergostat block --now` takes no notice of lanes, and the completion estimates (eta) do not model
  them.

Left:
- **The factory's queue is not a user yet.** `dev/bin/queue.py` runs as one program under the queue lock, pool 1. It
  builds its batch inside its run and lands on one checkout's main with one pending push. To use lanes, each batch
  must be an item the merge-queue block takes (pool ≥ lanes) carrying its changed paths. Each run must test on a
  worktree of its own, from main or from the lane it is `on`, and land only after its chain. The lock, the single
  pending push and `recover()` must allow several runs. That is a rewrite of queue.py (about 1,400 lines) beyond this
  gap's budget and risk, so dev/model/landing.yaml is unchanged.
- **Checking less needs a way back.** Apart lanes, when the factory uses them, land two batches whose combination no
  run tested. The owner's rule asks for a way to find and revert regressions on main for that path. The daily browser
  run (browserday.py) and the escapes record (escapes.py) find some, but nothing here reverts. The factory's switch to
  apart lanes needs that first. A lane on top tests its whole chain, so it checks no less.

Round 2: both blocking findings of review 1 are fixed. Review 1 listed no other findings.
- **A take that fails under a lane on top** (dispatch.py `tick_block`, lesson-1 and lesson-3). A look plans first and
  takes after, so a base's take can fail: the budget refuses it, `bounds.room` is full, or ergostat is stopping. Then
  any start whose `on` names a lane planned in that look and not taken is now dropped, at any depth. It is not taken
  and waits for a later look. Test: `test_a_base_whose_take_fails_takes_nothing_on_top` (a refused; b on a and d on
  a and b are not taken, c apart is; the next look takes a, b on a, and d on a and b). With the check removed, b and
  d were taken on a, which never ran, and the test failed.
- **An unknown cost is the worst case** (compile.py, ir.py, lanes.py `room` and `cost`, lesson-3 and lesson-8). If
  `each` is not declared, its cores and memory are now 0, which means not declared. `cost` returns None for cores or
  memory when none of the 20 newest runs measured it. `room` allows one lane when either is unknown: neither declared
  nor measured. So a new block with no `each` runs one lane until its runs are measured. The replay's default cost is
  unknown too. Test: `test_an_unknown_cost_is_the_worst_case` (no `each`: 1 lane before any run, 4 after runs measured
  at 2 cores and 2g; cores measured without memory gives 1). With the check removed, 4 lanes were held from the
  start, and the test failed. SPEC §9.5 and the agent guide say so.
- **A slip found and fixed in this round.** The first version of the take-loop edit nested the frozen-window record
  (`frozen.broken`) under the failed take. tests/test_frozen_window.py caught it, and that test passes now.
- **Run here:** tests/test_merge_lanes.py (16), test_leases, test_lease_end_turns, test_spec_schema, test_take_order,
  test_frozen_window, test_lease_kill, test_spec_structure, test_faults_hold_by, test_lease_watch_slices,
  test_daemons, test_gaps_doc, test_gapsdoc. All pass, and ruff is clean. Not run here: the whole unit suite and the
  four browser files (no page changed). No example touched. main merged: already up to date.
- **Size:** about 25 more net lines outside tests, docs and dev, about 375 in all (budget 600). Left is as in round 1.

Round 3: the one finding of review 2 (blocking) is fixed. The review listed no other findings.
- **A taken-up lane on top keeps its `on`** (dispatch.py `adopt`, lanes.py `taken_up`; lesson-3, lesson-5).
  `adopt()` now reads the item's lease from the fold and copies its `on` into `going` when that lease is this run's
  at this fence. So after a restart, `discard` finds the lane when its base goes red, is given back, or its lease
  expires. Test: `test_a_base_failing_under_a_taken_up_lane_discards_it` (restart; a fails: b on a is stopped and its
  end is given back uncounted; e's lease expires: f on e is stopped). With the copy removed, the test failed (b held
  with no `on`).
- **A base that ended before the take-up** (lesson-1). `adopt` reads the lease, then writes `going` under the lock,
  so a base that failed before the write would have been missed. After the write, `taken_up` reads each base the
  lane is on. One that holds no lease and is not passed (or cannot be read: the worst case) stops the lane now, and
  its end is given back uncounted, as `discard` would have done. A base that fails after the write finds the lane
  through `discard`. Test: `test_a_base_failed_before_its_lane_was_taken_up_discards_it` (a failed under the engine
  before; taking up b on a stops it. f on e, whose e landed before the restart, is kept and lands). With the call
  removed, the first case failed. With every base read as not passed, the kept cases failed.
- **Not changed, said here:** a lane on top whose run moves its item on before its kill lands still stands. That is
  as in round 1, and SPEC §9.5 already says so ("a run that did so first stands"). SPEC §9.5 and the agent guide now
  say that a taken-up lane on top is discarded the same way.
- **Run here:** tests/test_merge_lanes.py (18), test_runs_adopted, test_leases, test_lease_kill, test_lease_end_turns,
  test_frozen_window, test_spec_structure, test_take_order, test_gaps_doc, test_gapsdoc. All pass, and ruff is
  clean. Not run here: the whole unit suite and the four browser files (no page changed). No example touched. main
  merged: already up to date.
- **Size:** about 25 more net lines outside tests, docs and dev, about 400 in all (budget 600). Left is as in round 1.

Round 4: the one finding of the reviews and the queue (blocking, lesson-3) is fixed. No other finding was listed.
- **A lane on top needs its `passed` states** (compile.py `lanes`, lanes.py `passed`, `taken_up`, `unproven`).
  `passed` is read checking for None, not falsiness. When present it must be one or more non-empty state names, so
  `passed: false`, `0`, `{}`, `[]` and `""` are refused (`bad-lanes`). `ahead` above 0 without `passed` is refused
  too, since no base could then be told failed. At run time a lane passes only when its run leaves its item in a
  `passed` state. With none declared (only `ahead: 0` allows that, and then nothing is on top) none passes: the worst
  case, no longer "any move passes". So a base moved to `failed` always discards its lane on top. SPEC §9.5 and the
  agent guide (its example now says `ahead: 1, passed: [landed]`) say so.
- **Test:** `test_a_lane_on_top_needs_its_passed_states` (ahead without passed, and each falsy or empty passed, are
  refused; `passed: landed` with ahead and no passed without ahead are kept; `lanes.passed` with none declared passes
  neither `failed` nor `landed`). Seen to fail, each mutation reverted: with the ahead check removed (at `ahead: 1`);
  with the present-but-empty check removed (at `passed: []`); with the runtime read as "none declared: any move
  passes" (at the `lanes.passed` assert).
- **Run here:** tests/test_merge_lanes.py (19), test_spec_schema, test_runs_adopted, test_leases, test_lease_kill,
  test_spec_structure, test_lease_end_turns, test_take_order, test_frozen_window. All pass, and ruff is clean. Not
  run here: the whole unit suite and the four browser files (no page changed). No example touched. main merged:
  already up to date.
- **Size:** about 0 more net lines outside tests, docs and dev (the fallback to `moved_on` is gone), about 400 in
  all (budget 600). Left is as in round 1.

## Entry

section: The factory (ergostat on ergostat)

- **Batches tested in parallel lanes, split by the paths they touch** (core part built, on
  `factory/merge-lanes-in-parallel`; SPEC §9.5, *Lanes*). `takes: {lanes: {apart: FIELD, most: N, within: {cpu,
  memory}, each: {cpu, memory}, ahead: K, passed: [STATE]}}` runs a block's items at once when their FIELD lists share
  nothing. An overlapping item waits in order, or runs on top of a lane up to K deep. It is stopped and given back
  uncounted when that lane does not pass. The lanes held are bounded by `within` at the larger of the declared and the
  measured cost. One rule (`leases/lanes.py`) serves the dispatcher and a fixture replay (1.3 merges/h on one lane
  against 3.4 on three). Off unless declared. *Left*: the merge queue (dev/bin/queue.py, one run under one lock) is
  not a user yet, and apart lanes there need a way to find and revert regressions on main first.
