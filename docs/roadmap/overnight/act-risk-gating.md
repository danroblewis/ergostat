# act-risk-gating: an action declared with `risk:` is gated one step stricter when the risk of this act reaches its threshold, at the request and again at the act
depends-on: []

## Definition of done

An action (SPEC §12k) may declare `risk: {severity: S, threshold: T}`. When it does, each request for it gets a
score, and its gate moves one step stricter when that score is at or above T. The step only ever goes from `auto` to
`approve` (held for the owner), or from `approve` to `deny`. It never goes the other way. An action without `risk:`
is gated exactly as on main.

**The score** (a new module `ergostat/actions/risk.py`, plain arithmetic, no AI):

    act_risk = S × (1 + 4c) × (1 + n)        step  ⇔  act_risk ≥ T

- `S`: an integer from 1 to 5, required inside `risk:`. Compile rejects 0, 6, non-integers and text (`bad-value`,
  with where it was written).
- `T`: a number with 1 < T ≤ 50, default 8. Compile rejects anything outside that range. Scores run from 1 (S=1,
  c=0, n=0) to 50 (S=5, c=1, n=1), so T can fall anywhere in that range. T is absolute, not a multiple of S, so
  **severity changes the outcome**. Example: with c=0, n=0, T=4, S=3 gives 3 (no step) and S=4 gives 4 (step).
- `c`: the asking block's contradicted share. It comes from `claims.record.stored` over the last week (the window
  `trust.WEEK` uses) and is counted with `trust.counts(cs, block)`. Every case where it cannot be read counts as the
  worst case, and each case records its own reason in `why`:
  - the claims record raises (unreadable) → c = 1, `why: "claims record unreadable"`;
  - the request names no block → c = 1, `"no asking block"`;
  - the block made no claims in the window (missing from the counts) → c = 1, `"no claims on record"`;
  - the block made claims but none was checked (verified or contradicted) → c = 1, `"claims made, none checked"`.
    This reason must differ from the one for a block with no claims;
  - otherwise c is the share, clamped: a value that is not finite (NaN, ±inf) → 1, and anything else is held to
    [0, 1]. NaN never passes through and never counts as 0.
- `n`: novelty. n = 0 only when the actions record (`actions.record.stored`, requested in the last 90 days) holds
  another action with the same name that reached `ran` (exit 0) within the last 90 days. Otherwise n = 1. An action
  that only `failed` does not count as having run. **An unreadable record, or a query that raises, gives n = 1**
  (`why: "action record unreadable"`).
- Staleness of the state the act was planned on (08 §6) is **not** part of the score. SPEC says so, and nothing in
  the code or docs claims it.

**At the request** (`gate.request`): the score is worked out before `requested` is written, and recorded on it as
`risk: {score, severity, threshold, c, c_why, n, n_why, gate}`, where `gate` is the stepped gate. The stepped gate
then decides as `gate:` does today. When it stepped, the denied note or the held note says so, e.g. "act-risk 12 ≥
8: its gate auto stepped to approve". `result()` gives that note to the session.

**At the act** (`gate.run_once`, inside its existing O_EXCL run lock, after the fence check and before the command
starts), for every action:

1. The model is read again with `reload.load_checked(p.model)`. If the model has no file (in-memory test models),
   the spec passed in is used instead, and SPEC says so.
2. If the model cannot be read, the action is **re-held**: a `requested` event with `held_by: "act-risk"` and a note.
   The lock file this call created is removed, by its own name, so a later approval can run the action. The command
   is not run.
3. If the action is gone from the fresh model, it is `denied` by `gate`, with a note saying the action is no longer
   in the model. The command is not run.
4. Otherwise the score is worked out again from the fresh action (its current `gate:` and `risk:`) and the record as
   it is now. The fresh gate is stepped by it. The **effective gate** is the stricter of that and the request's
   recorded stepped gate (the request's `gate` when it had no `risk`).
5. The effective gate decides:
   - `deny` → `denied` by `gate` (even when the owner approved);
   - `approve`, and the action was approved by `gate` (auto) → re-held, as in step 2;
   - `approve`, and the action was approved by a person → it runs;
   - `auto` → it runs.

   The act's own reading is recorded on the event that ends the act (`ran`, `failed`, `denied` or the re-held
   `requested`) as `risk_at_act: {...}`.
6. A re-held action is approved again by its owner as any held action is. After that its `approved_by` is the
   owner's, not the stale `gate`.

**Concurrency (lesson-1).** At the request, the score is read, the decision made and the requested/approved/denied
events written. A claim verdict can land between that read and the writes. Re-scoring inside the run lock catches it
before anything runs. A verdict recorded after the act's re-check (in the moment between the re-check and the
command starting) is not seen. SPEC says exactly that and claims nothing wider.

**Docs.**
- SPEC §12k documents `risk:`, the formula, every worst-case rule above, the act re-check, and what is left out
  (staleness).
- SPEC's sentence "takes effect at the next request" now also says that a stricter gate takes effect at the act.
- The `actions:` keys list in `docs/AGENT-GUIDE.md` gets one line on `risk:`, if the guide lists those keys.
- GAPS.md line 188 says act-risk gating is done on `act-risk-gating`, and that modes, thresholds scheduled by
  regime, reshaping and staleness are still open.

**Done when:**
- the acceptance tests below exist and pass;
- the unit suite and the four browser files pass with rc 0 and no page test skipped for want of a port;
- `uv run ruff check` is clean;
- origin/main has been merged in and the suites run again.

No example is touched, so `demo_check` is not required. If one is touched, it must pass.

## Files to touch

- `ergostat/actions/risk.py` (new): `inputs()`, `score()`, `step()`, `stricter()`, `clamp()`
- `ergostat/actions/gate.py`: scoring in `request`, the act re-check in `run_once`, notes in `result`
- `ergostat/actions/compile.py`: the `risk` key, validated with a floor and a ceiling
- `ergostat/spec/ir.py`: `Action.severity: int | None`, `Action.threshold: float`
- `ergostat/actions/server.py`: the tool description says an action may be held or denied when riskier (one line)
- `docs/SPEC.md` (§12k), `docs/GAPS.md`, `docs/AGENT-GUIDE.md` (if it lists the action keys)
- `tests/test_act_risk.py` (new)
- `docs/roadmap/overnight/act-risk-gating.md` (this definition)

## Risks

- **lesson-1:** the score is read at the request and written as a decision. A contradiction, or the owner changing
  `gate:`, between the request and the act would otherwise let a stale decision run. This is answered by reloading
  the model and re-scoring inside the run lock, taking the stricter result. Tests put a contradiction and a gate edit
  in that window.
- **lesson-3:** each unreadable input counts as the worst case:
  - an unreadable claims record, a block with no claims, a block with none checked, a NaN share → c = 1;
  - an unreadable 90-day record → n = 1;
  - an unreadable model at the act → re-held;
  - the action gone at the act → denied.

  Each has a test, and the two "no claims" cases are tested apart.
- **lesson-4:** severity and threshold have a floor and a ceiling (S from 1 to 5, 1 < T ≤ 50), enforced at compile.
- **lesson-5:** a re-held action is the same id, refolded. The stale `approved_by: gate` must neither run it without
  the owner nor block the owner's approval. A test covers the re-hold followed by an owner approval.
- **lesson-8:** SPEC claims "never looser than its gate, at the request and at the act" and "staleness not counted".
  `test_never_looser` covers the whole path, with severity, threshold, c, n and both gates varied, and the act path
  included. The NaN rule has a test that fails if NaN is treated as 0 or passed through.
- **lesson-9:** for each test the implementor breaks the guarded code and reports the failure seen. The cases to
  break are:
  - drop S from the comparison (compare `(1+4c)(1+n) ≥ T/S`);
  - treat a missing c or n as 0;
  - remove the NaN clamp;
  - skip the act re-check;
  - take the act's gate instead of the stricter of the two.
- **lesson-11:** the re-hold removes a lock file. It must remove only the `<short id>.run` file this call created,
  by name, under `folder(p)`.
- **lesson-2:** the 90-day and one-week windows are windows, not orderings. The re-check uses the action's own
  fields and never compares times to decide which came first.

## Acceptance tests

All in `tests/test_act_risk.py`. Models are written as files, so the act reloads them.

- `test_score_formula`: S=2, c=0.5, n=1 → 12.0. S=1, c=0, n=0 → 1.0. S=5, c=1, n=1 → 50.0.
- `test_severity_alone_changes_the_step`: c=0 (a block with a verified claim, none contradicted), n=0 (an earlier
  run of the action, 10 days ago), T=4, `gate: auto`. S=3 → approved by the gate and ran. S=4 → held (`requested`,
  `risk.gate == "approve"`). Fails if severity cancels.
- `test_threshold_alone_changes_the_step`: the same act with T=6 and with T=4 (S=4) gives different outcomes.
- `test_auto_steps_to_approve`, `test_approve_steps_to_deny`, `test_deny_stays_deny`: each base gate with a score
  ≥ T. The denied note names the score and the threshold.
- `test_no_risk_key_gates_as_before`: an action without `risk:` and a block with c = 1 is still `auto`, and runs.
- `test_block_missing_from_claims_counts_as_one`: a block with no claims → c = 1, `c_why == "no claims on record"`.
- `test_block_with_no_checked_claims_counts_as_one`: claims made, all `unchecked` → c = 1,
  `c_why == "claims made, none checked"`, different from the reason above.
- `test_checked_none_contradicted_counts_zero`: c = 0.
- `test_claims_unreadable_counts_as_one`: `claims.record.stored` is monkeypatched to raise → c = 1, with its reason.
- `test_nan_share_counts_as_one`: `trust.counts` is monkeypatched to return checked=2 and a NaN share. With S=2,
  n=0, T=6: c must be 1 and the gate steps (score 10). If NaN were treated as 0 the score would be 2 (no step), and a
  NaN passed through compares false (no step), so either fails the test.
- `test_novel_when_never_ran`, `test_known_when_ran_within_90_days`, `test_novel_when_last_ran_over_90_days_ago`,
  `test_failed_run_is_not_known`.
- `test_novelty_record_unreadable_counts_novel`: the action record query is monkeypatched to raise → n = 1, with its
  reason.
- `test_contradiction_between_request_and_act_reholds`: a program asks for an `auto` action that passes at the
  request (approved by the gate, left for the sweep). Contradicted claims for the block are then recorded, and
  `gate.sweep` runs. The command's marker file is absent, the state is `requested`, `held_by == "act-risk"`, and
  `risk_at_act` is recorded. The owner's approve then runs it, with `approved_by` the owner's (lesson-5).
- `test_gate_edited_to_deny_between_request_and_act`: an `approve` action is held, the owner edits the model file to
  `gate: deny`, then approves it. The result is `denied` by the gate, and the command never ran.
- `test_act_takes_the_stricter_of_request_and_act`: the request stepped to `approve` (c = 1, held). It is then
  approved by `gate` through a crafted `approved` event, and the record improves so the act's own step is `auto`.
  It is re-held, not run.
- `test_owner_approval_runs_when_act_steps_to_approve`: owner-approved, and the act's effective gate is `approve` →
  it runs.
- `test_action_gone_at_act_is_denied` and `test_model_unreadable_at_act_reholds`: neither runs the command.
- `test_rehold_removes_only_its_own_lock`: another action's `.run` file in the same folder is untouched.
- `test_never_looser`:
  - over S 1..5 × T {1.5, 4, 8, 20, 50} × c {0, 0.25, 1, NaN} × n {0, 1} × base {auto, approve, deny},
    `step(base, score)` is never less strict than the base, and moves at most one step;
  - `stricter(req, act)` is never less strict than either;
  - end to end, over a subset (S {1, 5} × T {4, 50} × base {auto, approve} × act-time c {0, 1}) through `request`
    and then `run_once`, the recorded outcome (ran, held, denied) is never less strict than the base gate, nor than
    the request's stepped gate.
- `test_risk_key_validated`: S of 0, 6, 2.5 and "high", and T of 1 and 51, each give a compile error with where it
  was written. A valid `risk:` compiles to `Action.severity` and `Action.threshold`.

The existing `tests/test_gated_actions.py` and `tests/test_program_actions.py` pass unchanged.

## Size budget

220 net lines of code outside `tests/` and `docs/`:
- `risk.py`: about 100
- `gate.py`: about 70
- `compile.py`: about 30
- `ir.py`: about 5
- `server.py`: about 3

## Notes from the plan review (answer each)

- lesson-5: the re-held `requested` event (held_by act-risk) must clear the earlier approved/approved_by:gate in the fold, not only be overwritten by the owner's later approval. Add to test_contradiction_between_request_and_act_reholds (and test_model_unreadable_at_act_reholds): a second gate.sweep after the re-hold writes no new event and does not run the command; otherwise a stale gate approval leaves the action re-picked and re-held on every sweep.
- Re-hold order: write the re-held `requested` event before removing this call's `.run` lock, so a concurrent sweep that takes the lock already folds the action as held. State the order in the code and test it, or say why it is safe.
- Compile validation: S must reject booleans (`True` is an int equal to 1) and T must reject NaN, ±inf and booleans explicitly. Add these cases to test_risk_key_validated.
- A request with no asking block (an owner-initiated request) always scores c=1 and steps, so an owner's own `auto` request with S≥2 is held for that same owner. Either say this in SPEC §12k as intended, or define what counts as the asking block for owner requests; do not leave it implicit.
- Novelty is keyed by action name only. An action whose command was changed but kept its name counts as known. Say so in SPEC (lesson-8: don't let 'novel' read as 'this command never ran').
- Step 4: say exactly which recorded stepped gate is used for a refolded id. After a re-hold, the later `requested` event carries `risk_at_act`, not `risk`; the fold must keep the original request's `risk.gate` (or take the stricter of the recorded ones). Define it and cover it in test_act_takes_the_stricter_of_request_and_act.
- The fallback to the spec passed in when the model has no file has no acceptance test. Add one, in which an in-memory model with a risk: that steps at the act is still re-held or denied, or state why it is exempt.
