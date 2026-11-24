# operating-gates: an action's gate scheduled by the operating state in force, and owner-granted bypass leases on a class, decided once under one lock at request and again at the command's start
depends-on: [operating-states]

This builds on `operating-states`, which is leased and not on main. From that gap it uses two things: the reader of the operating state in force (called `current(p, spec)` below) and the acts that enter and leave a state (`enter`, `leave`). It also uses that gap's declared state names, with the default state that a model starts in (`normal`). If those functions have other names when that gap lands, the implementor uses them; the definition below holds on behaviour, not on names. Presence (owner away), the act-risk step (`act-risk-gating`) and the budget permissive (`run-budget-permissive`) are not part of this gap.

## Definition of done

1. **A gate map.** An action's `gate:` (SPEC §12k) is either a plain `auto | approve | deny`, unchanged and the same in every state, or a map from a declared operating state to one of those values, with an optional `else:`. Example: `gate: {normal: auto, freeze: approve, else: deny}`. The compiler (`actions/compile.py`) reports each mistake with its location:
   - a key that is not a declared state or `else` → `unknown-ref`;
   - a value outside the three → `bad-value`;
   - a map with no `else` that leaves a declared state out → `gate-uncovered`;
   - a map in a model that declares no operating states → `gate-needs-states`.

   `Action.gate` becomes `str | dict[str, str]`. A plain-string gate never reads the state or takes the lock below, so the behaviour of existing models and their tests does not change.
2. **One resolution.** One function decides an action's gate everywhere: `ergostat/actions/schedule.py: resolve(action, state, bypasses, now) -> (gate, why)`.
   - `state` is the state that was read, or `None` when it could not be read.
   - `bypasses` maps a class to its `until`, as read by `standing(p, now)`.
   - `now` is an injected clock.

   The rules:
   - A plain gate resolves to itself.
   - For a map, `state is None` resolves to `deny`. A state that has no key in the map and no `else` also resolves to `deny`, even though the compiler's check should have prevented that map. A model can change after it was checked, so the run-time answer is the strictest one.
   - Otherwise the result is the map's cell for the state (or `else`). If the action's class has a standing bypass, the result is instead the looser of that cell and the cell for the default state. A bypass is standing when `until > now`, strictly.
   - Strictness order: `auto < approve < deny`. A bypass never makes a gate looser than its default-state cell. With no bypass, the result is exactly the cell.

   `request`, `run_once` and the `ergostat actions` class table all call `resolve`. None of them works out a state or a bypass on its own.
3. **The operating lock.** `schedule.lock(p, exclusive)` is `fcntl.flock` on `<state dir>/operating.lock`.
   - Entering or leaving a state (operating-states' `enter`/`leave`, wrapped there) and granting or ending a bypass take it **exclusive**. They hold it across their read, decision and write.
   - The gate's decisions take it **shared**.

   So no act reads a state or bypass while one is being changed, and no state or bypass changes between an act's re-check and its command's start.
4. **At request** (`gate.request`), for a map gate: under the shared lock, the gate reads the state with `current`, reads `standing(p, now)`, calls `resolve`, and records the step `denied`, `approved` (by `gate`) or held, as today. `requested` also records the resolved `gate` and the `state` it was read in. A reader that raises, or that returns a name that is not declared, counts as `state=None`, which resolves to deny.
5. **At the act** (`gate.run_once`), after the existing run-once file and `fenced`: under the shared lock, held from the re-read until the child process has started, the gate re-reads the state and the standing bypasses and calls `resolve` again.
   - An approval by `gate` (auto) still holds only if the result is still `auto`.
   - The owner's approval holds if the result is `auto` or `approve`.
   - `deny` refuses every approval.

   A refused action is recorded `failed` with `exit: None`, `seconds: 0` and `refused: <why>`, and its command never starts. The spawn step is a separate function, `gate._spawn(command, cwd, env) -> Popen`. The lock is released when `_spawn` returns. The run then continues outside the lock with `communicate(timeout)`, so a state change waits only for the start, not for the whole run. On timeout, the gate kills the child's process group (`os.killpg`) and collects what is left. It records the same `ran`/`failed` fields as today.
6. **Bypass leases.** Command: `ergostat bypass CLASS --for DUR [--note TEXT]`, `ergostat bypass CLASS --end`, and `ergostat bypass` to list the standing ones.
   - Each bypass is a built-in item `ergostat.bypass/CLASS`, with events `ergostat.bypass.granted` (`until`, `by`, `note`) and `ergostat.bypass.ended`. Its kind is registered beside `action_kind`, so it shows in the Items tab and needs no new page.
   - `CLASS` must match the name pattern and be the class of at least one action with a map gate (an allowlist). Any other class is refused with rc 2 and nothing is recorded.
   - `DUR` must be greater than 0 and at most 24 h. The grant is refused beyond that. `standing()` enforces the cap again when it reads: `until` is clipped to the grant event's time + 24 h.
   - A grant made again after an end gives a fresh lease. The fold clears `ended`/`ended_by` on a new grant. Grants and ends are ordered by the record's sequence, never by their times.
   - `standing(p, now)` treats any of these as no bypass (the stricter gate): an item that cannot be read, a grant whose data is not an object, an `until` that is missing, not a number, NaN or infinite, and a query that raises.
   - Standing bypasses show in `ergostat bypass`, in the `ergostat actions` class table (gate in force, with "bypass until HH:MM") and on the item.
7. **A bypass is the owner's act.** Two checks enforce this:
   - **(a)** The new type is `ergostat.bypass.*`, so the existing `runner.OWN_TYPES` refusal already turns it away from every path an agent writes events through: `intake/envelope.parse` (`POST /api/events` and the engine's socket `calls/ops.event`), `ergostat event --add` (`cli/record.add_event`) and MCP `record_event` (`mcp.py`). A block's event line goes through the same check.
   - **(b)** `ergostat bypass` grants and ends refuse, with rc 2 and nothing recorded, when the caller has `ERGOSTAT_RUN` in its environment. That is the mark the engine gives every run it starts (`runner.py:293`, `spec/engine.py:884`).

   Neither the MCP server nor the web server offers a bypass. SPEC says the scope plainly: these checks refuse every agent path that writes the record and every caller that carries a run's mark. An unsandboxed process that strips its own environment is not stopped by them; the boundary against that is the gated session's sandbox (§12k).
8. `bypass` is its own CLI topic, not in `goodmodel.READS`, so the read-only fallback never runs it. `tests/test_cli_fallback.py` still passes.
9. Docs:
   - SPEC §12k: gate maps, resolution, the lock, the run-time re-check and the bypass leases, with the scope of item 7 stated as above.
   - The agent guide: how to write a gate map.
   - GAPS: a line under "Operating modes, regime-scheduled thresholds, interlocks, risk gating" saying what this gap built and what is left.
10. Done in the house sense: the acceptance tests pass, the unit suite and the four browser files pass with rc 0, ruff is clean, origin/main is merged in and the suites are run again. Each new lock or re-check test was run once with its guard removed, and the report says that it failed then.

## Files to touch

- `ergostat/actions/schedule.py` (new: `resolve`, `standing`, `lock`, `grant`, `end`)
- `ergostat/actions/gate.py` (request and run_once under the lock; `_spawn`; Popen with process-group kill)
- `ergostat/actions/compile.py` (gate maps)
- `ergostat/spec/ir.py` (`Action.gate` type; `BYPASS` kind beside `action_kind`, registered where the built-in kinds are)
- operating-states' module that holds `enter`/`leave` (wrapped in `schedule.lock(p, exclusive=True)`)
- `ergostat/cli/gated.py` (`bypass` topic; class table uses `resolve`)
- `ergostat/cli/__init__.py` (register the topic, if registration lives there)
- `docs/SPEC.md`, `docs/AGENT-GUIDE.md`, `docs/GAPS.md`
- `tests/test_operating_gates.py` (new)

## Risks

- **lesson-1.** Request and act each read the state and bypasses, decide and then write or start. A freeze entered, or a bypass ended, between the re-check and the start would let the act through. The guard is the shared lock from the re-check to `_spawn`'s return, with exclusive locks on enter, leave, grant and end. Both orders are tested by putting the competing write in the gap.
- **lesson-3.** The unreadable inputs and their worst cases: the state (read fails or the name is undeclared → deny, even for an owner-approved action), a map cell (missing with no `else` → deny), and a bypass (unreadable, corrupt or with a bad `until` → none).
- **lesson-2.** Bypass grant and end ordered by time instead of by sequence; a grant and an end in the same second. The fold orders them by sequence, and the test makes the stamps equal.
- **lesson-4.** A bypass with no ceiling. 24 h is enforced at grant and again at read.
- **lesson-5.** `ergostat.bypass/CLASS` reused: an old `ended` surviving a new grant, or an old `until` reviving after an end.
- **lesson-6.** Moving to Popen could leave a timed-out command's children running. The process group is killed.
- **lesson-7.** A new topic not classified for the fallback, or a clash with operating-states' enter/leave. The branch merges main and runs the suites again; the fallback test stays green.
- **lesson-8.** The claim that a bypass is "owner only" is stated no wider than the checks in item 7. "Never looser" is held by an exhaustive test.
- **lesson-9.** Each lock or re-check test is broken by removing its guard, and the report says it failed then.
- **lesson-10.** The lock tests order things by events and lists, not sleeps. A bounded wait can only run out in the direction where the test passes.
- **lesson-11.** `CLASS` becomes an item id. It is validated by the name pattern and an allowlist of map-gated classes; no path is built from it.

## Acceptance tests

All in `tests/test_operating_gates.py`.

**Gate maps and resolution**
- `test_gate_map_compiles_and_errors`: a good map compiles. A bad key gives `unknown-ref`, a bad value `bad-value`, an uncovered state without `else` `gate-uncovered`, and a map with no declared states `gate-needs-states`. A plain gate is unchanged. Fails if any of the four checks is dropped.
- `test_resolve_missing_state_or_cell_denies`: `state=None`, an undeclared state, and a state missing from a map with no `else` (built by hand, bypassing the compiler) all resolve to `deny`, including for a map whose other cells are all `auto`. Fails if the fallback is `auto`, `approve` or `else`-less defaulting (lesson-3).
- `test_resolve_never_looser`: for every map over three states with cells drawn from the three gates (27 maps), and for every state with and without a standing bypass, plus `until == now`: with no bypass the result equals the cell; with a bypass it equals the looser of the cell and the default-state cell, never looser; `until == now` is not standing. Fails if a bypass loosens past the default state or `>=` is used for standing (lesson-8).

**Request, and the re-check at the act**
- `test_request_scheduled_by_state`: one action with map `{normal: auto, freeze: approve, else: deny}`. Its command touches a marker file. In normal it runs at once. In freeze it is held. In incident it is denied, and `state` is recorded each time.
- `test_released_then_state_changed_not_run`: a program asker's action is auto-approved in normal; freeze (cell approve) is then entered; `run_once` records `failed` with `refused`, and the marker is absent. Fails if the gate's approval is not re-checked at the act.
- `test_owner_approval_refused_when_state_denies`: held in freeze, the owner approves while a waiter marker stops it running at once. The state then moves to a deny state. `run_once` refuses, unrun.
- `test_unreadable_state_refuses_owner_approved`: `current` is monkeypatched to raise `OSError`, and in a second case to return an undeclared name. Then: an owner-approved action fails unrun with `refused`, and a fresh `auto`-in-normal request is recorded denied. Fails if an unreadable state is read as the default (lesson-3).

**The lock**
- `test_state_entry_waits_for_command_start`: `gate._spawn` is monkeypatched. The patch starts a thread that calls the locked `enter(p, "freeze")`, waits up to 2 s on that thread's done-event, appends `"spawned"` and calls the real `_spawn`. The thread appends `"entered"` when `enter` returns. Asserts: the order is `["spawned", "entered"]`, the action ran (it was re-checked in normal), and the thread finished after `run_once` released the lock. With the lock removed from `run_once`, or `enter` not exclusive, the order is `["entered", "spawned"]` and the test fails (checked and reported; lesson-1, lesson-9).
- `test_act_waits_for_state_entry`: operating-states' write inside `enter` is monkeypatched to start a thread calling `run_once` on an owner-approved action whose freeze cell is `deny`, then wait up to 2 s on that thread before writing. Asserts: `run_once` returns after the write and records `failed`/`refused`, and the marker is absent. With the locks removed, it runs on the old state and the marker exists (lesson-1).
- `test_bypass_end_waits_for_command_start`: the same structure as the first lock test, with `ergostat bypass CLASS --end` in the thread. It shows that the end lands after the start, and fails with the exclusive lock removed from `end`.

**Bypass leases**
- `test_bypass_lets_class_through_until_end`: freeze cell `deny`, normal cell `approve`. With a bypass granted, a request in freeze is held instead of denied; the owner approves and it runs. After `--end`, a new request is denied.
- `test_bypass_ended_before_start_fails_unrun`: released in freeze with a bypass standing (owner approval, waiter marker set). Two variants, ended before `run_once` either by `bypass --end` or by the injected clock passing `until`. Both are recorded `failed` with `refused`, and the marker is absent. Fails if `run_once` does not re-read the bypasses inside the lock.
- `test_bypass_corrupt_counts_as_none`: grant events written straight to the store with data that is not an object, with `until` missing, `"soon"`, NaN or inf, and a `p.events.query` that raises `OSError`. Each gives `standing() == {}`, and a freeze request is denied. Fails if a bad bypass counts as standing (lesson-3).
- `test_bypass_ceiling`: `--for 25h` and `--for 0` are refused with rc 2 and no event. A grant written straight to the store with `until` 48 h after its event is standing only until event time + 24 h. Fails if either check is dropped (lesson-4).
- `test_bypass_regrant_and_same_second_order`: grant, end and grant, all with the same `time` stamp. The bypass is standing and `ended` is cleared. Grant then end with equal stamps: it is not standing. Fails if ordered by time, or if old fields survive (lesson-2, lesson-5).
- `test_bypass_refused_from_a_run`: `ergostat bypass CLASS --for 1h` and `--end`, run with `ERGOSTAT_RUN` set, exit rc 2, and the record holds no `ergostat.bypass.*` event.
- `test_bypass_events_refused_from_agents`: `ergostat event --add ergostat.bypass.granted --item ergostat.bypass/C`, MCP `record_event` with that type, and `intake.envelope.parse` with it are each refused, and nothing is recorded. Fails if the type escapes `OWN_TYPES`.
- `test_bypass_class_allowlist`: an unknown class, a class whose gates are all plain, and `../x` are each refused with rc 2 and no event (lesson-11).

**Status and the run step**
- `test_actions_table_shows_gate_in_force`: under freeze with a bypass standing, `ergostat actions` shows the class's resolved gate with "bypass until". `resolve` is monkeypatched to a sentinel to show the table calls it.
- `test_run_timeout_stops_its_group`: a command that starts a background `sleep` and writes its pid, run with a 1 s timeout, ends `failed` with the timeout note, and the background pid is gone. Fails if only the child is killed (lesson-6).

**Unchanged**
- `tests/test_gated_actions.py`, `tests/test_program_actions.py` and `tests/test_cli_fallback.py` all pass without changes (plain gates unchanged; lesson-7).

## Size budget

380 net lines of code outside `tests/` and `docs/`.

## Notes from the plan review (answer each)

- test_bypass_regrant_and_same_second_order: equal stamps cannot catch a stable sort by time (insertion order == seq). Add a case where the later-seq event has an EARLIER time stamp (grant@t, end@t-5 → not standing; end@t, grant@t-5 → standing), so ordering by time fails the test (lesson-2/lesson-9).
- schedule.lock must open a fresh fd per acquisition (flock conflicts are per open file description); a cached/shared fd makes same-process threads never block and the lock tests meaningless. Also ensure no code path takes the lock again while holding it (enter/leave/grant/end must not call each other under the lock) — state this and keep it from deadlocking.
- Only `end` (of grant/end) and `enter` (of enter/leave) have a race test. Either add the analogous tests for grant and leave or state in SPEC/report that they only loosen and a race there is strictness-only; the 'exclusive on all four' claim must otherwise be backed by a failing-when-removed test (lesson-8/9).
- Popen must use start_new_session=True (or setsid) for os.killpg to hit the group and not the caller's group; test_run_timeout_stops_its_group should poll with a deadline (failing only by timeout in the pass direction is not allowed — here a timeout must FAIL) and treat a zombie/reaped pid as gone.
- The wrapper around operating-states' enter/leave touches another gap's module that is not on main; the report must say how the wrap matched that gap's final names and that its suite still passes after merge (lesson-7).
- Bypass --for: negative, unparseable and absurd units are refused with rc 2 and no event, not only 0 and 25h; add to test_bypass_ceiling.
- --end on a class that no longer has a map gate is refused by the allowlist; decide (and document) whether listing/ending such a stale bypass is allowed, since ending should never be blocked by a check meant to stop loosening.
