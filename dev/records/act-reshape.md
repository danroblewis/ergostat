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
