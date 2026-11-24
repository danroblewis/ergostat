# act-staleness-in-risk: act-risk counts how far the record moved under the run that planned the act
depends-on: [regime-scheduled-gates]

## Definition of done
- The score becomes `S × (1 + s) × (1 + 4c) × (1 + n)`, with staleness `s` 0 or 1. `HIGHEST` and the threshold ceiling
  become 100, and SPEC §12k's formula, limits and the sentence "staleness is not part of the score" are replaced.
- `s = 1` when the action's work item has events from writers other than the asking run, with `seq` greater than that
  run's start. `s = 1`, each with its own `s_why`, also when there is no asking run, no work item, the run's start
  cannot be found, or the record cannot be read. Otherwise `s = 0`. Order is compared by `seq`, never by time.
- `s` and `s_why` are recorded on `risk` at the request and on `risk_at_act`. At the act, `s` is worked out again on the
  record as it is then.
- Existing tests in `tests/test_act_risk.py` change only to set up a fresh plan (s = 0) where they meant one, and the
  report names each one changed.
- The GAPS entry's *Left* line is emptied for this gap.

## Relation to other work
- regime-scheduled-gates: waits for it (both edit `gate.py` and `risk.py`).
- act-reshape: no overlap except `gate.py`. Either may land first after regime-scheduled-gates.

## Files to touch
- `ergostat/actions/risk.py`
- `ergostat/actions/compile.py`
- `ergostat/actions/gate.py`
- `docs/SPEC.md`
- `docs/GAPS.md`
- `tests/test_act_risk.py`

## Risks
- lesson-2: "moved since the run started" must compare `seq`, never `at`. Two events in the same second must still be ordered.
- lesson-3: a run or start that is not found, no item, or an unreadable record must each give s = 1, never 0.
- lesson-9: the move must come from another writer. Events the asking run wrote itself must not count, or every act would read as stale.

## Acceptance tests
- `tests/test_act_risk.py::test_staleness_when_item_moved_by_another_writer`: an event by another source after the run's start gives s = 1, and the gate steps.
- `tests/test_act_risk.py::test_own_events_are_not_staleness`: events written by the asking run alone give s = 0.
- `tests/test_act_risk.py::test_staleness_by_seq_not_time`: a later `seq` with an earlier `at` still counts as moved.
- `tests/test_act_risk.py::test_staleness_unknown_counts_one`: no run, no item, and a query that raises each give s = 1 with its own reason.
- `tests/test_act_risk.py::test_staleness_rechecked_at_the_act`: the item moves between the approval and the act, so the act is re-held.

## Size budget
60 net lines
size: M (confidence: medium)
