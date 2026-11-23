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

## Where it stopped

Built, round 1. Every item of the definition is done. The six acceptance tests and one more
(`test_setting_a_state_is_refused_on_the_last_good_model`) pass. Each guard was broken by hand and a test failed: the
fold ordered by `at`, an entry merged over the earlier one of its state, a non-number lease end read as lapsed, and
incident and freeze swapped. Main had nothing new to merge (`HEAD..main` is empty).

Overrun reason: 194 net lines against 150. The extra is the strictest-case handling the risks ask for (an unknown state, a lease end that is not a number, an unreadable record, an overflowing or out-of-bounds `away-after`), the CLI's refusals (a lease past 24 h, `--for` off maintenance, an `--actions` name not in the model), and 6 lines of `operating:` in `schema/ergostat.schema.json` so a model using it stays valid against the schema.

Choices taken where nobody could be asked (each reversible):
- Each of incident, freeze and maintenance is held as its own layer. `normal` ends the strongest one held, so ending an
  incident entered over a freeze leaves the freeze in force. This is the stricter reading of "only the owner's typed
  act ends a freeze".
- The whole `operating` topic is refused under the read-only fallback, showing included. It is not in
  `goodmodel.READS`, and adding it there is a one-line change if showing is wanted.
- "An event from the owner" is an event whose `source` is `owner`.
- `away_after` is a field on `Spec` (`ergostat/spec/ir.py`, one line), and the `operating` topic has a line in the
  CLI's help (`ergostat/cli/__init__.py`). Neither file was in the list to touch.
- Not covered (said in SPEC): a state entered longer ago than the model's `keep:` is pruned with its event and then
  reads as `normal`. Keeping it belongs with the record's pruning, outside this gap.

Round 2. The one finding, the conflict with main in `docs/SPEC.md`, is answered by the merge of main (b6d7a1db) in
bd812a8e. It also conflicted in `ergostat/spec/ir.py`, `ergostat/spec/load.py` and `schema/ergostat.schema.json`,
where main had added `runs:` and `dashboards:` next to this gap's `operating:`. Each was resolved by keeping both
sides: §12k's new subsection sits before main's "Compute pools", and `TOP`, `Document`, `Spec` and the schema hold
both keys. No code changed outside the merge, so the net lines and the overrun reason above stay as they were. After
the merge, `tests/test_operating_state.py` (7 passed), `tests/test_spec_schema.py`, `tests/test_dashboards.py` and
`tests/test_runs_outlive_engine.py` (82 passed) pass, and ruff is clean. The unit suite and the browser files were not
run here; the factory runs them.
