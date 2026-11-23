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
