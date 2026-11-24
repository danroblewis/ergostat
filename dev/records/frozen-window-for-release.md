# frozen-window-for-release: A frozen window: work about to run is not reshuffled by new work unless it is marked urgent

depends-on: [forecast-promise-proposal]

A general, declared option for a block or item kind: items within a stated horizon or position keep their order when new work or re-ranking arrives. A declared urgent path can override it, recorded with who and why. The forecast and quotes simulate the same rule.

Definition of done.
1. Off by default, with existing models unchanged, proven by a test.
2. Tests cover re-ranking inside and outside the window, the urgent override and its record.
3. The simulated order matches the dispatcher's on a fixture.

Boundary (the owner, 2026-11-23). ergostat serves job shops with rework, batch and yield production, and make-to-stock alike. No production style is a principle of the core. The core offers general parts, off unless a model declares them, and names no gaps, merges, software or factories. The ergostat-on-ergostat factory is one user, a job shop with rework, and its choices live in its own model. A model read as a remote system must be able to expose these answers to the model reading it.

Build on what exists: the Monte Carlo over every open item (`ergostat/numbers/eta.py`, `etamodel.py`), its what-if overrides, its backtest (`tests/eta_backtest.py`), and the Timeline's calibration line. Do not start a second estimator.

Do not measure or change the live instance in the session.

## Where it stopped

Round 1, built. The window is by **position** (`takes: {frozen: {first: N, urgent: FIELD}}`), not by horizon.

- The one rule is `ergostat/leases/frozen.py` (`arrange`): urgent first, then the list in force still waiting, filled
  to N from the plain order, then the rest. The dispatcher (`Dispatcher.in_order`, for each look and `block --now`)
  and the simulation (`eta._Run.pick`) both call it, and `eta.reasons` (the Items tab's why and place) does too.
  The list is recorded as `block.frozen` about `ergostat.frozen/BLOCK` only when it changes, under the dispatcher's
  lock (its only writer), newest by `seq`. `etamodel.read` takes the list in force at its moment, so the backtest
  replays a past moment with the window then in force. The what-if path reads the same inputs. No second estimator.
- Done items. 1: `test_off_by_default_existing_models_unchanged` (no `frozen:`: plain re-rank, nothing written, the
  simulation's frozen path patched to fail and never reached). 2: `test_rerank_inside_the_window_holds_outside_takes_effect`,
  `test_urgent_goes_ahead_and_is_recorded_with_who_and_why` (the record's by, why and ahead; a bare flag and one
  without `why` override nothing and are said; the events read through `/remote/v1/events`). 3:
  `test_simulated_order_matches_the_dispatchers` (one fixture: window, re-rank inside and outside, urgent, later
  item; simulated start order == dispatcher's take order == the why's places, != the plain order). Also
  `test_frozen_checked_with_its_bounds`, `test_unreadable_list_takes_the_plain_order_and_says_so`, `test_newest_list_by_seq`.
- Seen to fail: the simulation without `pick` fails the done-3 test; `arrange` ignoring the list fails both
  re-rank tests; the broken record not written fails the urgent test (each mutation reverted).
- Run here: tests/test_frozen_window.py, test_take_order, test_eta, test_spec_schema, test_spec_structure,
  test_lease_watch_slices, test_faults_hold_by, test_scale_caches, test_daemon_lines, test_lease_end_turns,
  test_daemons, test_run_budget, test_library_untrusted_runs: all pass. ruff clean. Not run here: the whole unit
  suite and the four browser files (the factory's and the queue's); no page changed. No example touched.
- Size: about 210 net lines outside tests, docs and dev (budget 600).

Decisions taken alone (each the more reversible):
- Position, not horizon. A window by forecast start needs the standing runs (proposal §1, forecast-standing-runs),
  which are not on main; the horizon form (`for`, `every`, the renewal and lapse) is left to that gap, and
  `takes.frozen` can take those keys beside `first` without breaking a model that uses `first`.
- `frozen:` sits in `takes:` (the block's queue), not beside it as the proposal sketched; moving it is a rename.
- The urgent path is a field whose value says `{by, why}`: who and why are what the item carries, so the record
  holds them without reading the field's history. A bare flag or a missing `by`/`why` overrides nothing (the
  declared window is the safe reading) and is said once. An urgent item taken with no frozen item waiting broke
  nothing and is not recorded.
- The window is refilled at a look with room (the dispatcher) and at a take (the simulation), the same moments, so
  the two agree; a look with no room writes nothing.
- An unreadable list takes the plain order and is said by the dispatcher (proposal §5: a lost preference, never a
  stopped block); the estimates then project the plain order too.
- `Dispatcher.take` now returns True when its run started (it returned None either way off the inline path), so the
  override is recorded only for a take that happened.
- Quotes (forecast-quotes) are not on main; when they land they run through `eta._Run`, so the same rule applies.

## Entry

**Frozen window (built).** `takes: {frozen: {first: N, urgent: FIELD}}` keeps a block's next N items in their order
against re-ranks and new work; an item whose FIELD says `{by, why}` goes ahead, recorded as `block.frozen.broken`.
One rule (`leases/frozen.py`) for the dispatcher, the completion estimates and the Items tab's why; the list is the
record's `block.frozen`, served to a remote reader through its events. Off unless declared. Left: the window by
horizon (the items to start within a time), which waits on the standing runs.
