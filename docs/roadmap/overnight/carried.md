# carried: which runs carried over a model change is never lost to the page

Branch `carried`, from main at 07a07c1. Found in review: the page server has its own Project and writes to the same
event log as the engine (`cli/running.py`). When a page request notices a model change first, `Live.get` records
`model.changed` without `carried`; the engine's later `history.note(p, said)` sees the same fingerprint and records
nothing, so with the page open the record of which runs carried on under the old model is lost now and then. Also,
`tests/test_reload_in_place.py::test_ergostat_run_takes_an_edit_in_place_and_stop_still_kills` is flaky under load: it
reads the last `model.changed` once `agent.ran` arrives, which may still be the startup record; and `ergostat run`
begins following the model's files only after its first runs have started, so an edit made in that moment (as the
test makes it, at `agent.started`) is never taken.

## Definition of done

While a runner holds `run.pid` (`runner.running_pid`), the page server records no `model.changed`, neither when a
request notices the edited files nor when a proposal is accepted on the page: the runner (engine or TOML runner)
records it, with what carried over. With no runner, the page records model changes as today. `ergostat run` follows the model's files from before it
starts any run. The flaky test waits
for a `model.changed` that marks a reload (`reload` in its data), asserts it came before `agent.ran`, and its run is
long enough to take the edit under load. That test passes 10 times in a row, and while a full unit suite runs
alongside.

## Acceptance tests

- `tests/test_reload_in_place.py::test_a_page_noticing_the_change_first_leaves_it_to_the_runner` (the race: the page
  takes the edit before the engine swaps; the engine's record still says what carried, and there is one record)
- `tests/test_reload_in_place.py::test_ergostat_run_takes_an_edit_in_place_and_stop_still_kills` (10 in a row, and
  alongside a full unit suite)
- the unit suite and ruff, rc 0.

## Size budget

100 net non-test lines (outside `tests/` and `docs/`); expected about 10.
