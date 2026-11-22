# operating-state-record: the model's operating state (normal, maintenance, freeze, incident) and the owner's presence (present, away), set by the owner's typed act and folded from the record
depends-on: []

## Definition of done
- `ergostat operating` shows the operating state now and the owner's presence. `ergostat operating freeze|incident
  --note TEXT` enters a state. `ergostat operating maintenance --for DURATION --actions A,B --note TEXT` enters
  maintenance as a lease of at most 24 h that lapses on its own. `ergostat operating normal` ends the state in force.
  Each is an event from the owner. No acts are gated yet (that comes in `regime-scheduled-gates`).
- Precedence: incident over freeze, and freeze over maintenance and normal. Only the owner's typed act ends an incident
  or a freeze. A maintenance lease past its end reads as lapsed, with no event needed.
- The state is folded in the record's `seq` order, never by comparing `at` times. A new entry starts clean: it carries
  no note, end time or action list from an earlier entry of the same state.
- Presence is `away` when the record holds no event from the owner for `away-after` (top-level `operating:
  {away-after: 2h}`, default 2h, at least 5m and at most 7d, `bad-value` at its line otherwise). Otherwise it is
  `present`.
- A record that cannot be read counts as `incident` and `away`, and says why. One function returns the state, the
  presence, the seq of the event it was read from, and the reason.
- SPEC gets a new subsection under §12k. The GAPS entry says this part is done.
- Under the read-only fallback (a broken model), setting a state is refused like any other write.

## Relation to other work
- `regime-scheduled-gates`, `act-reshape`, `act-staleness-in-risk`: all build on this.
- No active gap touches `ergostat/actions/`. `ergostat/cli/gated.py` and `ergostat/spec/compile.py` are not named by an active gap.

## Files to touch
- `ergostat/actions/operating.py` (new)
- `ergostat/cli/gated.py`
- `ergostat/actions/compile.py`
- `ergostat/spec/compile.py`
- `ergostat/spec/load.py`
- `docs/SPEC.md`
- `docs/GAPS.md`
- `tests/test_operating_state.py` (new)

## Risks
- lesson-2: deciding which entry is in force by `at` would let two entries made in the same second read the wrong way round. The fold uses `seq`.
- lesson-3: an unreadable record, or a lease end that is not a number, must read as the strictest case, never as normal.
- lesson-5: freeze entered, ended, then entered again must not keep the old note or maintenance end time.

## Acceptance tests
- `tests/test_operating_state.py::test_precedence_incident_over_freeze_over_maintenance`: shows that ending maintenance under freeze leaves freeze in force.
- `tests/test_operating_state.py::test_order_is_by_seq_not_time`: two events with equal `at` and a reversed clock still fold in `seq` order.
- `tests/test_operating_state.py::test_maintenance_lapses_and_is_capped`: `--for 25h` is refused, and a 1 h lease reads as normal after its end.
- `tests/test_operating_state.py::test_reentry_starts_clean`: freeze with a note, then normal, then freeze with no note, gives no note.
- `tests/test_operating_state.py::test_unreadable_record_reads_incident_and_away`: the query is monkeypatched to raise.
- `tests/test_operating_state.py::test_presence_away_after`: away past the window and present within it; `away-after: 0s` and `8d` are each `bad-value`.

## Size budget
150 net lines
size: M (confidence: medium)
