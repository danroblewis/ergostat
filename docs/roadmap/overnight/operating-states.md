# operating-states: operating states declared in the model, entered by the owner's typed act or by a goal's trip, capping the pool of every block that takes items
depends-on: []

## Definition of done

Gap: `docs/proposals/coordinator/08-modes-and-protection.md` §2 and §5.3 (operating states, trips) is designed but not built. Nothing in `ergostat/` today knows an operating state. This branch builds the first part: states declared in the model, entered and left, tripped by goals, and the state in force capping the lease dispatcher's pool. Gates and act categories scheduled by state, bypass leases, act-risk, P3/T1 and presence (away) are other gaps (`operating-gates`, `act-risk-gating`, `run-budget-permissive`) and are not built here.

When it is done, all of the following is true:

1. **Declared.** A model may have a top-level `operating:` section. Each entry is a state named `^[a-z0-9][a-z0-9-]{0,63}$` with these keys:
   - `rank:` a whole number, 1 or more, unique among the states. A higher rank takes precedence.
   - `pool:` optional, a whole number, 0 or more. It is the most runs at once of each block that takes items while the state is entered. Left out, the state sets no cap.
   - `description:`.
   - `trips:` a map from goal name to `{unknown-after: DURATION}` or `{}`/null.

   The compiler (`ergostat/operating/compile.py`, called from `spec/compile.py`) refuses each mistake with its own code: `bad-name`, `bad-number` (rank or pool), `rank-taken`, `unknown-ref` (a trip on a goal that does not exist), `bad-duration`, `unknown-after-unmeasured` (unknown-after on a goal whose part has no sensor) and unknown keys. It also refuses **`pool-rises-with-rank`**: going up the ranks, a state's pool must stay the same or fall, where no cap counts as infinite. So the SPEC's example has incident (rank 3, pool 0) over freeze (rank 2, pool 0) over maintenance (rank 1, pool 1). A model with maintenance at rank 3 and pool 1 over freeze at rank 2 and pool 0 is refused. A model without `operating:` gets nothing: no built-in kind, no fold read and no trip check (invariant 12).

2. **Folded from the record.** The built-in item kind `ergostat.operating` is added only when `operating:` is declared.
   - Its ids are `ergostat.operating/<state>` and its states are `entered` and `left`.
   - It is changed by the events `ergostat.operating.entered` and `ergostat.operating.left`. Its fields are `by` (owner | run | trip), `why`, `since` and `trips` (a list of `{goal, spell, event}`).
   - An `entered` on an item already entered keeps it entered and appends to `trips`.
   - An `entered` after a `left` starts afresh: `by`, `why` and `trips` from the earlier entry are cleared (lesson-5).
   - The fold refuses a `left` that was recorded during a run (its `causedby` is set).
   - It shows in the Items tab like every kind. No new page or panel.

   `ergostat/operating/fold.py::in_force(p, spec)` returns `(top, pool, why)`:
   - `top` is the highest-ranked entered state.
   - `pool` is the **smallest pool among all entered states** (None when no entered state sets one).
   - An entered state the model no longer declares counts as pool 0 until it is left.
   - **If the record cannot be read (any exception from the query or the fold), it returns pool 0, whatever any declared state's pool is**, and the reason says so.

3. **Entered and left.**
   - `ergostat operating` lists the states: rank, pool, entered or left, by, since and the trips that entered it.
   - `ergostat operating enter NAME --why TEXT` records the owner's entry.
   - `ergostat operating leave NAME --why TEXT` records the owner's leaving. It works for any entered state, including one the model no longer declares.
   - The CLI refuses `leave` (rc 1) when `ERGOSTAT_RUN` is in its environment. `enter` from a run is allowed (it moves toward the safe state) and is recorded as caused by the run, with `by: run`.
   - Only the owner leaves a state. Trips never leave one in this branch.
   - The docs claim exactly this much: the refusal covers a run that carries its environment or records through `ergostat record`. It is not a guard against a process that writes the record by other means; that is the sandbox's job (lesson-8).
   - `operating` is not a read topic for the last-good-model fallback (`goodmodel.READS` is unchanged), so `tests/test_cli_fallback.py` still holds.

4. **Trips** (`ergostat/operating/trips.py::check(p, spec, now)`). These run in the dispatcher's thread once a second (its `EVERY` branch), holding `Dispatcher.lock` across the read, the decision and the write. Each trip `(state, goal)` has a current **spell**, taken from the record only:
   - **Crossing:** if the goal's newest unvoided `loop.*` event is `loop.off`, the spell is `off:<that event's id>`. Otherwise there is no crossing spell. The engine restores goal status from the record at start (`engine._initial`), so a restart does not record a new `loop.off` for a goal already off.
   - **Unreadable** (only with `unknown-after:`, declared per trip under the state): the clock starts at the newest reading's time over the sensors of the goal's part (`p.measurements.latest`). If the part has never been read, the clock starts at the time of the `ergostat.operating.watching` event (item: the goal, data: `{state}`). The first `check` that finds no such event writes it once, and a restart finds it and writes nothing. When `now − start > unknown-after`, the spell is `unread:<newest reading's time>` or `unread:never`. Neither the engine's start time nor `born` is used, so a restart does not reset the clock. Time asleep counts (worst case).
   - A trip fires **once per spell**: when the spell is not in the `trips` of any earlier `ergostat.operating.entered` of that state in the record, `check` records `entered` with `{by: trip, goal, spell}`, caused by the `loop.off` for a crossing. It fires whether the state is entered already or not, so that the owner's later `leave` covers it. Spells are compared for equality on what was read (ids and stored reading times), never by comparing wall-clock times (lesson-2). So an owner's `leave` is not undone by the same crossing or the same unread spell: neither on later passes nor after an engine restart. A new crossing, or a new reading followed by a new silence, is a new spell and trips again.
   - If a trip's inputs cannot be read (the event query or the measurements raise), `check` records nothing, the engine says why, and **that look's dispatch uses pool 0** (lesson-3).

5. **Scheduling the pool** (`leases/dispatch.py`):
   - Each `tick` reads `in_force` once. For each block, `room = min(b.pool, pool) − in flight` (the daemon's room as before), so a state never raises a block's pool.
   - With pool 0 nothing new is leased. Runs already holding leases are not killed: they run on and end as usual ("running work finishes, nothing new starts").
   - `ergostat block NAME --now` (`Dispatcher.once`) still ignores the block's pool, but is refused under pool 0, naming the state.
   - **The race:** right after `take` writes `TAKEN` (the fold re-read it already does), it reads `in_force` again. If the cap now leaves no room for this run, counting the runs already in flight, it ends the lease at once (`ENDED`, nack, `count: False`, why "operating state X entered"). The item goes back to the state it was taken from with its attempts unchanged, and no run starts. Any entry with a lower seq than the `TAKEN` is visible to that read. An entry after it is work that started before the state and finishes under it (lesson-1).
   - Blocks that do not take items (every:, cron:, commanded) run as before. Gating those by state is `operating-gates`.

6. **Docs:**
   - SPEC §9.5 gets a subsection "Operating states" covering points 1 to 5, with the example and the claim limits above.
   - `docs/AGENT-GUIDE.md` gets how to declare `operating:` and trips.
   - `docs/GAPS.md`'s "Operating modes…" entry gets "operating states and trips capping the pool: done (`operating-states`); left: gates by state, bypass leases, act-risk, P3/T1, presence".
   - `dev/model/` is not changed.

Done also means everything in the house rules: the acceptance tests exist and pass; the unit suite and the four browser files pass with rc 0 (no page test skipped for want of a port); ruff is clean; origin/main is merged in and the suites are run again. No example under `~/ergostat-demos` is touched, so `demo_check` is not required (say so in the report).

## Files to touch

- `ergostat/operating/__init__.py` (new: event types, the built-in kind)
- `ergostat/operating/compile.py` (new)
- `ergostat/operating/fold.py` (new: `in_force`)
- `ergostat/operating/trips.py` (new)
- `ergostat/operating/acts.py` (new: enter, leave)
- `ergostat/spec/ir.py` (an `OperatingState` dataclass, `Spec.operating`)
- `ergostat/spec/compile.py` (the section in the known sections, call to compile, the kind added when declared)
- `ergostat/leases/dispatch.py` (the cap in `tick` and `once`, the re-check after `take`, trips in the `EVERY` branch)
- `ergostat/cli/operating.py` (new), `ergostat/cli/__init__.py` (the topic)
- `docs/SPEC.md`, `docs/AGENT-GUIDE.md`, `docs/GAPS.md`
- `tests/test_operating.py` (new)

## Risks

- **lesson-1:** `tick` decides room, then `take` writes `TAKEN`, and an owner's `enter` can land in between. Separately, `trips.check` reads "spell not yet answered" and then writes. The fix for the first is the post-write re-read in `take`, ordered by seq. For the second, `check` runs only in the dispatcher thread under `Dispatcher.lock`, and the only other writers (owner, runs) do not touch the trip's spell key.
- **lesson-2:** comparing reading times with `>` to decide whether a spell is new. Spells are compared by equality on event ids and stored reading times, never as newer/older.
- **lesson-3:** an unreadable operating record treated as "no state entered". It must give pool 0 even when the top state's pool is 1. Other cases: trip inputs unreadable; an entered state no longer declared (a lookup that misses); a goal never read (must not wait forever: its clock is the `watching` event).
- **lesson-4:** a state's `pool` read with a floor and no ceiling. It is applied only as `min(b.pool, pool)`, so it can't raise anything. Tested.
- **lesson-5:** the item id `ergostat.operating/freeze` re-entered after a `left` keeps the old `by`, `why` and `trips`, for example a stale trip spell that then suppresses a new one, or `by: trip` shown on an owner's entry.
- **lesson-6:** pool 0 must not kill running work, and the run given back in the race must never start its program. Tested both ways.
- **lesson-7:** a new CLI topic and flags interacting with the last-good-model fallback classification; main's dispatcher changes conflicting at merge.
- **lesson-8:** "only the owner leaves a state" stated wider than the env/`causedby` check supports; "a restart never resets the clock" stated without a test.
- **lesson-9:** pool tests that would pass with the top state's pool, or with the latest-entered state's pool. Each test below says what it breaks.
- **lesson-10:** dispatch and trip tests that wait with sleeps. Drive `tick()` and `trips.check(now=…)` directly with injected `now`, and poll the record with a deadline for a run's end.
- **lesson-12 and lesson-13:** in a fix round answer every finding; report unrelated suite failures, don't fix them.

## Acceptance tests

All in `tests/test_operating.py`. The implementor breaks the guarded code for each one and reports that it fails.

- `test_compile_example_and_kind_only_when_declared`: the SPEC example compiles, and `ergostat.operating` is in `spec.items`. A model without `operating:` has no such kind, and its dispatcher never calls `in_force` (monkeypatched to raise; leases are still taken).
- `test_compile_refuses_bad_states`: each code in point 1 except `pool-rises-with-rank`, one case each.
- `test_pool_rises_with_rank_refused`: maintenance (rank 3, pool 1) over freeze (rank 2, pool 0) gives `pool-rises-with-rank`, and the equal-pool and falling-pool orders compile. Fails if the check is removed (lesson-8/9).
- `test_state_caps_block_pool`: a block with pool 3 and five ready items. With `careful` (pool 1) entered, exactly one lease; left, three. A state with pool 5 over a block with pool 2 gives two (lesson-4).
- `test_pool_zero_takes_nothing_running_work_finishes`: a run holding a lease when freeze (pool 0) is entered is not killed and ends ack. No new lease is taken while freeze is entered (lesson-6).
- `test_freeze_and_maintenance_both_entered_take_nothing`: the example model. Freeze is entered first and maintenance (pool 1) second, so the latest entered has pool 1. No lease is taken. Fails if dispatch uses the latest-entered or lowest-ranked state's pool.
- `test_pool_is_smallest_among_entered`: a `Spec` built directly (the check bypassed) with a higher rank at pool 2 and a lower rank at pool 0, both entered. `in_force` gives 0 and no lease is taken. Fails if the top state's pool is used.
- `test_unreadable_fold_is_worst_case`: a model whose only and top state, `careful`, has pool 1 and is entered, with a block of pool 2. With the operating query monkeypatched to raise, `in_force` gives pool 0 with a reason, and no lease is taken. The control case (readable) takes exactly one. Fails if the top state's pool (1) or "none entered" (2) is used (lesson-3/9).
- `test_undeclared_entered_state_counts_as_pool_zero`: freeze entered, then the model reloaded without freeze: no lease. After `ergostat operating leave freeze`: leases resume (lesson-3).
- `test_state_entered_between_check_and_take_gives_back`: monkeypatch the step between `tick`'s room computation and the `TAKEN` write so that it records the owner's freeze entry. The lease is ended nack with `count: False` naming freeze, the item is back in its state with attempts unchanged, and the block's program never ran (its marker file is absent). Fails without the re-read in `take` (lesson-1/6).
- `test_owner_leave_in_trip_gap`: monkeypatch between `trips.check`'s read and write to record an owner's `leave`. The state ends up entered by the trip, and the next `check` writes no second `entered` (lesson-1).
- `test_owner_enter_leave_cli`: `enter`, the listing, and `leave`, with their rc. With `ERGOSTAT_RUN` set, `leave` is rc 1 and `enter` is recorded `by: run`. A `left` event recorded with `causedby` is refused by the fold (lesson-8).
- `test_reentered_state_clears_old_fields`: entered by a trip (goal, spell), the owner leaves, the owner enters. Then `by == owner`, `why` is the new one and `trips == []` (lesson-5).
- `test_crossing_trips_once_per_crossing`: the goal goes off, so the state is entered by trip with spell `off:<loop.off id>`. The owner leaves, and later checks don't re-enter. The goal holds, then goes off again: it re-enters (lesson-2/5).
- `test_unknown_after_trips_on_record_clock`: the part was last read at t0, and `check(now=t0+unknown-after+1)` enters with spell `unread:t0`. A new reading means no trip. Silence again trips with a new spell.
- `test_restart_neither_reenters_nor_resets_clock`: (a) after a crossing trip and the owner's leave, a new engine and dispatcher on the same project (a restart) record no new `loop.off` and no `entered`. (b) The part was last read at t0 and the engine restarts at t0+50 s with unknown-after 60 s: `check(now=t0+61)` enters. A clock from engine start would wait until t0+110. (c) After the owner leaves that unread spell, a restart and later checks don't re-enter (lesson-3/5).
- `test_never_read_clock_starts_at_watching_event`: the first `check` writes one `watching` event, and a restart writes none. The trip enters only after unknown-after from that event's time (lesson-3).
- `test_unreadable_trip_inputs_hold_dispatch`: with `measurements.latest` raising, that look takes no lease and records nothing. When it reads again, dispatch resumes (lesson-3).
- `test_now_refused_under_pool_zero`: `Dispatcher.once` with freeze entered starts nothing, and the message names freeze.
- Existing `tests/test_cli_fallback.py` passes unchanged (lesson-7).

## Size budget

450 net lines (outside `tests/` and `docs/`): the operating package about 260, the CLI about 70, dispatch about 45, spec IR and compile hooks about 30, with room to spare.

## Notes from the plan review (answer each)

- Removing the whole `operating:` section while a state is entered drops the fold read (invariant 12) and silently lifts every state: dispatch goes back to full pool with no `left` in the record. This contradicts 'an undeclared entered state counts as pool 0 until it is left' and widens 'only the owner leaves a state' (lesson-3/8). Choose one: keep the fold read and `leave` whenever the record holds an `entered` with no later `left`; refuse to load a model that drops the section while a state is entered; or document that removing the section lifts all states and narrow the claim. Add a test for whichever is chosen.
- Unknown-after clock: the newest reading over all the part's sensors lets one live sensor hide a dead one forever (lesson-3 fail-open). Start the clock at the oldest of the per-sensor latest readings, count as `never` if any sensor was never read, and put the sensor in the spell (e.g. `unread:<sensor>:<time>`). Add a two-sensor case to test_unknown_after_trips_on_record_clock where one sensor goes silent and the trip fires.
- Say whether `Dispatcher.once` shares `take`'s post-TAKEN re-check. It must not nack a --now run under a state with pool >= 1 because of in-flight runs (once ignores block pool). Test pool 1 with one run in flight.
- Define how long 'that look's dispatch uses pool 0' lasts after unreadable trip inputs when tick runs more often than the once-a-second trip check: until the next trip check that reads cleanly.
- test_owner_leave_in_trip_gap: name the bug it guards (check skipping its write because the fold read showed the state entered), break exactly that, and report that the test fails.
- Docs: `pool-rises-with-rank` is for readability only, since in_force already takes the smallest pool among entered states. Don't present it as a safety guard (lesson-8).

## Where it stopped

Round 1: points 1 to 6 are built, and the acceptance tests pass (`tests/test_operating.py`, 29 tests, about 3 s).
The implementor did not run the full unit suite or the four browser files: the house rules leave those to the factory,
under the watchdog. No `origin` remote exists in this container. The branch is based on local `main` (dc0d5ac), so
merging that is a no-op. origin/main still has to be merged and the suites run again before review. No demo is
touched, so `demo_check` is not needed.

Choices made alone (the most reversible):

- **Removing the whole `operating:` section** (plan review, first note): documented, not refused. A model without the
  section reads nothing (invariant 12, and the acceptance test that `in_force` is never called), so removing it
  lifts every entered state with no `left` in the record. The record keeps the entries, so putting the section back
  holds them again. SPEC and the agent guide say this, and they narrow "only the owner leaves a state" to the
  CLI/fold check. Tested: `test_removing_the_whole_section_lifts_every_state_and_restoring_it_restores_them`.
  Refusing such a model at reload would be the stricter option; it needs the engine's reload path to read the record,
  and is left for a later gap if wanted.
- **Unknown-after clock**: per sensor, as the review asked. The clock starts at the oldest of the newest readings. A
  sensor never read uses the trip's `watching` event, which every `unknown-after` trip writes once on its first
  check. The spell is `unread:<sensor>:<repr of the stored time>` or `unread:<sensor>:never`. A sensor added later
  and never read starts from that old `watching` event, so it may trip at once (worst case, stated in SPEC).
- **`Dispatcher.once` shares the post-`TAKEN` re-check**, but only pool 0 gives a `--now` run back. Tested with
  pool 1 and one run in flight (`test_now_under_pool_one_with_a_run_in_flight_still_runs`).
- **Unreadable trip inputs** hold dispatch at pool 0 until the next trip check that reads cleanly
  (`Dispatcher.hold`).
- **The fold hook** is in `ergostat/spec/items.py`, 6 lines, beside the lease fold. It was not in the files list,
  but the item fold is where `entered`/`left` must be folded, so the item index and a direct fold agree. `operating`
  is added to `spec/load.py`'s `SECTIONS`, and to `schema/ergostat.schema.json` so the schema matches the SPEC.
- **The kind is `sealed`**: only `ergostat.*` event types fold into it.

Each test was checked by breaking the code it guards; each failed:

- the post-`TAKEN` re-read removed;
- re-entry not clearing the old fields;
- the newest reading used instead of the oldest;
- the rank check removed;
- the top state's pool used;
- `--now` not refused;
- check skipping its write when the fold showed the state entered (the bug `test_owner_leave_in_trip_gap` names);
- a `left` caused by a run accepted;
- an unreadable fold giving "none entered";
- the trip hold ignored;
- a `--now` run nacked for runs in flight;
- an undeclared state given no cap;
- `room = cap` in place of `min`;
- the `watching` event ignored;
- spells answered only while the state is entered (this broke both the crossing test and the restart test).

Not broken separately: part (b) of the restart test. There is no engine-start clock in the code to switch to; the
test pins the record clock with a fresh engine created 50 s after the reading.

Size: 447 net lines outside tests and docs (the schema counted).

Round 3 (the fix round for round 2's review, after main 7b39bc9 was merged in):

Merge: the factory's merge of main conflicted in six factory files. Each kept both sides: the groomer (the branch's
backlog) and the pipeline manager (main) in `dev/bin/agents.py`, `fac.py` and `dev/factory.toml`; the plan reviewer
given main's read-only tools; the planner's `takes:` with main's `to:` (no `planned`) and the backlog's
`unblocked: true, order: rank`; `gap.closed` commented for both; `messages.done` with main's `situation:` but `gap`
kept as `[merged, closed]`, because the backlog moved `parked` to `paused:` (the owner's rule). The factory tests of
those files pass (`test_factory_knowledge.py`, `test_factory_manager.py`: 52).

The two findings:

1. **Roll-up (and forgetting) took the answered spells and the watching clocks.** Fixed by the review's second
   option, exempting them. I also found and covered a third path the review didn't name: `prune` (past `keep`, 30
   days) forgets a `/` item whole once nothing is newer, and an unkinded item's (`goal.<name>`) old events. So a
   state left 30 days ago with its sensor still silent tripped again, and the watching events were deleted.
   `store.KEPT = "ergostat.operating."`: `rollup.batches` skips an item whose prefix holds such an event, and
   both backends' `prune` keep every event of those types (`store.Events.prune`'s two deletes, `segments.prune`'s
   `old`). SPEC §4b (*Keeping*) and §9.5 say so. Test:
   `test_rolled_up_and_pruned_record_still_answers_its_spells[segments|sqlite]`. It uses two states tripping on one
   goal, so there are two watching events on `goal.room`. It runs `rollup.compact(now=+8d)` and `prune`, then
   compact and prune again past +40 d, and checks after each that the entries, leaves and watching events are all
   still there. Then `check()` records no new entry, every state stays left, and no new watching event is written.
   Broken separately, each failed: the roll-up exemption removed (the owner's leave undone: `'entered' == 'left'`);
   the segments prune exemption removed; each of sqlite's two prune clauses removed (the leaves gone, and the
   watching events gone). Cost: those items' events are never archived, which is a few events per trip spell and
   per owner act.
2. **One unread spell per trip hid other sensors.** `_spells` now gives one spell per sensor past `unknown-after`
   (`unread:<sensor>:<time>` or `unread:<sensor>:never`, the never-read ones timed from the watching event). Each
   is answered on its own. The reviewer's case is a new test,
   `test_a_sensor_left_silent_never_hides_another_going_silent`. a goes silent, its spell is left, then b goes
   silent while a is still the oldest: b trips. The same holds with a never read and `unread:a:never` left. With
   only the first spell per trip emitted, this test fails, and so do the existing unread tests whose expectations
   now list a spell per sensor (`test_unknown_after…`, `test_restart…`, `test_never_read…`).

Not resolved, reported (lesson-7, lesson-13): **the branch base.** This branch was made from the container's local
`main` (dc0d5ac6, "Merge branch 'backlog'"), and the factory's main (7b39bc9) does not hold that merge. So
`git diff 7b39bc9...HEAD` also lands the backlog feature (`leases/ready.py`, `numbers/eta*.py`, `precedence.py`,
`cli/spec_cmds.py`, `leases/compile.py`, `pages.js`, `relations.js`, `style.css`, `ergostat.yaml`'s rank fields,
`dev/bin/backlog.py`…), as the other branches cut from that base do. The implementor's tools allow no rebase or
revert of it, and removing it is outside this gap. The coordinator has to either land the backlog first or recut
the branch on main and replay commits e94c6a20, 0848a040 and this round's.

Size: this gap's own code is 450 net lines (447 + 3 this round: trips −1, rollup +1, segments +1, store +2), exactly
the budget. Tests run this round, one file at a time: `test_operating.py` (33 including both parametrised cases),
`test_rollup.py`, `test_store_conformance.py`, `test_storage.py`, `test_cli_fallback.py`,
`test_factory_knowledge.py` and `test_factory_manager.py`, all passing; ruff clean. Not run by the implementor: the
full unit suite and the four browser files (the factory runs them under the watchdog). No demo is touched, so
`demo_check` is not needed. A stray empty file, `docs/roadmap/overnight/operating-states.md.tail`, was created by
mistake in this round and is untracked. It is not committed, and it can be deleted.

Round 4 (the fix round for round 3's review). Each finding, and what changed:

1. **The stray `operating-states.md.tail`** (blocking). The round 3 note above was wrong: commit 4f9f2f9d ("work
   the session left uncommitted") committed it. I could not delete it: this session's environment refused `git rm`
   and `rm` on it, and I did not try other ways around that refusal. It is still in the branch, one line ('x'), and
   nothing reads it. The coordinator should delete it (`git rm docs/roadmap/overnight/operating-states.md.tail`)
   or drop it in the recut below.
2. **The branch base** (blocking, the coordinator's). Still not resolved. Local `main` here is 7b39bc94 and
   `git merge-base --is-ancestor dc0d5ac6 main` fails, so the diff still lands the backlog feature and its
   `dev/model/` edits. I tried to recut the gap on `main` in a side branch (cherry-picking ee2ced77, e94c6a20,
   0848a040 and 543c7060), but this environment refused making the branch. The recut is the coordinator's: those
   four commits on `main`, without dc0d5ac6, the merge fix 293f937d (it edits main's `test_relations_asof.py` only
   to fit the backlog), and 4f9f2f9d (the `.tail` file). One thing to check during that recut: the gap's own
   `dispatch.py` hunks sit beside the backlog's `ready.ordered` calls in `tick` and `once`, so they may need
   resolving by hand there.
3. **The watching event note** (lines 146-148 above, non-blocking). It was wrong. `trips._spells` writes the
   watching event only when some sensor of the part is unread at that look, not on every `unknown-after` trip's
   first check. So a sensor added later starts from an earlier watching event if one exists, and may trip at once.
   If every sensor had been read until then, it starts from a fresh watching event written by the first look that
   finds it unread. SPEC §9.5 already said "written once by the first look that finds a sensor never read". Its
   last sentence about added sensors assumed an earlier event, so I made it state both cases. No code changed.
4. **Not run by the round 3 reviewer** (a note, not a finding). This round ran `tests/test_operating.py`: 32 passed
   (3.1 s). Round 3's "33" was a miscount. The collection lists 32, counting both parametrised cases of the roll-up
   test and the eight bad-state cases.

Size: unchanged, 450 net lines of the gap's own code (no code changed this round). Tests run this round:
`tests/test_operating.py` (32 passed), `tests/test_cli_fallback.py` (17 passed, unchanged), ruff clean. Not run:
the full unit suite and the four browser files (the factory runs them under the watchdog). No demo is touched, so
`demo_check` is not needed.

Round 4, after the factory's fast suites: `unit` was reported failed, but its tail ends at 45% with no `F`, no
error and no summary, so every worker stopped at once. That is the run being cut off (the watchdog or the slot's
time), not a test failing. I could not find a failure to fix:

- This environment refused running the whole suite (even under `suite_watch.py`), so I ran every unit file
  serially, in batches (`-p no:randomly -x`, each batch under a 590 s timeout): a–c 426 passed; d–g 313; h–m 273; n–r
  276; s 198; t–z 133; and separately the lease, dispatch, reload, store, rollup, daemon, spec, schema, architecture,
  docs, backlog and relations files (31 + 91 + 127 + 192). All passed. The only skips were the page tests (they
  belong to the browser suite). No batch came near its timeout.
- No thread leak from this gap: after `tests/test_operating.py` the process holds only its 4 usual threads
  (MainThread, the sampler, two sockets), from a probe test kept out of the tree.
- So no code changed. If `unit` stops again at the same point, the next step is the watchdog's JSON line (which
  limit it hit and its peak), which the tail didn't include.

The stray `.tail` file is still in the branch: `git rm` was refused again this round.

Round 4, after the fast suites a second time: `unit` was reported failed again. Its tail stops at 49% this time
(45% before), again with no `F`, no `E`, no traceback and no summary line. A stop at a different point with no
failing test looks like the run being killed by the watchdog or the slot's time limit, not like a test of this gap
failing. This session could not look further, because every shell command was refused, including `git`, `pytest`
and `ruff`. So no code changed, nothing was run, and this note is not committed (committing needs the shell). Reading
`tests/test_operating.py` turned up no unbounded wait: every engine is closed, and every wait has a deadline
(`wait_for`, 15 s). What is needed next: the watchdog's JSON line for this run (which limit it hit, and the peak
threads and memory), or the suite's per-test durations, to find the test it stopped on. The `.tail` file and the
branch base are still the coordinator's to fix (see above).

Round 5. The factory merged main (2388572a) in, and it conflicted in two files. Neither is this gap's, and in both
the branch side was the older text carried from the backlog base. Main's side holds everything the branch side said,
so main's side was taken in both: `dev/model/knowledge.yaml` (the planner's `pool: 12`, the operator's setting) and
`ergostat.yaml` (main's rewording of the `gap.closed` comment). Commit 0bccaffb.

The two findings:

1. **The stray `operating-states.md.tail`** (blocking). Still in the branch. `git rm` was refused again this round,
   and I did not try other ways around the refusal. The coordinator has to run
   `git rm docs/roadmap/overnight/operating-states.md.tail`. It is one line ('x'), and nothing reads it.
2. **The branch base** (blocking). Resolved in content by this merge. Main now holds the backlog's content, so
   `git diff 2388572a...HEAD --stat` is only this gap's 22 files (+1485/−16): `ergostat/operating/`, the
   `cli/operating.py` topic, `dispatch.py`, the spec hooks, `rollup.py`/`segments.py`/`store.py` (round 3's
   keeping), the schema, SPEC, the agent guide, GAPS, this file, `tests/test_operating.py` and the `.tail` file.
   No `dev/model/`, backlog, `ready.py`, eta or UI file is in the diff any more. The history still contains
   dc0d5ac6 (`git merge-base --is-ancestor dc0d5ac6 main` still fails), but merging lands nothing outside this
   gap except the `.tail` file.

No code changed this round. Tests run after the merge, one file group at a time: `tests/test_operating.py` and
`tests/test_cli_fallback.py` (49 passed); `tests/test_factory_knowledge.py`, `tests/test_factory.py` and
`tests/test_daemon_yaml_review.py` (the files the merge touched: 119 passed, 2 skipped); ruff clean. Not run by the
implementor: the full unit suite and the four browser files (the factory runs them under the watchdog). No demo is
touched, so `demo_check` is not needed.

Round 6 (the fix round for review operating-states-4). This session's shell was refused from its first command, so
it ran no `git`, `pytest` or `ruff`, and committed nothing: the edits below are in the working tree, uncommitted.
Each finding:

1. **The stray `operating-states.md.tail`** (blocking). Still in the branch. `git rm` was refused once more (the
   whole shell was), and the file tools can't delete a file. The coordinator has to run
   `git rm docs/roadmap/overnight/operating-states.md.tail` and commit.
2. **A trip write that raises left the old hold** (non-blocking, `dispatch.py` `Dispatcher.trip`). Fixed:
   `trips.check` is now called in a `try`, and any exception, a write's included, sets `hold` ("the trips could not
   be checked: …"), so that look dispatches at pool 0 until a check runs cleanly. New test
   `test_a_trip_write_that_raises_holds_dispatch`: `p.events.add` raises for `ergostat.operating.*`, so the watching
   write fails after a clean read. Then `hold` names the failure and `tick` takes no lease. Not run, and not checked
   by breaking the fix, because the shell was refused. Without the fix the OSError leaves `trip()` and the test
   fails with that error.
3. **Not run by the round 4 reviewer** (a note). Not run this round either, for the same reason.

Size: 453 net lines, 3 over the 450 budget. The reason: the `try`/`except` the review asked for, and nothing else
could go to make room for it. What has to happen next (needs a shell): commit the working tree, `git rm` the `.tail`
file, run `tests/test_operating.py` (and break the new `try` once to see the new test fail), `tests/test_cli_fallback.py`
and ruff.

Round 7 (the fix round for review operating-states-5). Round 6's working tree was committed as 701bcbdf. Each finding:

1. **The stray `operating-states.md.tail`** (blocking). Still in the branch. This session ran `git status`, pytest and
   ruff, but `git rm` on that file was refused twice (once on its own), and I did not try other ways around the
   refusal. The coordinator has to run `git rm docs/roadmap/overnight/operating-states.md.tail` and commit. Nothing
   else in the branch is waiting on it.
2. **Not run by the round 5 reviewer** (a note). This round ran them: `tests/test_operating.py` 33 passed (3.1 s),
   with `tests/test_cli_fallback.py` 50 passed together. Ruff is clean. Round 6's `try` in `Dispatcher.trip` was
   checked by breaking it (`except KeyError` in place of `except Exception`).
   `test_a_trip_write_that_raises_holds_dispatch` then failed. With the `try` restored, it passes.
3. **Scope** (a note). No change. As round 4 said, `store.py`, `segments.py`, `rollup.py`, `spec/items.py`,
   `spec/load.py` and the schema are each needed by the definition.
4. **The watching event's item is `goal.<name>`, while `loop.*` events use the bare goal name** (non-blocking). No
   change, and this is the more reversible choice. Reading and writing agree, and SPEC §9.5 documents
   `goal.<name>`. Renaming it now would orphan every watching event already in a record, which would restart a
   never-read sensor's clock (lesson-3). If wanted, it could be renamed later, with a read of both ids.

Size: unchanged, 453 net lines (3 over the budget, for the reason given in round 6). Not run by the implementor: the
full unit suite and the four browser files (the factory runs them under the watchdog). No demo is touched, so
`demo_check` is not needed.

Round 7, after the fast suites: `unit` was reported failed. Its tail stops at about 2191 of about 2204 results (the
99% line), with no `F`, no `E`, no traceback, no pytest summary and no `suite_watch` JSON line (the watchdog prints
one whenever it kills a run or the run ends). The run was cut off from outside, as in round 4 (45%, then 49%).
I found no failing test to fix, so no code changed:

- This session could not run the unit command itself. `suite_watch.py … pytest -n 8` was refused, and so was a
  multi-file run with `--durations`. It could run single commands: `tests/test_operating.py` (33 passed, 2.9 s),
  `tests/test_leases.py` + `tests/test_cli_fallback.py` + `tests/test_rollup.py` (88 passed, 75 s), and ruff
  (clean). The collection holds 2121 tests in `tests/`.
- The slowest tests in those files belong to main, not this gap. `test_leases.py::test_a_lease_held_by_a_run_survives_a_model_edit`
  takes 14 s, by its own design (two runs one after the other, each ten CLI calls with a 0.5 s sleep). The
  model it uses has no `operating:`, so this gap's code is never read there (invariant 12, and
  `test_compile_example_and_kind_only_when_declared`).
- What is needed next: the watchdog's JSON line, or the run's wall time against the slot's limit. If the slot
  stops the run at its time limit, the suite needs more time or fewer tests, not a fix in this gap (lesson-13).

The stray `.tail` file: `git rm` was refused once more this round. The coordinator has to run
`git rm docs/roadmap/overnight/operating-states.md.tail`.

Round 7, after the fast suites a second time: this time `unit`'s tail showed two real `F`s (at about 3%), so the
cause was found. The whole of `tests/` was run serially (`-p no:randomly`): 6 failed, 2011 passed, 69 skipped, plus
the 41 `slow` tests (41 passed, 6 skipped). The failures were
`test_index_files.py` (four tests that spawn a second process), `test_store_conformance.py::test_a_second_instance_threads_and_processes_lose_nothing[sqlite]`
and `test_runner_and_state.py::test_a_run_past_its_timeout_is_stopped_with_what_it_started`. Each spawned process
dies with `AttributeError: module 'queue' has no attribute 'LifoQueue'`. Those three files pass on their own (86
passed). Running `tests/test_backlog.py` before them reproduces the failures (5 failed). The cause is
`tests/test_backlog.py:24`. It does `sys.path.insert(0, dev/bin)` and never takes it out again, so a process spawned
later in the same pytest worker imports `dev/bin/queue.py` in place of the standard library's `queue`. Under `-n 8`,
any worker that runs a backlog test before a spawning test fails this way. Neither file is in this branch's diff
(`git diff 512f08ef...HEAD --stat`), so main fails the same way. It belongs in its own gap (lesson-13), and no code
changed here. The fix: `test_backlog.py` loads `dev/bin` modules without leaving the path changed (monkeypatch
`sys.path`, or load them by file path as the other factory tests do).

Round 8 (the fix round for review operating-states-5's one blocking finding, the stray `.tail` file). This
session's shell was refused from its first command, `git rm` on that file included (twice), and the file tools
cannot delete a file or commit. I did not try other ways around the refusal. So the file is still in the branch,
nothing else changed, and this note is in the working tree, uncommitted. No code changed, so nothing was run this
round (the round 7 runs stand: `tests/test_operating.py` 33 passed, `tests/test_cli_fallback.py` passing, ruff
clean). What the coordinator has to do, two commands with no other effect:
`git rm docs/roadmap/overnight/operating-states.md.tail`, then commit it with this note. Nothing else in the
branch waits on it. The other findings of review operating-states-5 were answered in round 7 and are unchanged.
No demo is touched, so `demo_check` is not needed.

Round 9, after the fast suites (`unit` cut off at 84%, no `F`, no summary). The stray `.tail` file is gone (commit
4d6834ea). The cause of the stop is on main, not in this gap. I ran the unit files serially in batches
(`-p no:randomly`): a–c 457 passed; s–z 461 passed; d–k stopped at
`tests/test_index_files.py::test_two_processes_one_tidying_never_corrupt_an_index_another_has_open`. Its spawned
children die with `ImportError: cannot import name 'Empty' from 'queue' (/work/dev/bin/queue.py)`, and the parent
waits on them for about a minute. It reproduces with two of main's tests alone:
`tests/test_factory.py::test_two_gaps_editing_gaps_md_merge_cleanly` and then that index test (1 failed, 68 s). Run
alone, `tests/test_index_files.py` passes (8). `tests/test_factory.py:2998` and `tests/test_backlog.py:24` put
`dev/bin` on `sys.path` and never take it out again, so `dev/bin/queue.py` shadows the standard library's `queue` in
every process spawned later in that pytest worker. Under `-n 8`, the workers that reach a spawning test after one of
these fail or stall, at a point that changes from run to run (45%, 49%, 84%). Neither file is in
`git diff main...HEAD`, so main fails the same way. Per lesson-13 I did not change it here. The fix belongs in its
own gap: load the `dev/bin` modules with `monkeypatch.syspath_prepend` (or by file path), or rename
`dev/bin/queue.py`. No code changed in this round. Run: `tests/test_operating.py` + `tests/test_leases.py` (64
passed). h–r was not finished: the d–k batch stopped at the failure above.

## Where it stopped

Parked by the factory (review/operating-states-6, 2026-11-21 00:31).

Failed its gates 6 times (the kill rule). Blocking findings:
- docs/roadmap/overnight/operating-states.md.tail: the stray scratch file (one line, 'x') is still committed and still in `git diff origin/main...HEAD --stat`. It was raised as blocking in rounds 3, 4 and 7, and neither commit since (ec632425, e9f9cada) touches it. A committed scratch file would land on main, which people install from. Fix: `git rm docs/roadmap/overnight/operating-states.md.tail`, by the coordinator if the implementor's tools refuse it.

Round 9 (resumed after the park, review/operating-states-6). Its one blocking finding, and what changed:

1. **The stray `operating-states.md.tail`** (blocking). Removed: `git rm` was allowed this time, and this round's
   commit deletes it.

Also found this round: after the factory's merge of main (bfdb0552),
`test_state_entered_between_check_and_take_gives_back` failed. Main's `take` now adds the run's key to
`Engine.running` (and the run to `ours`) before the `TAKEN` write. The give-back after the post-`TAKEN` re-read
returned without removing them, so the item stayed marked as running in this engine. No program ran (the lease ended
nack, and the test's other assertions held). Fixed in `dispatch.py`: the give-back now shares the cleanup of the
"someone else took it first" branch. That is 0 net lines, so the size stays at 453, 3 over the budget for round 6's
reason. The test failed before the fix and passes after it.

Tests run this round: `tests/test_operating.py`, `tests/test_cli_fallback.py` and `tests/test_leases.py` (81
passed); ruff clean. Local `main` has nothing the branch lacks, and there is no `origin` remote in this container.
Not run by the implementor: the full unit suite and the four browser files (the factory runs them under the
watchdog). No demo is touched, so `demo_check` is not needed.

Round 9, after the fast suites again (`unit` cut off at 96%, with no `F`, no error and no summary). No code changed.
The cause is still main's, and I reproduced it at this HEAD: `tests/test_backlog.py` then `tests/test_index_files.py`
(`-p no:randomly -x`) gives 1 failed, 16 passed in 151 s. The index test's spawned children die with `ImportError:
cannot import name 'Empty' from 'queue' (/work/dev/bin/queue.py)`, and the parent waits on them. Five places in the
tests leave `dev/bin` on `sys.path` in-process: `tests/test_backlog.py:24`, `tests/test_factory.py:2998`,
`tests/test_factory_knowledge.py:122` and `:707`, and `tests/test_factory_times.py:36`. None of those files, and
nothing in `dev/bin/`, is in `git diff main...HEAD`. So main stalls the same way under `-n 8` wherever a worker
reaches a spawning test after one of them. Per lesson-13 it is not fixed here. Its own gap should use
`monkeypatch.syspath_prepend` in those five places (as `tests/test_factory.py:439` already does), or rename
`dev/bin/queue.py`. Until then this branch's `unit` run can't pass, whatever the branch contains.

Round 10 (the merge of main 07f9b250, which conflicted in `ergostat/leases/dispatch.py`). Both sides were kept. The
`Dispatcher` fields are main's `mine` and `unread` plus the branch's `hold`. A block's room in `tick` is now
`min(pool_now(b), cap) − in flight`: main's pool (`pool:` or its stock's level, `pool_now`), capped by the state in
force. So a state still never raises a block's pool. Merge commit 83ed9b9b. No other code changed, so the size is
unchanged (453 net lines). Tests run after the merge: `tests/test_operating.py` and `tests/test_cli_fallback.py`
(50 passed), `tests/test_pool_now.py` (25 passed), `tests/test_leases.py` (37 passed), and ruff is clean. In its
first run, `tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere` failed once. It
passed alone, and the whole file passed when run again. It is main's test, its model declares no `operating:`, and
it is not in this branch's diff, so it is reported here and not fixed (lesson-10, lesson-13). Not run by the
implementor: the full unit suite and the four browser files. No demo is touched, so `demo_check` is not needed.

Round 11 (the queue's finding: the merge of main 9b993691 brought in main's library-trust allowlist, and
`tests/test_library_trust.py::test_every_compile_key_classified` failed, alone too, because the new `operating:`
section was not classified). Fixed in `ergostat/library/trust.py`: `operating` is in `REFUSED` ("operating states,
which cap or stop every block's pool"). A template from a folder the owner did not mark trusted may not declare
operating states, since a state can stop every pool or trip a freeze. This is the fail-closed choice, and the more
reversible one: allowing it later is one line. SPEC §2a already says any section not listed as allowed is refused, so
no doc changed. +1 line, so the size is 454 net lines, 4 over the budget (round 6's reason, plus this line). The test
failed without the line and passes with it. Tests run: `tests/test_library_trust.py` (48 passed),
`tests/test_operating.py` and `tests/test_cli_fallback.py` (51 passed), and ruff is clean. Not run by the implementor:
the full unit suite and the four browser files. No demo is touched, so `demo_check` is not needed.

Round 12 (the fix round for review operating-states-9). Each finding:

1. **`docs/GAPS.md`, the spliced "Operating modes…" entry** (blocking). Rewritten as one entry: the designed-in
   line once, one *Done* (act-risk gating on `act-risk-gating`, SPEC §12k; operating states and trips capping the
   pool on `operating-states`, SPEC §9.5) and one *Left* (gates by state, bypass leases, P3/T1, presence, thresholds
   scheduled by regime, reshaping an act, the staleness of the state an act was planned on). This replaces the
   wording definition §6 gave, since main has since built act-risk gating; the review asked for this form.
2. **`take()`'s re-check outside the `try`** (non-blocking). Fixed: the post-`TAKEN` decision, `entered_meanwhile`
   included, is now inside the `try`, so a raise in its `flying()` read or its `ENDED` write clears the key from
   `e.running` and re-raises. `self.ours` is kept on that path, as main's own `except` already does for a `TAKEN`
   write that raises: the lease is then reaped at its ttl and counted (fail closed); changing that is main's path,
   not this gap's. New test `test_a_recheck_that_raises_after_taken_leaves_nothing_running`. With the call moved
   back outside the `try`, it failed; restored, it passes. +1 net line, so 455 net lines, 5 over the budget (round
   6's and round 11's reasons, plus this line).
3. **SPEC §9.5, "Only the owner leaves a state"** (non-blocking). Now reads "Only the owner leaves a state (or
   removes the section, above: a change the model's judge accepted can do that too)".
4. **SPEC §9.5 wrapping** (non-blocking). The opening paragraph is reflowed.

Tests run: `tests/test_operating.py`, `tests/test_cli_fallback.py` (52 passed), `tests/test_operating.py` with
`tests/test_leases.py` (71 passed); ruff clean. Not run by the implementor: the full unit suite and the four browser
files. No demo is touched, so `demo_check` is not needed.

Round 13 (the merge of main 4a1bcd10, which conflicted in `ergostat/spec/compile.py`). Both sides were kept: the
branch's `operating.section` call, then main's new `bounds.check` (an untrusted library's limits), in that order.
Merge commit 6db665b0. No other code changed, so the size is unchanged (455 net lines, for the reasons given in
rounds 6, 11 and 12). Tests run after the merge: `tests/test_operating.py`, `tests/test_cli_fallback.py` and
`tests/test_library_trust.py` (100 passed), `tests/test_leases.py` (37 passed), `tests/test_library_untrusted.py` and
`tests/test_library_untrusted_runs.py` (30 passed); ruff clean. Not run by the implementor: the full unit suite and
the four browser files. No demo is touched, so `demo_check` is not needed.
