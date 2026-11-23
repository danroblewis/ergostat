# regime-scheduled-gates: an action's gate and its risk threshold chosen by the operating state and presence in force, at the request and again at the act
depends-on: [operating-state-record]

## Definition of done
- An action's `gate:` may be a map with the keys `normal`, `away`, `maintenance`, `freeze` and `incident`, each `auto`,
  `approve` or `deny`. `risk.threshold` may be a map with the same keys, each within the same limits as now
  (1 < T ≤ 50). A plain value means the same as today. Any other key or value is `bad-value` at its line.
- Defaults never loosen: an `away` or `maintenance` cell that is not written takes `normal`'s; an unwritten `freeze`
  is `normal`'s gate one step stricter; an unwritten `incident` is `deny`. A written cell is used as written (it is the
  owner's file).
- The `maintenance` cell applies only to actions the lease names. Every other action takes its `normal` column (or
  `away` when the owner is away). `away` applies under normal while the owner is away.
- At the request, the state in force picks the cell, and then act-risk steps it as now. The request records
  `operating: {state, presence, seq, why}`.
- At the act, inside the run lock, the state is read again. The effective gate is the stricter of the request's and the
  act's. So freeze entered after the owner's approval denies the act, and `risk_at_act` records the state read.
  An unreadable state at the act counts as incident.
- SPEC §12k says all of this. The GAPS entry says thresholds by state are done.

## Relation to other work
- operating-state-record: waits for it, and builds on its fold.
- ir-control-document / ir-read-back: these touch `ergostat/spec/ir.py`. Here only `Action`'s gate and threshold fields
  change. Whichever lands second carries the field into the IR.

## Files to touch
- `ergostat/actions/gate.py`
- `ergostat/actions/risk.py`
- `ergostat/actions/compile.py`
- `ergostat/spec/ir.py`
- `docs/SPEC.md`
- `docs/GAPS.md`
- `tests/test_regime_gates.py` (new)

## Risks
- lesson-1: the owner approves under normal, and freeze is entered before the act. The act must read the state again inside the run lock.
- lesson-3: a state that cannot be read, or a state name not in the map, must take the strictest column, never `normal`.
- lesson-8: "defaults never loosen" must hold for every unwritten cell, checked by a test over all of them.

## Acceptance tests
- `tests/test_regime_gates.py::test_cell_chosen_by_state`: an `auto` normal / `deny` freeze action runs under normal and is denied under freeze.
- `tests/test_regime_gates.py::test_freeze_entered_between_approval_and_act_denies`: an approved action and a monkeypatched step between them; the command never runs.
- `tests/test_regime_gates.py::test_unwritten_cells_never_looser`: over every base gate and every state, the unwritten cell is at least as strict as `normal`'s.
- `tests/test_regime_gates.py::test_maintenance_opens_only_named_actions`: a looser maintenance cell applies to the named action only.
- `tests/test_regime_gates.py::test_threshold_by_state_steps_the_gate`: the same score steps the gate under away (T 4) and not under normal (T 8).
- `tests/test_regime_gates.py::test_bad_gate_map_refused`: an unknown key and an unknown gate value are each `bad-value` at their line.

## Size budget
140 net lines
size: M (confidence: medium)

## Notes from the plan review (answer each)

- Action.gate is read as a plain string in gate.py:65,66,76,195,201, risk.py:90 and, outside the Files to touch, program.py:77, server.py:52 ({...}[a.gate] fails with a dict), cli/gated.py:188 (a set of gates fails because a dict cannot be hashed), numbers/impact_fields.py:41 and pages.js:484,493 / review.js:453; the request's recorded "gate": a.gate (gate.py:66) is also at_act's fallback for `asked` (gate.py:196). Keep Action.gate as the normal value, add separate gates/thresholds fields filled with the defaults at compile time, add one cell(action, operating, named) -> (gate, threshold) function, pass that pair to rk.assess, and record the chosen cell as the request's gate so asked, rk.note and _why compare against the gate in force.
- 'unreadable state at the act counts as incident' plus 'a written cell is used as written' means an owner-written incident: auto runs the act when the state cannot be read, which contradicts the plan's own Risks line (strictest column). An unreadable state, or a state name not in the map, must be deny whatever is written, at the request as well as the act; add a test where incident: auto is written and the state read raises.
- Defaults for unwritten freeze/incident threshold cells are not given (a lower T is stricter); say that every unwritten threshold cell takes normal's, and cover thresholds in the never-looser test.
- operating-state-record has not landed (nothing under ergostat/ mentions an operating state); name the exact fold function giving {state, presence, seq, why} and the lease's named actions, and how it fails, before building.
- docs/roadmap/overnight/groomer-keeps-built-work.md mentions an operating-states-continued branch with 22 commits and 1,623 lines; its ref is not in this clone. Check it for overlapping work before starting from main.
- The freeze-between-approval-and-act test should cover both an auto request approved by the gate and an approve request approved by the owner; only the second relies on the stricter rule.
- The maintenance test should also show that an action the lease does not name, with a written looser maintenance cell, takes its normal column (or away while the owner is away).

## Where it stopped

Built, round 1. Every item of the definition is done. 83 net lines outside tests and docs (budget 140). The six
acceptance tests pass, along with two more: `test_unsure_state_is_deny_whatever_is_written` and
`test_unreadable_state_at_the_act_denies`. I broke each guard by hand and watched a test fail:
- the act not reading the state again (both freeze cases and the unreadable-at-act test failed);
- maintenance applied to every action (the maintenance test failed);
- the freeze default left at normal's (the never-looser test failed);
- `unsure` ignored (the unsure test failed);
- the threshold column not passed to the score (the threshold test failed).

Main had nothing new to merge (`HEAD..main` is empty).

Answers to the plan review:
- Plain-string readers. `Action.gate` and `Action.threshold` stay the `normal` column. New fields `Action.gates` and
  `Action.thresholds` hold all five columns, defaults filled at compile time. When they are empty (an `Action` built
  in memory, `inbox/config.py`'s notify actions), the defaults come from `gate` and `threshold`. `risk.cell(action,
  operating) -> (gate, threshold, column)` picks the cell, and `rk.assess` takes that pair. The request records the
  chosen column's gate as its `gate`, so `asked`, `rk.note` and `_why` compare against the gate in force (`_why`
  reads `risk_at_act.cell`). program.py, server.py, cli/gated.py, impact_fields.py and the pages are unchanged and
  still see a string.
- Unreadable state and a written `incident: auto`. An unsure state is `deny` whatever is written, at the request and
  at the act. Unsure means: the record cannot be read, an event names no known state, a maintenance end is not a
  number, `operating.read` itself raises, or a state name is not known. Only an incident the owner entered uses the
  `incident` column. To tell the two apart, `operating.Operating` gained `unsure`. `fold` returns a module constant
  `UNSURE` for its strict-when-unsure cases, checked by identity so no event's data can set it. This is a small
  change to `ergostat/actions/operating.py`, which is not in the files to touch. Tested with `incident: auto` written
  and the fold or the read raising.
- Thresholds. Every unwritten threshold cell takes normal's (written in SPEC). The never-looser test checks this
  through `risk.cell` over every state, presence and named/unnamed case, and through the compiler.
- The fold function. `operating.read(p) -> Operating(state, presence, seq, reason, note, until, actions, unsure)`.
  It never raises and reads an unreadable record as incident and away. `gate.in_force` also catches a raising read,
  as a second guard. The lease's named actions are `Operating.actions`.
- operating-states-continued. Its ref is not in this clone (`git branch -a` shows only main and this branch), so it
  could not be checked. Built from main.
- The freeze test covers both cases (parametrized). With an auto request approved by the gate, the freeze default
  (`approve`) holds it again for the owner. With an approve request approved by the owner, the freeze default
  (`deny`) denies it. The command runs in neither.
- Maintenance. The unnamed action `other` has a written looser `maintenance: auto`. It takes `normal` (approve, held)
  while the owner is present, and `away` (deny) while they are away.

Choices taken where nobody could be asked (each reversible):
- A refused cell (unknown column or value) is `bad-value` and is then read as unwritten, so it takes its default.
- `gate: ""` used to be read as `approve`. It is now `bad-value`. `risk: {threshold: null}` used to be refused. It is
  now read as unwritten.
- `operating` on the request also carries `column` (the cell used: one of the five, or `unsure`), besides
  `{state, presence, seq, why}`.
- `schema/ergostat.schema.json`'s `gate` now also takes a map by column. `risk:` was missing from the schema's action
  before this gap, and it is still missing (outside this gap).
- The threshold check no longer calls `math.isfinite`: the range test refuses NaN and ±inf, and a huge YAML integer no
  longer overflows (lesson-3).

Not run here: the unit suite and the four browser files; the factory runs them. No page changed.

Round 2. The one finding (blocking): `program.known` (ergostat/actions/program.py:77) reused an earlier gate
denial when `act.gate == "deny"`, which is only the normal column, so a keyed program ask never got a looser cell in
force. It now asks `gate.in_force(p, act)[0] == "deny"`, the gate the state in force gives. New test
`test_keyed_program_ask_takes_the_looser_cell_once_in_force`: the ask is denied under normal, asked again while
still deny and gets the same denial back, then asked again under a maintenance lease that names it, and it runs. With
the old line put back, the test failed. Main had nothing new to merge (`HEAD..main` is empty).
The other readers of `Action.gate` were checked again. `server.py:52`, `inbox/interventions.py:211` (the guard
surface, compared between model versions) and `pages.js` describe the model as declared, so they keep the `normal`
column. None of them decides whether an act runs.
Net lines outside tests and docs: 83 (budget 140).
Run: `tests/test_regime_gates.py` (10 passed) and `tests/test_program_actions.py` (10 passed), and ruff is clean.
Not run here: the unit suite and the four browser files.
