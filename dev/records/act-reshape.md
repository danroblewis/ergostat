# act-reshape: under a state whose cell says `reshape: OTHER`, the declared smaller action is requested at once and the full act waits for the owner
depends-on: [regime-scheduled-gates]

## Definition of done
- A gate cell may be `{reshape: ACTION}`, for example `gate: {normal: auto, away: {reshape: push-branch}}`.
- Compile refuses three cases, each at its line (`bad-reshape`): a target that is not in `actions:`; a target whose
  args are not a subset of the full act's; and a target whose own cell under that state reshapes again (no chains).
- At a request under a reshape cell, the full act is recorded and held for the owner (`approve`), with `reshaped_to:
  ID`. The target is requested at once with the same args (only the ones it takes), and its own gate and act-risk
  apply (`reshaped_from: ID`). The session is told both ids.
- The owner's approval of the full act goes through the act check as any held act does. Denying one of the two never
  answers the other.
- SPEC §12k says this. The GAPS entry says reshaping is done.

## Relation to other work
- regime-scheduled-gates: waits for it. The reshape cell is one more kind of cell in its map.

## Files to touch
- `ergostat/actions/gate.py`
- `ergostat/actions/compile.py`
- `ergostat/actions/server.py`
- `docs/SPEC.md`
- `docs/GAPS.md`
- `tests/test_act_reshape.py` (new)

## Risks
- lesson-4: a reshape that reshapes again could loop. Chains are refused at compile time, and at request time a reshape is followed at most once.
- lesson-8: "the full act waits" must hold. The full act is never approved by `gate`, even when its own act-risk would allow it.

## Acceptance tests
- `tests/test_act_reshape.py::test_reshape_runs_target_and_holds_full`: under away, the target ran, the full act is `requested`, and each links to the other.
- `tests/test_act_reshape.py::test_full_act_never_auto_approved`: an `auto` full act under a reshape cell is still held, and a sweep does not run it.
- `tests/test_act_reshape.py::test_reshape_refused_at_compile`: an unknown target, extra args and a chain are each `bad-reshape`.
- `tests/test_act_reshape.py::test_target_gated_by_its_own_cell`: a `deny` target is denied while the full act stays held.

## Size budget
110 net lines
size: M (confidence: low)

## Notes from the plan review (answer each)

- ergostat/actions/gate.py:180-197 (at_act) and :152: the plan never says how the act check reads a reshape cell. When the owner approves the full act, run_once calls at_act, which reads the regime gate as it is now and calls rk.stricter(mine, asked). Under away, mine is {reshape: X}, which is not auto, approve or deny, so stricter may crash, reshape again, or read it however the implementor guesses. State it: at the act, a reshape cell reads as `approve` for the full act (an owner-approved act runs; a gate-approved one is held again by line 152). Record the full act's `requested` with gate `approve` (not a.gate, line 66), so `asked` at the act can never be the act's own `auto`. Add a test where the owner approves the full act while still away, and it runs through at_act with risk_at_act recorded.
- ergostat/actions/server.py:90-92: once gate.request returns the held full act, the server waits up to spec.actions[name].wait on it, so the session blocks after the smaller act already ran, and say(a) reports only the full act. Say what the server does after a reshape: return at once (or wait on the target, not the full act), with the target's result (state, exit, output) and both ids in one answer. Do the same for a program's ask (ergostat/actions/program.py:99-124, settle/finish): program.py is not in Files to touch, but it reaches gate.request with asker=program and key=k, so say whether the target takes that key (it should not: known() then matches the target under the full act's key) and add program.py to the files.
- The chain check 'its own cell under that state reshapes again' is checked one key at a time, but regime-scheduled-gates chooses a cell by operating state and presence with precedence, so a chain can appear only in a combination (full reshapes under away; the target reshapes under freeze, and both hold). Write the check over the cell as resolved for each reachable state and presence pair, and say what the runtime 'followed at most once' does when the target's resolved cell is a reshape anyway: hold the target as approve, never reshape it. Test it with a monkeypatched resolver.
- No acceptance test shows that denying one of the two never answers the other in the direction of the owner denying the full act: the target's record and result stay as they were. test_target_gated_by_its_own_cell covers only the other direction.
- test_full_act_never_auto_approved should also give the full act an act-risk that would step it to auto/allow (or no risk at all with gate auto), and should run gate.sweep after an at_act pass. Break the hold, by letting the full act's own gate through, and show the test fails.
- The order of writes: take the target's id with rec.new_id before writing the full act's `requested` (reshaped_to), and write the target with reshaped_from in its first `requested` event, so neither record is ever seen without its link. Say which is written first and why a crash between them leaves no auto-run.
- regime-scheduled-gates also changes gate.py, compile.py and SPEC §12k. Rebase onto it after it lands, and add the reshape cell to its validation of cell kinds rather than adding a second parse of cells.

## Where it stopped

Built, round 1. Every item of the definition is done. That is 61 net lines outside tests and docs (budget 110). The
four acceptance tests pass, with six more: `test_owner_approves_full_while_away`, `test_denying_full_leaves_target`,
`test_reshape_followed_once`, `test_session_answered_by_target_at_once`, `test_program_answered_by_target_keyless`,
and the second parameter of `test_full_act_never_auto_approved`. regime-scheduled-gates is on main and under this
branch. Main had nothing new to merge (`HEAD..main` is empty).

How it is built: a reshape cell compiles to `approve` in `Action.gates`, and its target goes into a new
`Action.reshapes` (column → action; `ergostat/spec/ir.py`, one line, not in the files to touch). Every existing
reader (`risk.cell`, `at_act`, `rk.stricter`, `server.tools`, the pages) therefore sees the plain `approve` it
already handles. Only `gate.request` reads `reshapes`.

Answers to the plan review:
- The act check. At the act a reshape cell reads as `approve`, because that is its compiled cell, so `at_act` needs
  no new branch. The full act's `requested` records gate `approve` (`gate.request` also raises the cell to at least
  `approve` when `reshapes` names the column, for an `Action` built in memory), so `asked` is never `auto`. Under
  away, an owner-approved full act runs through `at_act` with `risk_at_act` recorded (cell, asked and effective are
  all `approve`): `test_owner_approves_full_while_away`. That test holds presence at away, because the owner's
  approval is itself an owner event and would make them present. A full act approved by the gate is held again
  (`held_by: act-risk`): the second half of `test_full_act_never_auto_approved`.
- The server and a program's ask. `server.call` does not wait on the full act. It answers with the target's result
  (state, exit, output), waited for up to the target's own `wait:`, plus `reshaped_from` and `full` (the full act's id,
  its state and a note), all in one answer. `program.ask` settles and delivers the target. The target takes no `key`:
  a second keyed ask finds the held full act through `known()`, follows its `reshaped_to`, and gets the same target
  back with no new record (`test_program_answered_by_target_keyless`). `program.py` changed by 2 lines.
- The chain check covers every reachable combination. For each reshape cell, `compile.reshapes` takes every state in
  `operating.STATES`, both presences, and each set of named maintenance actions among {full, target}. It resolves
  both actions' columns with `risk.column`, the resolver the request uses, and refuses the cell when the full act's
  column is that cell and the target's column is a reshape. The test's `combo` case is a chain that exists only in a
  combination: full reshapes under `normal`, target under `maintenance`, during maintenance naming only the target.
  At runtime a reshape is followed once. A target whose own column is a reshape anyway is held as `approve` and never
  reshaped: `test_reshape_followed_once` puts such a cell into the in-memory spec by hand.
- Denying the full act leaves the target alone: `test_denying_full_leaves_target`. The target either ran or is held;
  its record and `result()` are unchanged after the owner denies the full act, and a held target is still the owner's
  to approve on its own.
- Never auto-approved. The test is parametrized: no risk, and a risk that never steps (severity 1, T 50). It asserts
  that the full act's only move is `requested` (never approved, not even to be held again), and that `gate.sweep`
  after the target's `at_act` pass runs nothing.
- Order of writes. The target's id is taken with `rec.new_id` first. The full act's `requested` (with `reshaped_to`)
  is written next, and then the target's first `requested` (with `reshaped_from`). `test_reshape_runs_target_and_holds_full`
  checks this order. A crash between the two leaves the full act held as `approve` and no target recorded, so nothing
  runs. The full act is written first so that nothing can run before the held act exists. The cost is that a crash
  can leave a `reshaped_to` naming an id never written (`server.call` and `program.ask` then fall back to the full
  act).
- Cell kinds are parsed once. The reshape cell is one more kind accepted by the regime map's own `columns()`
  validation (`cell_of`). A malformed reshape (an extra key, a name that is not a name) is `bad-value` there, as any
  other bad cell is.

Each guard was broken by hand, and a test failed each time:
- the full act's request gate set to its own `auto`: `test_full_act_never_auto_approved` failed. Before I added the
  moves assertion it passed, because `at_act` held the act again; that is why the assertion is there;
- the reshape cell compiled without `approve`: four tests failed;
- the reshape followed more than once: `test_reshape_followed_once` failed;
- the chain check on the same column only: `test_reshape_refused_at_compile` failed (`combo`);
- the server's switch to the target removed: the session test failed after its 30 s wait;
- the program's switch to the target removed: the program test failed.

Choices taken where nobody could be asked (each reversible):
- A reshape applies only where it is written. An unwritten `away` or `maintenance` takes `normal`'s plain gate, never
  its reshape (a reshape `normal` gives them `approve`; freeze's default from it is `deny`).
- The full act's own act-risk still applies at the request. It can step `approve` to `deny`, and the target is then
  asked for anyway: the two are answered apart.
- `schema/ergostat.schema.json`'s gate map now takes `{reshape: NAME}` cells (6 lines, not in the files to touch), so
  the schema does not refuse what compile takes.
- `docs/GAPS.md` is not edited (the house rule: the queue writes it from the records). The entry is below.

Run: `tests/test_act_reshape.py` (10 passed); `tests/test_regime_gates.py`, `tests/test_gated_actions.py`,
`tests/test_act_risk.py`, `tests/test_program_actions.py`, `tests/test_operating_state.py`,
`tests/test_spec_schema.py` and `tests/test_spec_structure.py` all passed. ruff is clean. Not run here: the unit suite
and the four browser files (the factory runs them). No page changed.

## Entry

entry-of: operating-modes-regime
done: 2026-11-24 Reshaping an act, on `act-reshape` (SPEC §12k): a gate cell `{reshape: ACTION}` holds the full act for the owner and asks for the smaller declared action at once under its own gate and act-risk, each linked to the other (`reshaped_to` / `reshaped_from`), the session answered by the smaller one; unknown targets, extra args and chains refused at compile as `bad-reshape`.

## Where it stopped (round 2)

Built, round 2. The one finding (blocking) on a program asking again for a reshaped act is fixed in
`ergostat/actions/program.py`, in each of its three parts, and each part has its own test:
1. A held target is taken over by the lease. When `start` finds the held full act and takes it over (`reask`), it
   also takes over the target it was reshaped to (`program.target`: `reask` on the target, and then the fenced check
   on the target too). When the owner approves the target, it runs under the lease that asked last and is not failed
   as fenced: `test_program_reask_takes_target_over_with_lease` (lease 1, then 2, then approve: ran, not fenced).
2. A target that failed is asked for anew. A target that no longer stands, by the same rule `known()` applies to any
   act (now `program.stands`: failed, fenced, or denied by a gate whose cell is no longer deny), is asked for again.
   The full act's new `reshaped_to` is written first (an `ergostat.action.reshaped` event; it is not a state move),
   and then the new target, with `reshaped_from` in its first event: the same order and reason as round 1. A lock
   file named by the old target (`O_EXCL`, the same way as `run_once`) means two asks at once replace it only once
   (lesson-1). The one that loses the race gets the new target if it is written already, else the old one as it
   stands. Test: `test_program_failed_target_asked_anew`. The first ask fails, the second asks anew and runs, the full
   act links to the new target, and a third ask gets that target back with no new record.
3. Once the owner has answered the full act, the answer is the full act. `ask` follows `reshaped_to` only while the
   full act is not answered (`program.answered`: past `requested` and approved or denied by someone, never by the gate
   alone). A full act the owner approved (and that ran) or denied is the answer to a later ask, and is delivered to
   that run: `test_program_answered_by_full_once_owner_answers` (both cases).

Each fix was broken by hand and its test failed: no `reask` on the target (test 1); a failed target counted as
standing (test 2); `reshaped_to` always followed (test 3). The module docstring (the promise at program.py:12-16) and
SPEC §12k (*Reshaping an act*: a new item, "A program asking again") now say this.

A correction to round 1: it said regime-scheduled-gates "is on main". It is not. It is merged under this branch as
the base (f3425a8f), and `main` does not have it. `HEAD..main` is still empty. Measured against that base, the gap is
103 net lines outside tests and docs (budget 110). Against `main`, the diff also holds the base gap's own lines.

Left as it was, and not part of the finding: two programs taking over the same held act at the same moment write two
`reasked` events with no lock. That was already so for every held act before this gap. The later event wins, as it
does for an act that was never reshaped.

Run: `tests/test_act_reshape.py` (13 passed), `tests/test_program_actions.py`, `tests/test_gated_actions.py`,
`tests/test_regime_gates.py`, `tests/test_act_risk.py`, `tests/test_operating_state.py`, `tests/test_spec_schema.py`,
`tests/test_spec_structure.py`: all passed. ruff is clean. The unit suite and the four browser files were not run here
(the factory runs them). No page changed.

## Where it stopped (round 3)

Built, round 3. The one finding (blocking) is fixed in `ergostat/actions/program.py`. The finding: a full act whose
act-risk steps it to `deny` at the request, while its target ran, was dropped by `stands()` on a second ask, so a new
full act was made and the target ran again (lesson-5).
- `program.stands`: a full act denied by the gate at its request (`denied_by: gate`, never approved, so not a denial at
  the act after the owner's approval) that has a `reshaped_to` stands while that target stands, by the same rule
  (`stands` on the target; the target has no `reshaped_to`, so this is followed once). `ask` already follows
  `reshaped_to` for such an act (`answered` is false: the gate, not the owner, denied it), so the target is the answer
  and is delivered to the asking run. The target is never run twice. Once the target no longer stands (failed, fenced,
  denied by a gate since changed), the full act no longer stands either, and both are asked for anew. This is the
  finding's second option. The full act is denied, not held, so there is nothing of the owner's to keep.
- `program.start`: the target is taken over (`program.target`: lease `reask`, the fenced check, asked anew when it no
  longer stands) for every full act that is not yet answered, held or denied by the gate at its request. Before, this
  was done for a held one only. So a held target under a gate-denied full act is taken over by a later lease, as it is
  under a held one.
- Tests: `test_program_full_denied_by_risk_target_runs_once` uses `risk: {severity: 3, threshold: 2}`, which steps
  approve to deny on every ask. The full act is denied by the gate, the target ran, and two more asks with the same key
  get the same target back: no new record, the target ran once, and it was delivered to r1, r2 and r3. A second key
  whose target failed is asked for anew (a new full act and a new target), and that target runs once.
  `test_program_full_denied_by_risk_held_target_leased`: the target is held, and a later lease takes it over (fence 2);
  approved, it runs and is not fenced.
- Each fix was broken by hand and its test failed. With the `stands` branch off, the first test failed at r2 with a new
  target id (the finding reproduced). With the takeover limited to a held full act again, the second test failed (the
  target had no `fence`).
- SPEC §12k (*A program asking again*) and the module docstring (program.py:12-19) now say this.

Main has nothing new (`HEAD..main` is empty).

Overrun reason: measured against the base gap's merge (f3425a8f), the gap is 115 net lines outside tests and docs (compile 37, gate 15, program 49, server 3, ir 2, schema 9). That is 5 over the 110 budget. The three review rounds asked for program-ask behaviour (lease takeover, asking anew, the owner's answer, and this round's gate-denied full act) that the plan did not foresee, and most of program.py's lines are those rules and the docstring that states them. Round 2's figure of 103 left out the schema's lines.

Run: `tests/test_act_reshape.py` (15 passed), `tests/test_program_actions.py`, `tests/test_gated_actions.py`,
`tests/test_regime_gates.py`, `tests/test_act_risk.py`, `tests/test_operating_state.py`, `tests/test_spec_schema.py`,
`tests/test_spec_structure.py`: all passed (136 tests). ruff is clean. The unit suite and the four browser files were
not run here (the factory runs them). No page changed.

## Where it stopped (round 4)

Built, round 4. This round had one finding (blocking), and it is fixed in `ergostat/actions/program.py` (`stands`). The finding: a full act
denied by its own act-risk at its request stood for as long as its target stood, even after the reshape was no longer
in force. Once the owner was back, every later ask was answered by the old target, and the full act could never be
asked for again (lesson-5).
- `program.stands`: a full act denied by the gate at its request, with a `reshaped_to`, stands only while its column
  in force is still a reshape (`act.reshapes.get(gt.in_force(p, act)[2]["column"])`, the same reading the request
  makes) and its target stands. Otherwise it is like any act denied by act-risk: it does not stand, `known()` returns
  None, and `start` asks for the full act anew. That new ask is made under the column's own gate and act-risk, with no
  reshape and no new target. So the target is not run again. The docstrings (module, `known`) and SPEC §12k (*A program
  asking again*) now say this, and the docstring's "denied by a gate since changed" again matches what the code does.
- Test: `test_program_full_denied_by_risk_asked_anew_once_owner_back` uses `risk: {severity: 3, threshold: {normal:
  50, away: 2}}`. Under away the full act is denied by act-risk and the target runs. Then `operating.enter(p, "normal")`
  and the same key is asked again. The answer is a new `pr` record, which ran and has no `reshaped_to`. A third ask
  gets that same record back (3 records in all). `ran.txt` is `["push t1", "pr t1"]`: the full act ran once and the
  target once.
- I broke the fix by hand (the reshape-in-force check removed) and the new test failed: the second ask was answered by
  `push`, which reproduces the finding. The round-3 tests still pass with the fix in place, because there the column
  stays `away`, so the reshape is still in force.

Main has nothing new (`HEAD..main` is empty).

Overrun reason: the gap is now 119 net lines outside tests and docs, against the base gap's merge (f3425a8f). That is round 3's 115 plus this round's 4 in program.py (11 added, 7 removed), and 9 over the 110 budget. The four review rounds asked for program-ask rules the plan did not foresee: lease takeover, asking anew, the owner's answer, the gate-denied full act, and this round's check that the reshape is still in force. Most of program.py's lines are those rules and the docstring that states them.

Run: `tests/test_act_reshape.py` (16 passed), `tests/test_program_actions.py`, `tests/test_regime_gates.py`,
`tests/test_gated_actions.py`, `tests/test_act_risk.py`, `tests/test_operating_state.py`, `tests/test_spec_schema.py`,
`tests/test_spec_structure.py`: all passed (137 tests). ruff is clean. I did not run the unit suite or the four browser
files here (the factory runs them). No page changed.
