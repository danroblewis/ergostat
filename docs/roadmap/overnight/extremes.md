# extremes: extreme-conditions tests with the loops running, calibration per part, proposals that state their prediction

Branch `extremes`, from `closedloop` (8819129); rebased onto main once closedloop lands there. Gaps from `docs/GAPS.md`:
"Extreme-conditions tests and calibration per part of the model" (the Check page's first status takes seconds even on
small models), and the half of "Proposals drawn dashed … proposals that state the behaviour they predict" about the
stated behaviour.

## Definition of done

**Extremes.** The extreme-conditions test (Sterman, *Business Dynamics*, ch. 21) runs the closed-loop projection
(`closedloop.closed`: goals and built-ins on the engine's code, each machine block by its identified model, here
identified from no record, so each an assumption) from the model's own start, once per extreme: everything as usual;
every input from outside at 0; each input alone at 0 and at 10× its largest; each block that takes items with a pool
of 0; each goal's setpoint at its limits (0, and its stock's `limit:` or 10× the setpoint); each parameter at its
range's ends (kept from the open-loop test). It checks what cannot happen: a stock below empty; an outflow still
running from an empty stock; a stock that rises while nothing comes in; a one-way flow running backwards; an equation
that faults; a run that blows up or grows faster and faster (runs away); a controller's law with no limits still
moving its setting at the end (it does not saturate). Each violation is a finding (`extreme-conditions`) naming the
part, every extreme that showed it, and the projection's numbers. It replaces the open-loop replay the test used before
(`extremes._run` on `simulate.replay`, blocks held): every condition it ran is run here with the loops running. It is
**fast**: each condition's result is cached on disk in the state directory, keyed by the condition and the content of
the connected part of the model it can reach (`version._plain` of each part), so a second check runs nothing and an edit
reruns only the conditions whose part of the model changed; the total is bounded in time; it runs in a background
thread, so the Check page's status answers at once and says "extremes: running (k of n)" until done, and `ergostat
check` waits at most a few seconds for it and says what is left. **Calibration.** Each flow with an equation shows its
own partial-model fit on its panel, R² and scaled error and its skill against holding it at its mean; one that fits
worse than its mean (skill below 0, on enough record) is a finding (`calibration-worse-than-mean`) on the Check page and
in `ergostat check`. **Predictions.** Every change's effect (`review.effect`) states the closed-loop projection of the
stocks it touches, before and after, over its horizon, in one sentence ("backlog settles at 12 instead of 30 within
2h"), shown above the strip; accepting a change records that prediction on its item (`predicted`); once its horizon has
passed, the judge's pass reads what the stocks did and records `observed` beside it on the change item.

## Acceptance tests (`tests/test_extremes_closed.py`)

- `test_a_stock_that_goes_negative_at_zero_inflow_is_caught`
- `test_a_model_that_runs_away_at_ten_times_its_input_is_caught`
- `test_a_pool_at_zero_and_a_setpoint_at_its_limit_run_with_the_loops_running`
- `test_a_second_check_is_fast_from_the_cache`
- `test_an_edit_reruns_only_the_conditions_of_the_part_it_changed`
- `test_the_check_status_says_extremes_running_until_they_are_done`
- `test_an_equation_that_fits_worse_than_its_mean_is_a_finding_and_its_panel_says_so`
- `test_a_proposal_carries_its_prediction`
- `test_the_prediction_is_compared_with_what_happened_after_acceptance`

The existing extreme-conditions tests (`tests/test_sd_tools.py`, `tests/test_sd_review.py`) still pass, with the input
pushed to 10× (it was 100×). The four suites with rc 0, no page test skipped.

## Size

**Budget 600 net lines outside `tests/` and `docs/`.**
