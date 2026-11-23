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
