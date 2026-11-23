# model-data-source: Bode, Nyquist and pole-zero come from fitted or declared models

depends-on: [chart-result-shapes]

Owner's design, 2026-11-23. A dashboard data source is, as in Grafana, a connection, a query language and a typed result. Each panel query is text in its source's language. Visual query builders are not wanted. Metrics hold aggregates over bounded labels; anything with a generated ID stays in the event log. The event log remains the source of truth.

Problem. Frequency plots drawn from arbitrary series were mostly noise: 381 of 383 points unreliable on arrivals against completions. A response needs a real input and output, an input that moves, regular samples, roughly stable behavior and care in closed loop.

Change.
- A `model` data source returns a transfer function from a goal's declared or identified process, using the existing control code. Bode, Nyquist and pole-zero draw it.
- A fit from a step test (first-order plus delay at least) produces such a model, with its fit quality.
- The from-data estimate takes an explicit input and output. When coherence is poor it says this data cannot support a frequency response and does not draw a curve as if it were one.
- Replace the default dashboard's Bode, Nyquist and pole-zero examples with one from a model.

Definition of done.
1. Known transfer functions match analytic gain and phase.
2. A simulated step test recovers gain, time constant and delay within a stated tolerance.
3. Uncorrelated input and output yields the refusal, not a curve.

## Amendment from the chart catalog

See `docs/research/2026-11-23-charts/catalog.md` section 7.2. Refuse by catalog rule G5, on the server: a per-frequency coherence floor alone passes most noise records. Remove the fixed 0.6 in `plots-freq.js`. Pole-zero of a delayed process uses the discrete model and states `dt`.

## Entry

**Bode, Nyquist and pole-zero from a model** (model-data-source). A data source of type `model` (one named `model` is
there undeclared; `ergostat/datasources/model.py`) answers a `response` frame in a one-line language: `goal NAME`
(declared process, else the one its record identifies), `goal NAME declared|identified`, `fopdt gain= tau= delay=`,
`ipdt gain= delay=`, each with an optional `dt=`. The frequency response is exact (`lti.response`); a delayed process's
poles and zeros are its zero-order-hold sampled model's at a stated `dt` (`lti.poles_zeros`). An identified process
carries its fit (share held out followed, standard errors, from step tests or not) and is refused with the record's
reasons when not told apart. The default dashboard's three examples ask it. A public reader may ask it, and no outside
source. SPEC §4d, §4e (*The model as a data source*), §11. Left: no query editor of its own for the language (plain text
field), and the identification is not cut at the source's 10 s bound.

## Where it stopped

Built, round 1. Every definition-of-done item has a passing test, each seen to fail when the code it guards was broken:

1. Known transfer functions: `tests/test_model_data_source.py::test_known_transfer_functions_match_analytic_gain_and_phase`
   (FOPDT with and without delay, a negative gain, an integrator with delay, a goal's declared process; gain, unwrapped
   phase, re and im against the analytic form to 1e-6), and the corner test beside it.
2. Simulated step test: `::test_a_simulated_step_test_recovers_gain_time_constant_and_delay`. Tolerance: K within 5%,
   τ within 10%, θ within one sample (10 s), the same as `tests/test_control.py`'s step-test test; the fit is answered
   with it (follows more than 50% held out, the standard error of K under 5% of K). A fit found but not told apart is
   refused (`::test_a_process_found_but_not_told_apart_is_refused_not_drawn`; that test stubs `loop.identify`, since no
   simulated record found quickly gave that case).
3. Uncorrelated input and output: `::test_uncorrelated_input_and_output_yield_the_refusal_not_a_curve`, through the
   query API with explicit input and output, against a related pair on the same path that is drawn. The server's
   refusal (rule G5: the Bonferroni-corrected floor) and the removal of the fixed 0.6 in `plots-freq.js` were already on
   main from `frequency-refuses-noise`; this branch takes them as given, as catalog §7.3 says.

Amendment: a delayed process's pole-zero is the sampled model's and states `dt`
(`::test_a_delayed_process_has_the_poles_and_zeros_of_its_sampled_model_at_the_dt_it_states`, and in the page,
`tests/test_plot_forms.py::test_a_sampled_models_pole_zero_map_draws_the_unit_circle_and_states_its_dt`). The default
dashboard: `tests/test_dashboard_page.py::test_the_default_draws_no_response_from_arrivals_against_completions` (now the
model source's query) and `::test_the_model_source_draws_bode_nyquist_and_pole_zero_from_the_live_server` (the real server).

Choices taken without the owner, each the more reversible:
- "Replace ... with one from a model" is read as: the three examples stay (the every-family test needs all three), each
  asking the model source. The old `frequency` query's `model: {goal}` route is kept, answered by the same code.
- The model source needs no declaring: a source named `model` is implicit unless one declared takes the name.
- A reader under `open: read` may ask a `model` source (it reads only the project's own model and record, as the
  reader's other queries do); every other type stays refused to them.
- A delayed process with no `dt` is sampled at the goal's controller period, else a quarter of the dead time; past 64
  periods of delay the query is refused, asking for a longer `dt`.
- The language takes durations as `30s`, `5m`; an integrator's written gain is per second (a goal's `process:` gain of an
  integrator stays per hour, converted as before).

Not done: the identification under `goal NAME identified` runs to the end once begun (the 10 s source bound is checked
before asking, not inside `loop.identify`); a sensor cannot read a `model` source (not asked for). No screenshot was
taken: setting `DASHBOARD_SHOTS=/shots` on the test command, and building a draft link with `printf | base64` for
`walk.py`, were both refused by the session's command permissions. The full unit suite and the four browser files were
not run here (the factory runs them); the files touched were, each passing.
