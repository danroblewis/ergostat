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

## Where it stopped

Built, round 1. Every item of the definition is in the code. The size is 277 net lines in `ergostat/` and 5 in
`schema/` (budget 380). The 20 acceptance tests are in `tests/test_operating_gates.py`, with one more,
`test_bypass_never_runs_on_the_fallback`. That makes 31 cases with the parametrized ones, and all pass.
`tests/test_gated_actions.py`, `tests/test_program_actions.py` and `tests/test_cli_fallback.py` pass unchanged, and
so do `test_regime_gates`, `test_operating`, `test_act_risk`, `test_act_reshape`, `test_leased_workspaces`,
`test_inbox`, `test_spec_schema` and `test_spec_structure`. Ruff is clean. `HEAD..main` is empty, so there was nothing
to merge.

Not run here: the unit suite and the four browser files (the factory runs them). No page changed.

**Each guard broken by hand, and the test seen failing** (each then put back):
- `run_once` without the shared lock: all three lock tests failed (`['entered', 'spawned']`, the act returning before
  the write, `['ended', 'spawned']`).
- `enter` taking the lock shared: `test_state_entry_waits_for_command_start` and `test_act_waits_for_state_entry`
  failed. `end` taking it shared: `test_bypass_end_waits_for_command_start` failed.
- No re-check at the act: `test_released_then_state_changed_not_run`, `test_owner_approval_refused_when_state_denies`
  and both cases of `test_bypass_ended_before_start_fails_unrun` failed.
- `standing` sorted by time: the regrant test failed on grant@t, end@t-5.
- The read-time clip at grant + 24 h removed: `test_bypass_ceiling` failed.
- `until >= now` as standing: `test_resolve_never_looser` failed.
- `r.kill()` instead of `os.killpg`: `test_run_timeout_stops_its_group` failed at its deadline.
- The `gate-uncovered` check dropped: `test_gate_map_compiles_and_errors` failed.
- An unread state read as `normal`: `test_unreadable_state_refuses_owner_approved[raises]` failed.
- The finite-number check in `standing` dropped: the `inf` case of `test_bypass_corrupt_counts_as_none` failed.
- The class allowlist dropped: `test_bypass_class_allowlist` failed.
- Not broken separately: a cached lock fd. The lock tests run their competitor in a thread of the same process, so a
  shared fd would never block and the tests would fail the same way as with the lock removed.

**Choices taken where nobody could be asked** (each reversible; SPEC §12k, *Gates by declared state*, says them):
- *Two kinds of gate map.* Main already had `gate:` maps by the §12k columns (normal, away, maintenance, freeze,
  incident), from `regime-scheduled-gates`, which this definition did not mention. Rule: a map is by declared state
  when the model declares states under `operating:`, or when the map has `else:`. Otherwise it is a §12k column map,
  as before. So `gate-needs-states` is for an `else:` map in a model with no states. An unknown key in a column map
  stays `bad-value`, and `test_regime_gates` passes unchanged.
- *`Action.gate` stays a string.* The definition says `str | dict`. Instead the map is `Action.states` and `gate` is
  its `normal` cell (else `else`'s). Reason: `gate` is read as a string in program.py, server.py, cli/gated.py,
  numbers/impact_fields.py, inbox/interventions.py and the pages. Making it a dict would break each of them, outside
  the files to touch.
- *Both layers apply.* A map-gated action's §12k columns are filled from its `normal` cell. The gate in force at the
  request is the stricter of that column and `resolve`'s answer, then act-risk. So a §12k incident still denies it,
  and a bypass can never loosen past the §12k column either. At the act the declared-state re-check comes first
  (refused: `failed`). The existing §12k checks follow (`denied`, or held again).
- *`current`.* operating-states has no reader shaped like `current(p, spec)`. Its `fold.in_force` returns top=None
  both for "none entered" and for "unreadable". So `fold.current(p, spec)` was added beside it: the top state entered,
  `normal` when none is, raising when the record cannot be read. `schedule.state` catches the raise and refuses an
  undeclared name (both → None → deny).
- *A trip's entry takes the exclusive lock too* (`operating/trips.py: _record`, one line). It enters a state as `enter`
  does, and only tightens.
- *`--end`* needs only the name pattern and a bypass standing on the class, not a map gate still on it, because ending
  only tightens. With none standing it is refused (rc 2, nothing recorded). `ergostat bypass` lists every class
  standing.
- *A bad grant after a good one* ends the earlier lease (no bypass): the stricter reading.
- *The intake path.* `intake/envelope.parse` only decodes. The `OWN_TYPES` refusal is in `envelope.check`, which every
  push calls after it, so the test calls both.
- *GAPS (item 9).* docs/GAPS.md is not edited: the merge queue refuses a branch that edits it and writes the line from
  the `## Entry` below.
- *Not covered:* the §12k state's own acts (`ergostat operating freeze`) do not take the operating lock. That was not
  asked, and the act re-reads that state as before. `run_once` takes the lock when the request was map-gated or the
  model in hand has a map. An action changed from plain to map between that model's load and the act is still
  re-checked by `at_act`, but outside the lock.

**Answers to the plan review:**
- Regrant order: added grant@t, end@t-5 (not standing) and end@t, grant@t-5 (standing). Sorting by time failed the
  test (above).
- The lock opens a fresh fd per acquisition (`os.open` in `schedule.lock`). No path takes it again while holding it.
  `request` lets go before it calls `run_once`. `enter`, `leave`, `grant` and `end` never call each other; `end`
  calls `standing`, which takes no lock.
- `grant` and `leave` only loosen. A race with either can only leave an act refused or held under the stricter answer
  it read. SPEC says so (*Which races are tested*), and claims no test for them.
- `_spawn` uses `start_new_session=True`. The timeout test polls with a 10 s deadline. Running out of time fails it,
  and a zombie or reaped pid counts as gone. The background `sleep` writes to /dev/null, so with only the child killed,
  `communicate` returns and the sleep is still alive.
- The wrap matched operating-states as merged into this branch (59bcca6b): `operating/acts.py`'s `enter(p, spec, name,
  why, env)` and `leave(...)`. Their read, decision and write are now inside `schedule.lock(p, exclusive=True)`.
  `tests/test_operating.py` passes after the change.
- `test_bypass_ceiling` refuses `25h`, `0`, `0s`, `-1h`, `soon`, `5y`, `1e9h`, a 400-digit day count and `inf`, each rc
  2 with no event, plus `grant(..., 86401)`.
- Ending a stale bypass is allowed (above); the allowlist guards grants only.

## Entry

entry-of: operating-modes-regime
done: 2026-11-24 Gates by declared operating state and bypass leases, on `operating-gates` (SPEC §12k, *Gates by declared state*). `gate:` can be a map from a declared state (and `normal`, `else:`) to a gate. One `schedule.resolve` decides it at the request and again at the act, under a shared `flock` held from the re-check until the command has started. Entering, leaving, granting and ending take that lock exclusive, and an unread state is `deny`. `ergostat bypass CLASS --for DUR | --end` is the owner's lease (at most 24 h, folded by seq), refused from a run and from every agent's event path. A timed-out action's process group is killed. Left: the §12k state's own acts under the lock, P3/T1 and presence.
