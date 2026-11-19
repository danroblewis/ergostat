# closedloop: closed-loop simulation

**The gap** (GAPS.md, Modelling; docs/proposals/coordinator/12-model.md §7 gap 1): projection, what-if and the
sensitivity fan held the blocks still, so none could say what happens if the system keeps running: whether a
backlog drains, a loop holds, or what doubled arrivals do.

*Written after the work, at the gate review's request (2026-11-19): the branch began before the overnight gates, so
this file is not its first commit.*

## Definition of done

The projection runs the control structure forward beside the stocks and flows, the default wherever the model has
controllers, with **Held** one click away. Goals and built-in blocks run on the engine's own code, started from the
state the record lets us rebuild (what it cannot rebuild is said). Each machine block runs as an identified model of
what it does to its flow (servers, equation, fill, drain, rate, law), identified from the record with its standard
errors, said in words, and flagged as an assumption where the record is too short. The causes strip, what-if
(parameters, an input's rate, a setpoint, a pool), the fan, a goal's panel, proposal effects and `ergostat project` use
it, with no new page. Risk is a bounded, seeded Monte Carlo giving each goal's probability of being off at the horizon
and its expected time off, invalid runs counted as off. It is validated against held-out record on the coordinator,
the-job and ticket-factory, and the numbers, R² included, are reported honestly in MODEL-TOOLS.md.

## Acceptance tests (`tests/test_closedloop.py`)

- `test_built_ins_decide_exactly_as_the_engine_does`
- `test_the_engines_own_pass_and_the_shadow_agree_on_a_reading`
- `test_the_shadow_started_from_the_record_mid_run_decides_as_the_engine_goes_on_deciding`
- `test_a_draining_blocks_identified_model_is_little_s_law_from_its_record`
- `test_a_block_that_takes_items_is_servers_from_its_runs`
- `test_a_block_that_moves_while_nothing_commands_it_is_not_gated_by_its_command`
- `test_a_written_law_keeps_its_deadband_resolution_and_limits`
- `test_an_onoff_drain_loop_settles_between_its_release_point_and_its_setpoint`
- `test_arrivals_doubled_the_queue_grows_and_the_controller_saturates`
- `test_a_setpoint_tried_moves_where_the_loop_settles`
- `test_a_goal_on_a_count_of_items_reads_a_whole_number_as_the_engine_does`
- `test_risk_is_reproducible_with_a_seed_and_bounded`
- `test_a_run_that_is_not_valid_counts_as_off_and_is_said`
- `test_the_page_projects_with_the_loops_running_and_tries_what_ifs`
- `test_parse_whatif_splits_parameters_from_what_only_the_closed_loop_tries`

The validation (`tests/closedloop_validate.py`, not run by the suite) and the four suites with rc 0.

## Size

**Budget 600 net lines outside `tests/` and `docs/`; the branch is about 1,160** (1,438 before the review's cuts). The
overrun is the scope the gap asked for, in four parts that each stand alone:

- **identification** (`blockmodels.py`, about 310): six forms of model, each identified from a different part of the
  record (runs, leases, a flow while commanded, a stock's level), with standard errors and one sentence each;
- **the closed run and the risk** (`closedloop.py`, about 510): rebuilding the built-ins' state from the record (the
  review's first blocking item, about 70), the shadow on the engine's own methods, the control hook's other side, the
  what-ifs only a closed loop can try, and the Monte Carlo with its bounds;
- **the page** (about 220 across `numbers_api.py`, `charts.js`, `details.js`): the mode, the fan and the risk worked out
  apart from the request, the models and the pool what-if in the strip, the goal's line;
- **the command line** (about 105): `ergostat project`, the only way to read a projection without the page.

The simulator itself is not copied: `simulate.project` gained a control hook (about 20 lines), and the bands, the
quantiles, the estimates and the uncertain parameters' filter live in `sensitivity.py` for the fan and the risk alike.
