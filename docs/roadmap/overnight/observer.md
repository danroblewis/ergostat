# observer: staleness and estimated stocks

Branch `observer`, from main at a09c176. Gap (`docs/GAPS.md`, *Observer staleness and estimated stocks*;
`docs/proposals/coordinator/06-observer.md` §3): controllers act on readings as if they were current and exact. This
branch builds the smallest useful observer (a state estimator): each reading's age and staleness, with a policy per
goal or block, and a scalar estimate per stock between readings, with its uncertainty and its innovations.

## Definition of done

**Staleness.** A stock, flow or auxiliary is *stale* when its newest reading is older than 3 times the period of its
quickest periodic sensor (`every`, or the gap of its `cron`); one with an `items`, `changes` or `manual` sensor, or no
reading yet, is never stale. A goal on a stale part shows the status `stale` (with the reading's age) on its goal and
controller panels and in "needs attention", and `ergostat.goal.stale` / `ergostat.goal.fresh` are recorded as it goes
stale and reads again. `on-stale:` on a goal: `act` (the default: error and off worked out from the stale value, as
today), `hold` (its `.error` and `.off` stay as they were when it went stale, so what it commands is kept) or `off` (it
counts as off: `.off` is 1, its error the last one). `on-stale:` on a block applies while anything it reads directly
(a stock, flow or auxiliary, or a goal on one) is stale: `act` (default), `hold` (a built-in is not stepped and keeps its
output; a machine block is not started) or `off` (the goals it reads are seen as off). A machine block's input JSON
names its stale inputs and their ages (`stale`) under every policy. **Estimated stocks.** Every stock with a sensor
and flows, or whose estimate a block reads, has an estimate: between readings the engine propagates it by its modelled
net flow (the flows' equations, worked out by simulate's stepper, where they have them; their measured rates
otherwise; the stock's last measured rate of change when a flow is neither), and at each reading it blends in the
reading with a fixed steady-state Kalman gain, scalar per stock, from the sensor's noise and the model's error, both
estimated from the record (the open-loop one-step errors between readings: noise from their lag-1 autocovariance, the
model's error from the rest of their variance; the gain for the median interval). `in:` may name
`stock.X.estimate` and `stock.X.uncertainty` (a standard deviation, in the stock's unit). The innovation (reading minus
prediction) is recorded as the series `observer/X/innovation`; five in a row more than 3 expected standard deviations
off record `ergostat.model.disagrees` and give the finding `model-disagrees` on that stock (in `check` and `ergostat
findings`, so modelling can take it as a request). **No change by default:** controllers read the measured value unless
they name the estimate; a model with no `on-stale:` and no `.estimate` makes the same commands, statuses and runs as
before. SPEC (goals, signals, the observer), the agent guide (when to read the estimate; stale policies) and GAPS (done,
with this commit; residual structure can build on the innovations) say so.

## Acceptance tests

- `tests/test_observer.py::test_a_stale_reading_turns_a_goal_stale_for_each_policy` (act, hold, off)
- `tests/test_observer.py::test_a_block_on_stale_hold_keeps_its_last_command`
- `tests/test_observer.py::test_a_machine_blocks_input_names_its_stale_readings`
- `tests/test_observer.py::test_the_estimate_tracks_a_stock_between_sparse_readings_better_than_the_last_reading` (measured: the error of each, printed)
- `tests/test_observer.py::test_the_gain_comes_from_the_sensor_noise_and_the_model_error`
- `tests/test_observer.py::test_innovations_are_recorded_as_a_series`
- `tests/test_observer.py::test_a_planted_model_error_raises_model_disagrees`
- `tests/test_observer.py::test_a_block_reads_the_estimate_and_its_uncertainty`
- `tests/test_observer.py::test_models_that_use_none_of_it_run_as_before`
- `tests/test_observer.py::test_on_stale_and_the_estimate_ports_are_checked`
- `tests/test_observer.py::test_the_page_says_a_goal_is_stale_and_needs_attention`
- the four suites, rc 0, no page test skipped.

## Size budget

600 net non-test lines (outside `tests/` and `docs/`); expected about 400.
