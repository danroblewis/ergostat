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

## Where it stopped

Round 1, built (be4e5b2b). Net lines outside tests, docs and dev: +24 (41 added, 17 removed in `ergostat/`), budget 60.

What it does: `risk.staleness(p, run, item)` gives `s`. The run's start is the `agent.started` event whose id is the
run's id: both the engine and the runner write it that way. The event must have that exact id, since `events.get` also
matches an id's prefix, and that type. An event on the work item counts as a move when its `seq` is greater than the
start's and it is not `causedby` the run. The run's own writes, through `ergostat record`, a lease renewal or a session,
carry `causedby` = run, so they do not count. The cases that read as `s = 1` are: no run (`no asking run`), no item
(`no work item`), a start not found or of another type (`the run's start not found`), and a get or query that raises
(`record unreadable`). The request passes `ctx.run` and `ctx.item`. `at_act` passes the action's recorded `run` and
`item`, so `s` is worked out again inside the run lock. `risk` and `risk_at_act` carry `s` and `s_why`. `score()`
takes `s` as a required argument, so no caller can drop it and silently get 0.

Choices made without anyone to ask (each the most reversible):
- **Who counts as another writer.** "Another writer" means any event not `causedby` the asking run, whatever its
  `source`. So an engine event on the item with no `causedby` counts as a move, and so does one by the same block
  under another run. Erring that way gives s = 1, which is the stricter reading.
- **GAPS entry.** The house rules refuse a branch that edits `docs/GAPS.md`, which the queue writes from the records.
  So the *Left* line was emptied at its source: the clause "the staleness of the state an act was planned on" was
  removed from the umbrella's bullet in `dev/records/operating-modes-regime.md`. `docs/GAPS.md` itself is not edited.
  The `## Entry` below adds this gap's done line under that umbrella.
- **A test outside the Files list.** `tests/test_regime_gates.py` was changed, although it is not in the Files list.
  Without the change it fails on this gap's own definition. Its `ask` helper now sets up a fresh plan: a run started
  just now, on `ticket/1`. Without that, `test_threshold_by_state_steps_the_gate` would read s = 1 (no item) and score
  12 instead of 6. Its `away: 51` refusal became `away: 101`, because 51 is now a valid threshold.

Existing tests changed in `tests/test_act_risk.py`, by name:
- `ctx` and `ask` (helpers): `ask` now asks on a fresh plan, a run started just now (new helper `start`) on `ITEM`.
  `ctx` takes `run` and `item`. This change is what keeps every existing `ask`-based test at s = 0, with its numbers
  unchanged.
- `test_score_formula`: each `risk.score(...)` call is given `s = 0` (the argument is now required).
- `test_never_looser`: the two `risk.score(...)` calls are given `s = 0`.
- `test_risk_key_validated`: the refused threshold `t51: 51` became `t101: 101`. Done item 1 raises the ceiling to 100,
  so 51 is now valid. This change is not a fresh-plan setup: the definition forces it.

Each new test was broken on purpose and seen to fail, then the code was put back:
- `causedby` filter removed: `test_own_events_are_not_staleness` fails.
- `after_seq` replaced by `since=start time`: `test_staleness_by_seq_not_time` fails.
- `record unreadable` returning 0: `test_staleness_unknown_counts_one` fails.
- `at_act` reusing the request's `s`: `test_staleness_rechecked_at_the_act` fails (the act ran).

Run here, one file at a time through `scripts/named_tests.py`, all passing:
- `tests/test_act_risk.py` and `tests/test_regime_gates.py`: 46 passed.
- `tests/test_gated_actions.py`, `tests/test_inbox.py` and `tests/test_leased_workspaces.py`: 53 passed.
- `tests/test_repair_approver.py`, `tests/test_repair_verify.py` and `tests/test_interventions.py`: 61 passed and 1
  skipped. The skip is bwrap having no namespaces in this container, not a page test.

`ruff check ergostat tests scripts` is clean. Not run here: the whole unit suite and the four browser files (no page
changed), which the factory and the queue run. `main` had nothing new to merge (`HEAD..main` is empty).
`uv run python dev/bin/gapsdoc.py render --check` was refused here, so the Entry's form was not checked by the tool.
It follows the same form as `regime-scheduled-gates`' Entry: `entry-of:` followed by one `done:` line.

## Entry

entry-of: operating-modes-regime
done: 2026-11-24 The staleness of the state an act was planned on, in its act-risk, on `act-staleness-in-risk` (SPEC §12k): the score is S × (1 + s) × (1 + 4c) × (1 + n), s = 1 when the work item has an event from another writer with a seq after the asking run's start (or when the run, its start, the item or the record cannot be had), worked out at the request and again at the act; thresholds up to 100.
