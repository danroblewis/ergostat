# Classical and frequency-domain control charts for ergostat

Research date: 2026-11-23. Scope: charts from classical control, process control and control loop performance assessment (CLPA), judged for software and operations loops.

## 1. Verdict

**Most of the classical canon should not be a first-class chart in ergostat.** Bode, Nyquist, root locus and their relatives describe a *linear time-invariant model*. Production software rarely hands you one: gains move with load, actuators are integer and clamped, queues floor at zero, and excitation is whatever traffic happened to do. The charts that earn their place first are the ones CLPA built for exactly this situation: routine closed-loop data, no model, a fleet of loops, and nobody allowed to run an experiment.

Six findings shape everything below.

1. **The unit of analysis is a loop, not a metric.** Nearly every useful chart needs setpoint (SP), measured value (PV), controller output (OP), actual actuator position (MV), limits and mode, aligned. "Two signals" is not enough. A `LOOP` shape and a loop registry are the top infrastructure item.
2. **Plotting output against input from closed-loop data can return the inverse of the controller instead of the plant.** In a simulation with true plant gain 1.0 and controller gain 3, regressing y on u gave **-0.333 (exactly -1/C)**. Adding setpoint excitation moved it to 0.249, still wrong, because a static fit ignores dynamics. A tool must refuse to label such a fit "process gain".
3. **`rate()` windows are part of the loop when a controller consumes them, and hide oscillations when a human reads them.** A 60 s oscillation has **exactly zero amplitude** in a 60 s boxcar average. On a reference loop tuned to Ms 1.59, feeding the controller a window of 2x the dead time raised Ms to 2.76, and 4x raised it to 6.10 (section 11).
4. **Ziegler-Nichols should not be offered as a recommendation.** On the reference plant it gave Ms 2.43-4.07, against 1.59 for SIMC. Åström & Hägglund state that its quarter-amplitude criterion "gives closed-loop systems with poor robustness" ([Advanced PID, ch. 6][apid6]).
5. **The Harris index is only as good as the assumed delay.** The same data scores 0.55, 0.81 or 0.95 for an assumed delay of 1, 2 or 3 samples. Never show it without the delay and its uncertainty.
6. **The most valuable software chart is missing from the classical canon: the static operating curve** (throughput or latency against load, with hysteresis). It shows gain variation, saturation and metastable states, none of which a Bode plot at one operating point can show.

## 2. How to read the entries

**Result shapes.** Existing: `time series`, `dimensions to measures`, `points`, `distribution`, `two signals`, `transfer function`.

**Four new shapes are needed:**

| New shape | Contents | Why existing shapes fail |
|---|---|---|
| `LOOP` | Aligned SP, PV, OP, MV; limits; mode; segments; annotations; sample period; known window | "Two signals" loses the setpoint, the clamp and the mode |
| `FREQUENCY RESPONSE` | Frequency, complex value, coherence, confidence band, provenance (model or estimate) | An estimate is not a transfer function and must carry its uncertainty |
| `FAMILY` | Parameter or parameter grid mapped to curves, roots or scores | Root locus and tuning maps are sweeps |
| `GRAPH` | Nodes, signed edges, gains, delays, provenance per edge | Block diagrams and signal-flow graphs are structure |

**How to obtain:** `PromQL`, `PromQL + transform (named)`, `SQL` over item events, `model` (fitted or declared), `experiment` (active, always a gated action).

**Entry numbering** follows the brief: 1 name and aliases, 2 question and decision, 3 reading, 4 data, 5 shape, 6 how to obtain, 7 misuse and guard, 8 software applicability, 9 priority, 10 sources.

**Priority:** **must-have**, **useful**, **niche**. Must-have means ergostat's core question cannot be answered well without it.

**Evidence labels.** `[checked]` means I computed or simulated it (section 11). `[unsure]` means a rule of thumb or a claim I could not confirm in a primary source. Textbook-standard results are otherwise cited without a label.

**Reference plant** for numeric examples: P(s) = e^(-2s) / (10s + 1), a first-order lag with delay.

## 3. Time-domain response

### A1. Loop trend
1. **Name and aliases:** SP/PV/OP trend, faceplate trend, strip chart.
2. **Question and decision:** What did the loop try to do, and what happened? Decides whether the problem is the controller, the actuator or the demand.
3. **Reading:** PV should track SP while OP moves smoothly inside its limits. Bad: OP pinned at a limit, OP and PV cycling, OP moving with PV flat (dead actuator), mode changes before an incident.
4. **Data:** SP, PV, OP, MV, limits, mode, on one clock. Sample at least 4-10 times per closed-loop rise time `[unsure: rule of thumb]`. Open or closed loop. No stationarity assumption.
5. **Shape:** `LOOP`.
6. **Obtain:** PromQL, with SQL annotations for deployments and config changes.
7. **Misuse and guard:** Mixing windows across signals creates false lag. Warn when signals have different sample periods or `rate()` windows, and print the window on the axis.
8. **Software:** Yes. HPA: `spec_target_metric`, `status_target_metric`, `status_desired_replicas`, `status_current_replicas`, min and max on one panel.
9. **Priority:** **Must-have.** Every other diagnosis starts and is sanity-checked here.
10. **Sources:** [kube-state-metrics HPA][ksm]; [FBS ch. 1, 11][fbs].

### A2. Step response
1. **Name and aliases:** setpoint response, bump response (open-loop form is D1).
2. **Question and decision:** How fast and how cleanly does the loop reach a new target? Decides whether to accept a tuning.
3. **Reading:** Rise time, overshoot, settling time, steady-state error. Good: little overshoot, settles in a few time constants. Bad: ringing, offset, or asymmetry between up and down steps (nonlinearity).
4. **Data:** A real SP change, larger than noise, with quiet load. Record at least 5 settling times. Linear near the operating point if a single curve is to generalise.
5. **Shape:** `LOOP` per event; overlaid `time series`; `transfer function` when simulated.
6. **Obtain:** PromQL + transform (event-aligned segments) for observed steps; model for predicted; experiment if none occur.
7. **Misuse and guard:** Reading one step as *the* response. Require up and down steps at the operating point before quoting a metric, and show n.
8. **Software:** Yes. Raise a worker-pool target from 10 to 20 and measure time until queue wait returns to objective.
9. **Priority:** **Must-have.** The most legible way to show loop quality to non-specialists.
10. **Sources:** [FBS ch. 6][fbs]; [Ogata][ogata]; [python-control][pyctl].

### A3. Impulse response
1. **Name and aliases:** weighting function, finite impulse response (FIR) estimate.
2. **Question and decision:** How long does a brief shock echo? Decides memory length for models and dead-time estimates.
3. **Reading:** Initial flat region is delay; decay gives time constant; oscillating tail means low damping; no decay means integrator.
4. **Data:** A true short pulse, or an FIR fit from persistently exciting input. For closed-loop data, use a method that handles feedback.
5. **Shape:** `two signals` in, `time series` out.
6. **Obtain:** PromQL + transform (FIR or ARX fit); model; experiment.
7. **Misuse and guard:** An FIR fit on closed-loop data without excitation estimates the wrong thing. Refuse without an excitation check.
8. **Software:** Partly. A one-minute traffic burst and its queue decay is a natural impulse; integer and floor effects distort it.
9. **Priority:** **Niche.** Keep as a by-product of model fitting, since A5 answers the operator's version.
10. **Sources:** [FBS ch. 6][fbs]; [Forssell & Ljung][fl99].

### A4. Ramp response
1. **Name and aliases:** velocity-error test.
2. **Question and decision:** Can the loop follow steadily growing demand? Decides whether it needs more integral action or feedforward.
3. **Reading:** Constant lag behind the ramp indicates finite velocity error; growing error means the loop cannot follow.
4. **Data:** SP or load ramping for several closed-loop time constants, without saturation.
5. **Shape:** `LOOP`.
6. **Obtain:** PromQL + transform (ramp segment detection); model; experiment.
7. **Misuse and guard:** Blaming tuning when the actuator is rate-limited. Check MV slew against limits first.
8. **Software:** Yes. Morning traffic ramp against an autoscaler: constant replica lag is ramp error.
9. **Priority:** **Useful.** Daily ramps are the commonest real test signal in operations.
10. **Sources:** [Ogata][ogata]; [FPE][fpe].

### A5. Disturbance (load) response
1. **Name and aliases:** load-rejection response, regulatory response, recovery curve.
2. **Question and decision:** When something hits the system, how large is the excursion and how fast is recovery? Decides whether the loop protects its objective.
3. **Reading:** Peak deviation, integrated absolute error (IAE), recovery time. Slow tail suggests too little integral action; ringing suggests too much gain. Failure to return after the disturbance ends suggests metastability (G3).
4. **Data:** Identified disturbance events with onset time, PV, OP. Several events to compare.
5. **Shape:** `LOOP` per event; `distribution` of peak and recovery.
6. **Obtain:** PromQL + transform (event alignment), SQL for incident or deployment markers; model; experiment (fault injection).
7. **Misuse and guard:** Comparing events of different size. Normalise by disturbance size where measurable and otherwise say it was not.
8. **Software:** Yes, and this matters more than setpoint tracking because most targets rarely change. Example: node loss, then latency recovery.
9. **Priority:** **Must-have.** Operational loops mostly regulate against load.
10. **Sources:** [FBS ch. 12][fbs]; [Advanced PID ch. 6][apid6].

### A6. Tracking error views
1. **Name and aliases:** control error trend, IAE/ISE, error histogram.
2. **Question and decision:** How far from target, how often, in which direction? Decides whether to act and ranks loops.
3. **Reading:** Mean near zero with integral action. Biased error implies saturation or no integral action. Bimodal error implies limit cycle or two regimes. Heavy tails imply bursts.
4. **Data:** SP and PV over a representative window, excluding manual mode and SP transients where the metric is about regulation.
5. **Shape:** `time series`, `distribution`, or `dimensions to measures`.
6. **Obtain:** Plain PromQL for error and `avg_over_time`; PromQL + transform for IAE by segment.
7. **Misuse and guard:** Comparing raw IAE across units. Normalise to the objective or tolerance band. Warn when SP is not recorded rather than assuming a constant.
8. **Software:** Yes. Queue wait minus objective; fraction of time inside an SLO band.
9. **Priority:** **Must-have.** Cheap, and it is the base metric for the fleet view.
10. **Sources:** [FBS ch. 11][fbs]; [GE loop KPIs][gekpi].

### A7. Control effort and actuator travel
1. **Name and aliases:** movement index, valve travel, churn.
2. **Question and decision:** Is the controller working the actuator too hard? Decides whether to add damping, deadband or a slower policy.
3. **Reading:** Total variation of OP relative to the error it removed. High travel with no PV improvement is pure waste.
4. **Data:** OP or MV, at the controller's real update rate.
5. **Shape:** `time series`; `dimensions to measures` across loops.
6. **Obtain:** PromQL (`changes()`, or summed absolute increments through a subquery).
7. **Misuse and guard:** Coarse sampling undercounts reversals. State the sample rate and mark the value as a lower bound if slower than the controller.
8. **Software:** Yes, and costs are direct: pod churn, cold starts, cache loss, rebalance storms.
9. **Priority:** **Must-have.** Replica churn is a real bill and the usual price of aggressive tuning.
10. **Sources:** [GE Process+ KPIs][gekpi].

## 4. Frequency domain

### B1. Bode plot of the loop
1. **Name and aliases:** open-loop frequency response, L(iw) plot.
2. **Question and decision:** At which time scales does feedback work, and how close is it to instability? Decides gain, integral time, and filter or window changes.
3. **Reading:** High gain below crossover, roll-off above, adequate phase at crossover. Delay shows as phase falling ever faster with frequency. Reasonable margins: phase 30-60 degrees, gain 2-5 ([FBS ch. 10][fbs]).
4. **Data:** L = PC from a model, or estimated P with known C. Linear and time-invariant around one operating point.
5. **Shape:** `transfer function`, or new `FREQUENCY RESPONSE` if estimated.
6. **Obtain:** Fitted or declared model; experiment for a credible estimate.
7. **Misuse and guard:** A crisp curve from a weak fit looks authoritative. Show provenance, operating point and coherence band, and grey out frequencies above the Nyquist limit or beyond what the data excited.
8. **Software:** Conditional. A queue plus autoscaler at fixed utilisation can be linearised, as in the TCP/AQM analysis by [Hollot et al.][hollot]. It holds only locally.
9. **Priority:** **Useful.** The right design view once a model exists, but wrong as a default chart.
10. **Sources:** [FBS ch. 10, 12][fbs]; [Skogestad & Postlethwaite][sp]; [python-control][pyctl].

### B2. Nyquist plot
1. **Name and aliases:** polar plot of L(iw).
2. **Question and decision:** Is the closed loop stable, and how close does L pass to -1? Decides stability when Bode margins are ambiguous.
3. **Reading:** Closed-loop unstable poles Z = N + P, with N clockwise encirclements of -1 and P open-loop unstable poles. Minimum distance to -1 is 1/Ms.
4. **Data:** L from a model, including delay. Linear time-invariant.
5. **Shape:** `transfer function`; `FREQUENCY RESPONSE` possible but risky.
6. **Obtain:** Model.
7. **Misuse and guard:** Applying the criterion to an estimate with no low-frequency data, or forgetting P. Refuse a stability verdict unless P is known and the curve is model-based.
8. **Software:** Rarely directly. Example: an autoscaler with pod-start delay, where the curve shows delay spiralling toward -1. An operator would read a delay margin faster.
9. **Priority:** **Niche.** Correct and fundamental, but its answer is better delivered as a margin number.
10. **Sources:** [FBS ch. 10][fbs]; [python-control][pyctl].

### B3. Nichols chart
1. **Name and aliases:** gain-phase plot with M and N contours.
2. **Question and decision:** From open-loop shape, what closed-loop peak results? Supports manual loop shaping.
3. **Reading:** Curve should clear the critical point at (-180 degrees, 0 dB); tangency with an M contour gives the closed-loop peak.
4. **Data:** As B1.
5. **Shape:** `transfer function`.
6. **Obtain:** Model.
7. **Misuse and guard:** Unreadable to non-specialists. Offer only in an expert view of a model.
8. **Software:** Technically yes, practically no. No operations decision is better served by it than by B4 and B7.
9. **Priority:** **Niche.** Skip unless a control engineer asks.
10. **Sources:** [Ogata][ogata]; [FPE][fpe]; [python-control][pyctl].

### B4. Sensitivity and complementary sensitivity
1. **Name and aliases:** S and T, |S|, |T|, Ms and Mt plot.
2. **Question and decision:** At which time scales does this loop reduce disturbances, and where does it **amplify** them? Decides whether a retune merely moves the pain.
3. **Reading:** |S| < 1 attenuates, |S| > 1 amplifies. Peak Ms = 1/(minimum distance to -1). Ms = 2 guarantees GM >= 2 and PM >= 29 degrees; Ms = 1.4 guarantees 3.5 and 41.8 `[checked]`. Bode's integral means reducing |S| in one band raises it elsewhere (the "waterbed").
4. **Data:** L from a model, or S estimated from a measured disturbance-to-output response with sufficient excitation.
5. **Shape:** `transfer function`; `FREQUENCY RESPONSE`.
6. **Obtain:** Model; empirical spectrum ratio with feedback on and off is an experiment.
7. **Misuse and guard:** Promising disturbance rejection at every frequency. When a proposed tuning lowers |S| in one band, show where it rises.
8. **Software:** Yes, and it explains a common surprise: an autoscaler that smooths 10-minute swings can amplify 1-minute ones.
9. **Priority:** **Must-have** (model-backed). It is the most decision-relevant frequency-domain chart.
10. **Sources:** [FBS ch. 12][fbs]; [Stein][stein]; [Skogestad & Postlethwaite][sp].

### B5. Gang of Four, Six or Seven
1. **Name and aliases:** closed-loop transfer function matrix.
2. **Question and decision:** Does a loop that looks good from setpoint to output hide a bad response elsewhere? Decides whether a design is safe to accept.
3. **Reading:** Four panels: S, T, PS (load to output), CS (noise to control). Large CS means noise drives the actuator. Large PS means load disturbances get through. A pole-zero cancellation can look fine in T and be poor in PS.
4. **Data:** Separate P and C; F as well if feedforward is present.
5. **Shape:** `transfer function`, multiple.
6. **Obtain:** Model.
7. **Misuse and guard:** Showing only T. **Terminology varies:** Advanced PID says Gang of Six; the FBS edition I read says Gang of Seven with a two-degree-of-freedom controller. Label panels by transfer function, not by the nickname.
8. **Software:** Yes, if a model exists. CS shows metric noise producing replica churn; PS shows traffic reaching latency.
9. **Priority:** **Useful.** The correct review panel for a proposed tuning, reachable only from a model.
10. **Sources:** [FBS ch. 12][fbs]; [Advanced PID ch. 6][apid6].

### B6. Loop shaping view
1. **Name and aliases:** open-loop shaping, target loop.
2. **Question and decision:** What controller gives enough gain at low frequency and enough roll-off high up? Used to design a compensator.
3. **Reading:** Compare |L| against disturbance-rejection and noise bounds; crossover must stay well below the limit set by delay.
4. **Data:** Trusted P, explicit objectives by frequency.
5. **Shape:** `transfer function` plus bounds.
6. **Obtain:** Model.
7. **Misuse and guard:** Pushing crossover past the delay limit. Draw the delay-imposed limit and refuse designs beyond it.
8. **Software:** Rarely. Most software controllers are not free-form compensators; their adjustable parameters are few (target, windows, step limits).
9. **Priority:** **Niche.** Use D4 tuning maps for the parameters that actually exist.
10. **Sources:** [FBS ch. 12][fbs]; [Skogestad & Postlethwaite][sp].

### B7. Stability margin plot
1. **Name and aliases:** GM/PM/delay margin, disk margin, margin against operating point.
2. **Question and decision:** How much extra gain or delay can this loop survive, **at each load level**? Decides whether a loop is safe at the coming peak.
3. **Reading:** Plot margin against load. Good: stays above floor across the range. Bad: collapses near high utilisation. Delay margin = PM (radians) / crossover frequency. Disk margins cover simultaneous gain and phase variation and are stricter than classical margins.
4. **Data:** A model per operating point, or a parametric model with gain as a function of load (G2).
5. **Shape:** `FAMILY`; `dimensions to measures` for a fleet table.
6. **Obtain:** Fitted model; declared model; experiments at several loads.
7. **Misuse and guard:** Quoting a single margin for a nonlinear loop. Require the operating point on every number, and show a range when the gain estimate is uncertain.
8. **Software:** Yes. M/M/1 latency sensitivity to utilisation is **25x larger at 90% than at 50%** `[checked]`, so a margin measured off-peak says little about peak.
9. **Priority:** **Must-have.** Delay margin against load is the frequency-domain number operators can act on.
10. **Sources:** [FBS ch. 10][fbs]; [Seiler, Packard & Gahinet][disk]; [python-control][pyctl].

### B8. Empirical frequency response and coherence
1. **Name and aliases:** ETFE, Welch transfer estimate, magnitude-squared coherence.
2. **Question and decision:** Can a frequency response be measured from data, and at which frequencies is it believable? Decides whether B1 and B4 can be trusted.
3. **Reading:** Coherence near 1 means the output at that frequency is linearly explained by the input. Low coherence means noise, nonlinearity or no excitation there, and the gain estimate should not be read.
4. **Data:** Input and output, evenly sampled, long enough for many averaged segments. Stationary. In closed loop, use an external reference as an instrument.
5. **Shape:** `two signals` in, `FREQUENCY RESPONSE` out.
6. **Obtain:** PromQL + transform (Welch cross-spectrum, `scipy.signal.coherence`). Prometheus has no spectral or correlation function ([docs][promfn]). Experiment for credible results.
7. **Misuse and guard:** High coherence in closed loop does **not** imply causal plant gain, because feedback correlates input and output. Refuse a "plant" label without external excitation, and hide gain where coherence is low.
8. **Software:** Yes, with a deliberate small traffic-weight dither on a canary. Natural daily cycles excite only very low frequencies.
9. **Priority:** **Useful.** It is the honest bridge from telemetry to frequency-domain charts.
10. **Sources:** [SciPy coherence][scipycoh]; [Forssell & Ljung][fl99].

### B9. Power spectrum and spectrogram
1. **Name and aliases:** PSD, periodogram, time-frequency plot.
2. **Question and decision:** Is there periodic behaviour, and at what period? Separates a loop oscillation from scheduled jobs and daily cycles.
3. **Reading:** A sharp peak suggests an oscillation or a schedule; harmonics suggest a nonlinear limit cycle. Spectrogram shows when it began. Peaks at round periods (60 s, 1 h) suggest cron or scrape artefacts.
4. **Data:** One evenly sampled signal, at least about 10 periods of interest `[unsure: rule of thumb]`, with gaps handled. Detrend first.
5. **Shape:** `time series` in; `points` (frequency, power) out; a heatmap for the spectrogram.
6. **Obtain:** PromQL + transform (Welch PSD).
7. **Misuse and guard:** Aliasing and windowing. Mark the Nyquist period (2x sample period) and each null of the `rate()` window: a boxcar of width W removes period W and its harmonics `[checked]`. Warn when the raw signal is unavailable.
8. **Software:** Yes. Finds a 4-minute replica cycle hidden inside daily traffic.
9. **Priority:** **Must-have.** Required by oscillation diagnosis, and catches cron-driven false alarms.
10. **Sources:** [SciPy coherence][scipycoh]; [Thornhill & Horch][thornhill06].

## 5. Poles and zeros

### C1. Root locus
1. **Name and aliases:** Evans plot.
2. **Question and decision:** As one gain rises, how do closed-loop poles move and when does the loop go unstable? Supports choosing a single gain.
3. **Reading:** Branches start at open-loop poles and end at zeros. Moving right means slower or unstable; moving away from the real axis means less damping. In discrete time, the boundary is the unit circle.
4. **Data:** Rational L with one free parameter. Delay needs Padé approximation or a discrete model.
5. **Shape:** `FAMILY` from a `transfer function`.
6. **Obtain:** Model.
7. **Misuse and guard:** Trusting a Padé approximation far from crossover. State the delay approximation and prefer discrete-time form.
8. **Software:** Yes in discrete form. Idealised proportional autoscaler in log replicas, x[k+1] = x[k] - g x[k-d]: critical gain is 2 sin(pi / (2(2d+1))), i.e. 1.0 at d = 1, 0.618 at d = 2, 0.445 at d = 3 `[checked]`. Real HPA adds tolerance, readiness handling and stabilisation, so this is an illustration and not a prediction.
9. **Priority:** **Useful.** Worth having as "gain vs stability" for one parameter; a plain critical-gain readout covers most uses.
10. **Sources:** [Ogata][ogata]; [FPE][fpe]; [python-control][pyctl].

### C2. Pole-zero map
1. **Name and aliases:** s-plane or z-plane plot.
2. **Question and decision:** Is the fitted model stable, oscillatory, slow, or suspiciously over-parameterised? Used to validate models.
3. **Reading:** Poles outside the stable region mean unstable. Complex pairs mean oscillation, with period read from the angle. Near-cancelling pole-zero pairs suggest over-fitting or a hidden slow mode.
4. **Data:** A parametric model, with parameter covariance for uncertainty.
5. **Shape:** `points` derived from a `transfer function`.
6. **Obtain:** Model.
7. **Misuse and guard:** Reading poles of a badly fitted ARX model as physical. Draw uncertainty ellipses and warn on near-cancellations.
8. **Software:** Yes, as a model diagnostic. A fitted queue-autoscaler model with a complex pair near the unit circle predicts its oscillation period.
9. **Priority:** **Useful.** A compact check on every fitted model, mainly for experts.
10. **Sources:** [FBS ch. 9][fbs]; [Ogata][ogata].

## 6. PID tuning

### D1. Reaction curve and FOPDT fit
1. **Name and aliases:** bump test, open-loop step test, process reaction curve.
2. **Question and decision:** What are the process gain, time constant and delay? Provides the inputs to any tuning rule.
3. **Reading:** Delay before movement, slope or 63% point for time constant, final change / input change for gain. Different up and down fits mean nonlinearity.
4. **Data:** Controller held (open loop) or a clean step in OP; steady before; quiet load; record until settled. Repeat both directions.
5. **Shape:** `two signals`; output `transfer function` with parameter uncertainty.
6. **Obtain:** Experiment, or model fit on a naturally occurring OP step when the controller is paused or saturated.
7. **Misuse and guard:** Fitting through a concurrent load change. Show residuals and refuse when pre-step drift is comparable to the response. Experiment needs an abort limit and approval.
8. **Software:** Yes. Hold the autoscaler, add 2 workers, observe queue wait. For an integrating process such as a backlog, fit a slope rather than a gain.
9. **Priority:** **Must-have.** The cheapest credible route to a model of a real loop.
10. **Sources:** [Advanced PID ch. 6][apid6]; [SIMC][simc].

### D2. Ziegler-Nichols tuning
1. **Name and aliases:** ultimate-gain method, ZN step and frequency methods.
2. **Question and decision:** What PID values follow from reaction curve or ultimate gain? Historically the default answer.
3. **Reading:** Table lookup. It targets quarter-amplitude decay, meaning oscillation by design.
4. **Data:** Reaction curve, or the gain at which the loop sustains oscillation.
5. **Shape:** `points` (parameters).
6. **Obtain:** Experiment; model.
7. **Misuse and guard:** Applying it unmodified. On the reference plant: ZN step PI Ms 2.95, ZN ultimate PI 2.43, ZN step PID 4.07, against SIMC PI 1.59 `[checked]`. Driving a production loop to sustained oscillation is unacceptable. **Show ZN only as a labelled historical comparison, never as a recommendation.**
8. **Software:** Does not apply as a procedure. Deliberately oscillating a production service to find its ultimate gain is reckless.
9. **Priority:** **Niche.** Include only so users who ask for it are told why not.
10. **Sources:** Ziegler & Nichols, *Trans. ASME* 64 (1942) 759-768; [Advanced PID ch. 6][apid6]; [Hägglund & Åström][zn-rev].

### D3. Relay autotuning
1. **Name and aliases:** relay feedback test, Åström-Hägglund autotuner.
2. **Question and decision:** Can the critical point be found with a small, bounded oscillation? Used for automatic tuning.
3. **Reading:** Limit-cycle period gives Tu. Ku is about 4h / (pi a). Asymmetric or irregular cycles mean load drift or strong nonlinearity.
4. **Data:** A relay replaces the controller; several stable cycles; quiet load; known amplitude h.
5. **Shape:** `LOOP`; output `points` (Ku, Tu).
6. **Obtain:** Experiment only.
7. **Misuse and guard:** Treating Ku as exact. It is a describing-function approximation: on the reference plant it gave Ku 6.98 against a true 8.50 (-18%), with Tu 7.38 against 7.44 `[checked]`. Use Tu with more confidence than Ku. Gate it, cap amplitude, abort on SLO breach.
8. **Software:** Partly. Toggling a small concurrency limit on a canary is feasible. Long delays, integer actuators and non-stationary load make it weak, and it deliberately perturbs live traffic.
9. **Priority:** **Niche.** Valuable idea, but a reaction-curve test is usually safer for software.
10. **Sources:** [FBS ch. 11][fbs]; [Cambridge excerpt on relay autotuning][relay]; [Åström & Hägglund, A New Auto-Tuning Design][lund-relay].

### D4. Tuning map
1. **Name and aliases:** Kp-Ki stability region, performance-robustness map, Ms-contour map.
2. **Question and decision:** Across the parameters I can change, where is it stable, robust and fast? Chooses a retune and shows its tradeoff.
3. **Reading:** A 2D grid over the two real parameters with the unstable region blocked out, Ms contours, and IAE or churn as colour. Mark current and proposed settings. Good: current point inside the robust region with slack.
4. **Data:** A plant model with uncertainty, and an accurate model of the *actual* controller, including windows and limits.
5. **Shape:** `FAMILY`.
6. **Obtain:** Model (sweep), optionally by simulation.
7. **Misuse and guard:** An optimum on an uncertain model. Evaluate over the model's uncertainty set and recommend the robust point, not the sharpest one. Require a small canary change before adoption.
8. **Software:** Yes, and this is the best tuning UI for software. HPA example: axes of target utilisation and stabilisation window, with SLO miss and pod-minutes as outcomes (simulated, since this controller is not PID).
9. **Priority:** **Must-have.** Turns analysis into a decision using the knobs that exist.
10. **Sources:** [SIMC][simc]; [Advanced PID ch. 6][apid6].

## 7. Structure

### E1. Block diagram
1. **Name and aliases:** feedback diagram, functional diagram, P&ID loop view (ISA-5.1 for process plants).
2. **Question and decision:** What is measured, what decides, what acts, and where are the delays? Decides which loop to analyse and where a fix belongs.
3. **Reading:** Follow the signal around the loop. An odd number of inversions is negative feedback. Check for a missing sensor, hidden delays and nested controllers.
4. **Data:** Declared or inferred structure. No time-series requirement.
5. **Shape:** `GRAPH` (new).
6. **Obtain:** Declared model; inferred edges as labelled hypotheses.
7. **Misuse and guard:** Presenting an inferred arrow as fact. Mark every edge as declared, fitted or hypothesised, with evidence.
8. **Software:** Yes. Queue depth to autoscaler to replicas to service rate to queue depth, with scrape, window and start-up delays on the edges.
9. **Priority:** **Must-have.** It is how a loop gets defined at all.
10. **Sources:** [FBS ch. 1, 9][fbs]; [ISA-5.1][isa51].

### E2. Signal-flow graph
1. **Name and aliases:** Mason graph.
2. **Question and decision:** What is the transfer function between any two points in an interconnected system? Automates algebra.
3. **Reading:** Forward paths and loops. Non-touching loops enter Mason's gain formula.
4. **Data:** A linear graph with edge transfer functions.
5. **Shape:** `GRAPH` to `transfer function`.
6. **Obtain:** Declared or fitted model.
7. **Misuse and guard:** Applying Mason's formula to nonlinear edges. Refuse unless each edge is linear.
8. **Software:** Yes as an internal computation, no as a user-facing chart: it conveys nothing a block diagram does not.
9. **Priority:** **Niche.** Implement the algebra, do not ship the picture.
10. **Sources:** [Mason 1953][mason53]; [Mason 1956][mason56].

### E3. Cascade view
1. **Name and aliases:** inner/outer loop, master/slave loop.
2. **Question and decision:** Do nested loops have enough separation in speed? Decides which loop to retune first.
3. **Reading:** Inner loop should be several times faster than outer (rule of thumb 3-10x `[unsure]`). Tune inner first. If the inner loop saturates, the outer loop needs windup protection.
4. **Data:** PV, OP for both loops, with outer OP = inner SP. Time constants from D1.
5. **Shape:** Linked `LOOP`s plus `GRAPH`.
6. **Obtain:** PromQL; declared structure; model for bandwidth ratio.
7. **Misuse and guard:** Comparing nominal intervals rather than effective response times. Compute separation from measured response.
8. **Software:** Yes, and common. Cluster autoscaler (outer, minutes) supplies nodes for HPA (inner, tens of seconds). A rate limiter inside an autoscaled service is another pair.
9. **Priority:** **Must-have.** Stacked autoscalers and limiters are a leading source of interaction in real systems.
10. **Sources:** [FBS ch. 14][fbs].

### E4. Feedforward view
1. **Name and aliases:** disturbance feedforward, predictive scaling compensation.
2. **Question and decision:** Would acting on a measured disturbance beat waiting for error? Decides whether to add scheduled or predictive actions.
3. **Reading:** Compare error with and without feedforward; plot residual error against the measured disturbance. Remaining correlation means gain or timing is off.
4. **Data:** Measured disturbance leading the output, plus OP and PV. Needs a model of both paths.
5. **Shape:** `two signals`; `transfer function`.
6. **Obtain:** PromQL + transform (lagged regression); model.
7. **Misuse and guard:** Feedforward from a *feedback-affected* signal creates a hidden loop. Check that the signal is exogenous, and warn when it depends on the output.
8. **Software:** Yes. Scale ahead of a known batch release using queued-job count.
9. **Priority:** **Useful.** Often the best improvement available when delay limits feedback.
10. **Sources:** [FBS ch. 12][fbs]; [Advanced PID ch. 5][apid5].

### E5. Relative gain array
1. **Name and aliases:** RGA, Bristol array, interaction matrix.
2. **Question and decision:** With several loops sharing a system, which input should control which output, and will they fight? Decides pairing or decoupling.
3. **Reading:** Pair on values near 1. Avoid negative values. Value 0.5 is worst-case interaction. It is steady-state by default, so a good RGA does not rule out dynamic interaction.
4. **Data:** Steady-state gain matrix, needing a designed test per input or a trusted multivariable model.
5. **Shape:** `dimensions to measures` (matrix).
6. **Obtain:** Model; experiment.
7. **Misuse and guard:** Estimating gains from co-moving production metrics. Refuse without per-input excitation.
8. **Software:** Applies, but the required gain matrix rarely exists. Example: HPA on CPU and a rate limiter on the same service both affecting latency and error rate.
9. **Priority:** **Niche.** For now, a correlated-oscillation view (F7) finds fighting loops with no experiment.
10. **Sources:** [Skogestad & Postlethwaite ch. 3, citing Bristol 1966][rga]; [Skogestad & Postlethwaite][sp].

## 8. Control loop performance assessment

### F1. Harris index
1. **Name and aliases:** minimum-variance index, controller performance index (CPI), Desborough-Harris index.
2. **Question and decision:** How much of this loop's output variance could feedback remove at all? Separates "retune it" from "the delay or disturbance limits you".
3. **Reading:** Harris: eta = sigma_mv^2 / sigma_y^2, near 1 is near minimum variance. **Desborough-Harris normalised form reverses this:** 0 is best, 1 is worst. Always print the convention. A low Harris eta indicates potential, not a guaranteed gain: minimum variance control is aggressive and often undesirable.
4. **Data:** Routine closed-loop error, constant SP or a variable-SP extension, stationary, known delay. Typically 500-2000 samples with an AR order of about 10-30 `[unsure: common practice, not checked against the primary paper]`.
5. **Shape:** `time series` in; `points` plus `distribution` (bootstrap) out.
6. **Obtain:** PromQL + transform (AR fit, impulse coefficients over delay).
7. **Misuse and guard:** Wrong delay. With identical data, assumed delays of 1, 2, 3 give **0.546, 0.814, 0.951** `[checked]`. Refuse without a delay; show a range over the delay's uncertainty. Exclude saturation, setpoint moves and mode changes.
8. **Software:** Partly. Delay is often measurable from a registry and traces, but saturation, batching and regime changes violate assumptions. Example: queue-wait variance with a 45 s pod-start delay.
9. **Priority:** **Useful.** A good fleet triage signal, but dangerous as a headline score.
10. **Sources:** [Harris & Seppala, CPC6 review][harris]; Harris, *Can. J. Chem. Eng.* 67 (1989) 856-861.

### F2. OP-PV and OP-MV plots
1. **Name and aliases:** valve signature, stiction loop, phase plot, butterfly plot.
2. **Question and decision:** Is the actuator doing what it was told, or does it have deadband or stiction? Decides between fixing the actuator and retuning.
3. **Reading:** **OP-MV** is the direct test: a straight line is healthy; a parallelogram indicates backlash or deadband; flat segments followed by jumps indicate stiction. **OP-PV** is far more ambiguous because process dynamics and disturbances distort it. Cross-correlation of OP and PV is odd under stiction and even without it, for non-integrating loops (Horch).
4. **Data:** High-rate OP and MV, or OP and PV, during movement. Oscillating or excited loop.
5. **Shape:** `two signals`, drawn as `points` with time order.
6. **Obtain:** PromQL (range query on both, joined by timestamp).
7. **Misuse and guard:** Diagnosing stiction from an OP-PV ellipse. Linear dynamics alone also produce ellipses. Require MV for a verdict and show "ambiguous" otherwise. Detection is relatively mature but quantification methods can disagree strongly ([Jelali & Huang][jelali], via citing work).
8. **Software:** Physical stiction **does not apply**. The analogue does: tolerance bands, integer replicas and cooldowns create deadband and stick-jump behaviour. Software's advantage is that MV is usually observed: desired vs current replicas gives OP-MV directly.
9. **Priority:** **Must-have** (OP-MV form). Rules out the actuator fast, and software has the data the process industry often lacks.
10. **Sources:** [Choudhury, Shah & Thornhill][choudhury]; [Zheng et al., stiction detection][stiction]; [ISA-75.25.01][isa7525].

### F3. Oscillation detection
1. **Name and aliases:** Hägglund IAE detector, ACF zero-crossing regularity, oscillation index.
2. **Question and decision:** Is this loop oscillating, at what period, and how regularly? The primary triage alarm.
3. **Reading:** Show the period, regularity and amplitude with the ACF. Regular cycles indicate a loop cause. Near-sinusoidal suggests tuning or external forcing; square, triangular or harmonic-rich suggests a nonlinearity.
4. **Data:** Control error with zero mean, at least about 10 periods, sampled at 8 or more points per period `[unsure: rule of thumb]`. Hägglund's method assumes integral action.
5. **Shape:** `time series` in; `points` (period, regularity, amplitude) out.
6. **Obtain:** PromQL + transform (ACF zero crossings; Hägglund IAE between zero crossings).
7. **Misuse and guard:** Calling cron or daily seasonality a control oscillation. Compare to known schedules and check whether OP participates. Warn if the `rate()` window could hide or alias the period.
8. **Software:** Yes, and this is the headline detector. Example: replicas cycle 12-20 every 7 minutes, in phase with queue depth.
9. **Priority:** **Must-have.** High-signal, model-free and runnable across the whole fleet.
10. **Sources:** [Thornhill & Hägglund][th97]; [Hägglund/Lund record][osc-lund]; [Thornhill & Horch][thornhill06].

### F4. Saturation and windup view
1. **Name and aliases:** time at limit, clamp view, integrator windup trace.
2. **Question and decision:** Has the loop run out of authority, and does it recover late after leaving the limit? Decides between capacity change and anti-windup.
3. **Reading:** Shade time at limit on the loop trend. Windup signature: PV has returned, yet OP stays at the limit, then PV overshoots. ABB's index, for example, counts OP outside 3-97% of range.
4. **Data:** OP, limits, PV, and ideally the *unclamped* demand. Sampling fast enough to see limit entry.
5. **Shape:** `LOOP`; `dimensions to measures` for time at limit.
6. **Obtain:** Plain PromQL (`avg_over_time` over a `>= bool` subquery).
7. **Misuse and guard:** Retuning a saturated loop, which cannot help. **Suppress tuning recommendations while saturated**, and exclude those segments from linear estimators. HPA's desired replicas are clamped, so compute unclamped demand from current replicas and the metric ratio.
8. **Software:** Yes, everywhere: max replicas, rate-limit caps, connection pools, budgets. A backlog accumulated behind a clamp behaves like integrator windup.
9. **Priority:** **Must-have.** The commonest reason a software loop fails, and the easiest chart to compute.
10. **Sources:** [FBS ch. 11][fbs]; [Anti-windup review][aw]; [ABB CLAM][abb]; [HPA docs][hpa].

### F5. Idle index
1. **Name and aliases:** sluggishness index.
2. **Question and decision:** Is the loop too slow? Detects over-conservative tuning, which variance alarms miss.
3. **Reading:** Range [-1, 1]. Near +1 is sluggish. Negative tends to be well tuned, but near -1 can also mean oscillation, so read with F3.
4. **Data:** OP and PV increments around load disturbances, filtered for noise.
5. **Shape:** `two signals` in; `points` out.
6. **Obtain:** PromQL + transform (sign correlation of increments).
7. **Misuse and guard:** Frequent random disturbances can push it negative. Calculate only on segments with clear load events.
8. **Software:** Probably, but unproven `[unsure: I found no software application]`. Example: autoscaler creeping up slowly during every traffic rise.
9. **Priority:** **Useful.** Cheap counterpart to F3; validate on real loops before exposing it.
10. **Sources:** [Hägglund 1999][idle]; [Ooi & Weyer][idle2].

### F6. Fleet loop scorecard
1. **Name and aliases:** loop health report, CLPM dashboard, bad-actor Pareto.
2. **Question and decision:** Of all loops, which deserve attention now? Allocates engineering time.
3. **Reading:** One row per loop: time in auto, time at limit, oscillation, error, churn, data quality. Sort by business impact. Individual flags are better than a blended score.
4. **Data:** The registry and per-loop metrics on a fixed window.
5. **Shape:** `dimensions to measures`.
6. **Obtain:** PromQL + transforms, cached batch; SQL for mode and changes.
7. **Misuse and guard:** A single composite health number hides failure modes and invites gaming. Show components and the reason, and mark "not assessable" separately from healthy.
8. **Software:** Yes. All HPAs ranked by SLO impact, with flags for pinned at max, oscillating or high churn.
9. **Priority:** **Must-have.** It is what industrial CLPM products are, and it scales attention.
10. **Sources:** [GE loop monitoring][gekpi]; [ABB CLAM][abb]; [Emerson Ovation agent][emerson]; [POWER overview][power].

### F7. Plant-wide oscillation map
1. **Name and aliases:** spectral cluster map, high-density plot, spectral PCA.
2. **Question and decision:** Which loops share one oscillation, and where did it start? Stops teams retuning victims of a common cause.
3. **Reading:** Rows are signals, columns frequency, cells power. Vertical bands show a shared oscillation. The likely root has the strongest nonlinearity signature, not necessarily the largest amplitude.
4. **Data:** Many signals on one clock, weeks not required but several periods needed, consistent windows.
5. **Shape:** New matrix: `dimensions to measures` with frequency as a dimension.
6. **Obtain:** PromQL + transform (batch PSD and clustering).
7. **Misuse and guard:** A shared frequency is not causation; a shared schedule produces it too. Label clusters as "co-oscillating" and offer root-cause candidates with evidence.
8. **Software:** Yes. A GC cycle, cron or retry wave appearing across services.
9. **Priority:** **Useful.** Highly distinctive once there are many loops; premature before that.
10. **Sources:** [Thornhill & Horch][thornhill06]; [Thornhill et al. 2002][thornhill02].

## 9. Charts not named in the brief

### G1. Cross-correlogram and lag estimate
1. **Name and aliases:** CCF, delay estimation plot.
2. **Question and decision:** How long after A moves does B move? Supplies the delay for margins and Harris.
3. **Reading:** Peak lag estimates delay, peak height strength; a broad peak means distributed response. Peaks at both signs imply feedback.
4. **Data:** Two aligned stationary signals, prewhitened, with enough events. Open-loop or externally excited for causal delay.
5. **Shape:** `two signals` in; `points` (lag, correlation) out.
6. **Obtain:** PromQL + transform. PromQL has no correlation function; `offset` alone cannot produce a correlogram efficiently.
7. **Misuse and guard:** Shared seasonality gives spurious peaks. Prewhiten, show a significance band, and call it lead-lag rather than causation.
8. **Software:** Yes. Queue depth to replica change, or deploy to latency.
9. **Priority:** **Must-have.** Delay is the parameter that limits nearly every software loop.
10. **Sources:** [Horch method via Thornhill & Horch][thornhill06]; [Forssell & Ljung][fl99].

### G2. Static operating curve and gain schedule
1. **Name and aliases:** load curve, installed characteristic, universal scalability curve (related), gain map.
2. **Question and decision:** How does output depend on input at steady state, and how does loop gain change across the range? Decides capacity limits and whether one tuning is valid.
3. **Reading:** Slope is local process gain. Knees mark saturation. Separate up and down branches indicate hysteresis. Gain varying more than about 2x across the range means one fixed tuning is suspect `[unsure: rule of thumb]`.
4. **Data:** Quasi-steady points spanning the load range, binned, with n per bin. Closed-loop data is usable only for the steady relation, with care.
5. **Shape:** `points`; `distribution` per bin.
6. **Obtain:** PromQL + transform (settled-segment filter, binning); optionally a load test.
7. **Misuse and guard:** Fitting across transients or letting the controller's action create the relationship. Filter by settled state and colour by time so hysteresis stays visible.
8. **Software:** Yes, more than any classical plot. Latency against utilisation has gain rising 25x from 50% to 90% in M/M/1 `[checked]`.
9. **Priority:** **Must-have.** It is the check on whether any linear chart is valid.
10. **Sources:** [FBS ch. 6][fbs]; [Bronson et al.][metastable].

### G3. Phase portrait and return map
1. **Name and aliases:** state-space plot, cobweb diagram, metastability map.
2. **Question and decision:** Does the system return to its good state after a shock, or settle into a bad one? Decides whether load shedding or retry changes are needed rather than retuning.
3. **Reading:** Plot x against its rate, or x[k+1] against x[k]. A spiral inward is stable; a closed orbit is a limit cycle; two attractors mean metastability.
4. **Data:** State-like signals (backlog, error rate, retries) across incidents. Multiple trajectories, not one.
5. **Shape:** `points` with time order.
6. **Obtain:** PromQL + transform; SQL for item-level backlog; model for the vector field.
7. **Misuse and guard:** Inferring an attractor from a single incident. Require repeated trajectories, otherwise label it "observed path".
8. **Software:** Yes, and classical linear charts cannot show this. With failure fraction f and up to n attempts, offered load multiplies by (1 - f^n)/(1 - f), or **2.71x at f = 0.9, n = 3** `[checked]`, sustaining overload after the trigger ends ([metastable failures][metastable]).
9. **Priority:** **Must-have.** Retry storms are among the costliest software feedback failures, and no LTI chart represents them.
10. **Sources:** [Bronson et al.][metastable]; [Huang et al.][metastable2]; [FBS ch. 5][fbs].

### G4. Describing function overlay
1. **Name and aliases:** harmonic balance plot.
2. **Question and decision:** Will a nonlinearity plus this linear loop produce a limit cycle, and at what amplitude? Used to predict cycling.
3. **Reading:** Intersection of L(iw) with -1/N(a) predicts a limit cycle.
4. **Data:** Linear model plus characterised nonlinearity. Assumes the linear part filters harmonics.
5. **Shape:** `FAMILY` plus `transfer function`.
6. **Obtain:** Model.
7. **Misuse and guard:** The filtering assumption often fails with pure delay and square-like signals. Label the result approximate; confirm in simulation.
8. **Software:** Limited. Simulation of the real discrete controller is generally simpler and more accurate.
9. **Priority:** **Niche.** Prefer simulation.
10. **Sources:** [Cambridge excerpt][relay]; [FBS ch. 11][fbs].

### G5. Measurement and delay budget
1. **Name and aliases:** loop latency budget, phase-lag budget. A composite I am proposing, not a named classical chart.
2. **Question and decision:** Where does this loop's delay come from, and which part can I remove? Decides whether to shorten a window, scrape faster or speed start-up instead of retuning.
3. **Reading:** A stacked bar around the loop: scrape, `rate()` window (about W/2), metric pipeline, controller period, actuation, start-up, process. Compare the total with the delay margin.
4. **Data:** Configuration and measured latencies; a declared loop structure.
5. **Shape:** `dimensions to measures`, attached to `GRAPH` edges.
6. **Obtain:** Declared config plus PromQL; G1 to validate.
7. **Misuse and guard:** Counting a dashboard's window as loop delay. Only windows the **controller consumes** are in the loop. Mark which is which.
8. **Software:** Yes. On the reference loop, window W = 0, 1, 2, 4, 8 gives GM 3.14, 2.56, 2.19, 1.74, 1.27 and Ms 1.59, 1.81, 2.07, 2.76, 6.10 `[checked]`. For HPA, 15 s sync, metric lag and pod readiness all stack.
9. **Priority:** **Must-have.** Delay is usually the cheapest thing to fix, and software exposes each piece.
10. **Sources:** [Prometheus functions][promfn]; [HPA docs][hpa]; [FBS ch. 10][fbs].

### G6. Actuator staircase test
1. **Name and aliases:** deadband and resolution test, step-ladder test.
2. **Question and decision:** What is the smallest command the actuator honours, and how fast? Sets the limit on control precision.
3. **Reading:** Send small up and down steps. Missing moves reveal deadband and resolution; ISA-75.25 reports step response time at 86.5% of final value.
4. **Data:** OP and MV at high rate; controlled test; quiet process.
5. **Shape:** `two signals`.
6. **Obtain:** Experiment; declared limits often suffice in software.
7. **Misuse and guard:** Testing at one point when deadband depends on the range. Note that HPA's effective deadband scales with replica count: at 10 replicas a 10% tolerance is about one pod; at 100 it is about ten.
8. **Software:** Yes, though often computable without a test, because tolerance, step policy and integer rounding are documented.
9. **Priority:** **Useful.** Prefer computing it from config, and test only when behaviour disagrees.
10. **Sources:** [ISA-75.25.01][isa7525]; [HPA docs][hpa].

## 10. Synthesis

### Ranked top 15

| Rank | Chart | Entry | Why here |
|---:|---|---|---|
| 1 | Loop trend | A1 | Foundation for every diagnosis |
| 2 | Saturation and windup view | F4 | Commonest failure, cheapest to compute, blocks bad advice |
| 3 | Oscillation detection (with PSD) | F3 + B9 | Model-free, fleet-wide, high signal |
| 4 | Static operating curve | G2 | Tells you whether linear charts are valid at all |
| 5 | Fleet loop scorecard | F6 | Directs attention across many loops |
| 6 | Disturbance response | A5 | What operational loops actually do |
| 7 | Measurement and delay budget | G5 | Finds the cheapest fix |
| 8 | Cross-correlogram and lag | G1 | Supplies delay for everything else |
| 9 | Block diagram | E1 | Defines the loop |
| 10 | OP-MV plot | F2 | Separates actuator faults from tuning |
| 11 | Phase portrait and return map | G3 | The only view of retry storms and metastability |
| 12 | Reaction curve and FOPDT | D1 | Cheapest credible model |
| 13 | Tuning map | D4 | Turns analysis into a decision |
| 14 | Sensitivity S and T | B4 | Shows where a retune moves the pain |
| 15 | Margin against operating point | B7 | Safety at the coming peak |

Next in line: step response (A2), tracking error (A6) and control effort (A7) are must-haves but are cheap views of A1 and F6, so they ship with them rather than rank separately. Cascade view (E3) is a must-have as soon as nested loops are modelled.

**Deliberately excluded from the top 15:** Bode (useful, but behind a model), Nyquist, Nichols, root locus, Ziegler-Nichols. This is the most disputable call here. A control engineer will expect Bode on day one, so it should exist as an expert view, but putting it in front of operators without a validated model would produce confident nonsense.

### Analytical workflows

1. **Is this loop healthy?** F6 scorecard → A1 loop trend → F4 saturated? → F3 oscillating? → A6 error against objective → A7 churn. Outcome: healthy, capacity problem, dynamics problem, or **not assessable**.
2. **Why is it oscillating?** F3 period → B9 harmonics and known schedules → F7 shared with other loops? → F2 OP-MV for actuator deadband → G1 and G5 for delay → D4 or a model to test gain too high. Outcome: external forcing, actuator nonlinearity, excess gain or delay.
3. **How should I retune it?** F4 confirm not saturated → G2 choose operating range → D1 fit model (gated) → G5 include real delays → D4 choose robust point → B4 and B5 review → simulated A2 and A5 → canary → compare observed A5 with prediction. Outcome: an evidence-backed change, or a finding that tuning cannot help.
4. **Why can't it hold target?** A6 persistent bias → F4 time at limit → G2 knee → E3 is an outer loop starving it? Outcome: raise capacity, fix a limit, or change the objective.
5. **Will it survive the coming peak?** G2 gain at forecast load → B7 margin at that load → G5 delay → simulated A4 ramp. Outcome: safe, pre-scale, or retune for peak.
6. **Is this incident self-sustaining?** A5 no recovery after trigger removal → G3 trajectories → retry amplification from item events → G2 hysteresis. Outcome: shed load or cut retries. Retuning would be the wrong response.
7. **Which loop started it?** F7 cluster → G1 lead-lag → F2 and F3 nonlinearity in candidates → E1 structural path. Outcome: ranked root-cause hypotheses, never a certainty.

### Shared infrastructure

In order of leverage:

1. **Loop registry.** Declares SP, PV, OP, MV, limits, mode, controller type, update period and known windows. Almost every chart depends on it. Inferred bindings must be labelled as hypotheses.
2. **`LOOP` query and alignment layer.** Resamples onto one clock, records gaps, and preserves raw samples where retained.
3. **Window and delay ledger.** Tracks every `rate()`, recording-rule and controller window, distinguishing display windows from in-loop windows.
4. **Segmenter.** Splits data by mode, saturation, setpoint change, deployment, incident, settled or transient. Most estimators are only valid on some segments.
5. **Data-quality gate with typed refusals.** Reasons such as `too_short`, `aliased`, `saturated`, `no_excitation`, `closed_loop_unidentifiable`, `delay_unknown`, `nonstationary`. "Cannot say" must be a first-class result.
6. **Transform service.** Prometheus has no FFT or correlation, so this must exist outside PromQL: detrend, ACF/CCF, Welch PSD and coherence, AR/ARX, FOPDT fit, bootstrap intervals.
7. **Model store with provenance.** Declared, fitted and experimental models, each with operating point, fit data, uncertainty and validity range.
8. **LTI and simulation engine.** Margins, S/T, sweeps, and discrete simulation of the *real* controller, including clamps, rounding and tolerance. Simulation should be preferred wherever linear analysis is doubtful. [python-control][pyctl] covers the LTI side, and API names vary across versions.
9. **Experiment harness.** Gated actions with amplitude cap, abort condition, rollback, canary scope and a recorded result.
10. **Verdict object.** Every computed result carries value, confidence, assumptions, data window and refusal reason.
11. **Rendering primitives.** Log-frequency axes, dB and phase unwrapping, complex plane with critical point, contour grid, time-ordered scatter, frequency heatmap.

## 11. Checks run, and what remains unverified

**Computed for this report** (NumPy, on the reference plant unless stated):

| Check | Result |
|---|---|
| SIMC PI (Kc 2.5, Ti 10) | GM 3.14, PM 61.4 degrees, Ms 1.59 |
| ZN step PI | GM 1.66, PM 31.2, Ms 2.95 |
| ZN ultimate PI | GM 1.92, PM 36.2, Ms 2.43 |
| ZN step PID (derivative filter N = 10) | GM 1.33, PM 39.3, Ms 4.07 |
| In-loop boxcar window W = 0, 1, 2, 4, 8 (SIMC held) | Ms 1.59, 1.81, 2.07, 2.76, 6.10 |
| Relay test | Ku 6.98 vs exact 8.50; Tu 7.38 vs 7.44 |
| Closed-loop static regression, true gain 1, C = 3 | -0.333 with no excitation; 0.249 with setpoint excitation |
| Harris estimator on known MA(3), delay 2 | 0.818 vs true 0.814 |
| Harris with assumed delay 1, 2, 3 (exact) | 0.546, 0.814, 0.951 |
| x[k+1] = x[k] - g x[k-d], critical g | 2.0, 1.0, 0.618, 0.445, 0.347, 0.285 for d = 0..5 |
| Ms to margin bounds | Ms 1.2/1.4/1.7/2.0 give GM >= 6/3.5/2.43/2 and PM >= 49.2/41.8/34.2/29.0 |
| Boxcar of 60 s on a 60 s sine | Output amplitude 0 |

These are illustrations on one simple plant. They show direction and scale, and do not establish general rankings of tuning rules.

**Not verified against the primary text:**

- Paywalled originals were not read: Harris 1989, Ziegler & Nichols 1942, Horch 1999, Forssell & Ljung 1999, Jelali & Huang, and the ISA standards. Claims about them rest on citing papers, abstracts or previews.
- Ogata and FPE are cited as standard references from publisher pages. I did not check chapter-level details.
- Three links returned 403 to my automated check but appeared in search results, so they are unconfirmed as clickable: the Choudhury paper, Thornhill et al. 2002 and the ABB manual page.
- FBS chapter references are to the public 2016 preprint and may differ from the 2021 print edition.
- Harris sample length and AR order, sampling ratios, cascade separation and the 2x gain-variation threshold are rules of thumb.
- I found no published evidence that the idle index, Harris index or stiction methods have been validated on software loops. Their transfer to software is my inference.
- The HPA recurrence is idealised. Real HPA behaviour includes tolerance, stabilisation and conservative handling of unready pods ([docs][hpa]).

## References

[fbs]: https://www.cds.caltech.edu/~murray/books/AM08/pdf/fbs-public_15Oct16.pdf "Åström & Murray, Feedback Systems, public preprint"
[apid5]: https://skoge.folk.ntnu.no/puublications_others/books/%C3%85strom-2006_Advanced%20PID%20Control/5.FeedForward%20Design.pdf "Åström & Hägglund, Advanced PID Control, ch. 5"
[apid6]: https://skoge.folk.ntnu.no/puublications_others/books/%C3%85strom-2006_Advanced%20PID%20Control/6.PID%20Design.pdf "Åström & Hägglund, Advanced PID Control, ch. 6"
[sp]: https://skoge.folk.ntnu.no/book/ "Skogestad & Postlethwaite, Multivariable Feedback Control"
[ogata]: https://www.pearson.com/en-us/pearsonplus/p/9780137551064 "Ogata, Modern Control Engineering, 5th ed."
[fpe]: https://www.pearson.com/en-us/subject-catalog/p/feedback-control-of-dynamic-systems/P200000003343 "Franklin, Powell & Emami-Naeini, 8th ed."
[simc]: https://skoge.folk.ntnu.no/publications/2003/tuningPID/ "Skogestad, Simple analytic rules for model reduction and PID controller tuning (2003)"
[zn-rev]: https://lup.lub.lu.se/record/161428 "Åström & Hägglund, Revisiting the Ziegler-Nichols step response method"
[relay]: https://assets.cambridge.org/97811070/58712/excerpt/9781107058712_excerpt.pdf "Cambridge excerpt on relay autotuning"
[lund-relay]: https://lup.lub.lu.se/search/ws/files/48381659/TFRT_7398.pdf "Åström & Hägglund, A New Auto-Tuning Design (1988)"
[disk]: https://arxiv.org/abs/2003.04771 "Seiler, Packard & Gahinet, An Introduction to Disk Margins"
[stein]: https://ethw.org/Archives:Respect_the_Unstable "Stein, Respect the Unstable"
[fl99]: https://doi.org/10.1016/S0005-1098(99)00022-9 "Forssell & Ljung, Closed-loop identification revisited"
[harris]: https://skoge.folk.ntnu.no/prost/proceedings/cpc6-jan2002/harris.pdf "Harris & Seppala, Recent Developments in Controller Performance Monitoring and Assessment Techniques"
[choudhury]: https://www.ualberta.ca/~slshah/files/Diagnosis_Loop_performance2004.pdf "Choudhury, Shah & Thornhill, Diagnosis of poor control-loop performance"
[stiction]: https://sites.ualberta.ca/~bhuang/paper/Seshu%20Stiction%20Detection.pdf "Zheng et al., Valve stiction detection and quantification using k-means clustering"
[jelali]: https://sites.ualberta.ca/~bhuang/Stiction-Book.htm "Jelali & Huang, Detection and Diagnosis of Stiction in Control Loops"
[th97]: https://spiral.imperial.ac.uk/entities/publication/a8bb2d1a-cb77-4077-82d4-79d83e279dd1 "Thornhill & Hägglund, Detection and diagnosis of oscillation in control loops"
[osc-lund]: https://lup.lub.lu.se/record/537677 "Implementation of an on-line detection procedure for oscillating control loops"
[thornhill06]: https://folk.ntnu.no/skoge/prost/proceedings/adchem06/PDF_Files/K1_ADCHEM06_7.pdf "Thornhill & Horch, Advances in plant-wide disturbance detection and diagnosis"
[thornhill02]: https://discovery-pp.ucl.ac.uk/id/eprint/497/1/ThornhillEtAl_IFAC_2002.pdf "Thornhill et al., IFAC 2002"
[idle]: https://doi.org/10.1016/S0967-0661(99)00116-1 "Hägglund, Automatic detection of sluggish control loops"
[idle2]: https://skoge.folk.ntnu.no/prost/proceedings/ifac2005/Fullpapers/02129.pdf "Ooi & Weyer, Detection of sluggish control loops in irrigation channels, IFAC 2005"
[aw]: https://arxiv.org/abs/2606.01959 "Anti-Windup in PID Control: Review, Analysis, and New Tuning Directions"
[mason53]: https://dspace.mit.edu/handle/1721.1/4902 "Mason, Feedback theory: some properties of signal flow graphs"
[mason56]: https://doi.org/10.1109/jrproc.1956.275147 "Mason, Feedback theory: further properties of signal flow graphs"
[rga]: https://skoge.folk.ntnu.no/vgprosessregulering/papers-pensum/ch3-ch10-2ndedition.pdf "Skogestad & Postlethwaite, chapters 3 and 10 (RGA)"
[isa51]: https://isa.org/standards-and-publications/isa-standards/list-of-all-isa-standards "ISA standards list, including ANSI/ISA-5.1-2024"
[isa7525]: https://www.isa.org/products/ansi-isa-75-25-01-2024-test-procedure-for-control "ANSI/ISA-75.25.01-2024"
[gekpi]: https://www.gevernova.com/software/documentation/csense/version2023/Action%20Object%20Services/Understanding_Process_plus_KPIs.htm "GE Process+ KPIs"
[abb]: https://www.manualslib.com/manual/1215369/Abb-800xa.html?page=111 "ABB 800xA Control Loop Asset Monitor"
[emerson]: https://www.emerson.com/is/content/emerson/en/systems-and-software/ovation-distributed-control-systems/documents/PWS_011279-Ovation-AI-Loop-Performance-Monitor-Agent.pdf "Emerson Ovation Loop Performance Monitor Agent"
[power]: https://www.powermag.com/monitoring-control-loop-performance/ "POWER, Monitoring control loop performance"
[hpa]: https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/ "Kubernetes Horizontal Pod Autoscaling"
[ksm]: https://github.com/kubernetes/kube-state-metrics/blob/main/docs/metrics/workload/horizontalpodautoscaler-metrics.md "kube-state-metrics HPA metrics"
[promfn]: https://prometheus.io/docs/prometheus/latest/querying/functions/ "Prometheus query functions"
[scipycoh]: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.coherence.html "SciPy coherence"
[pyctl]: https://python-control.readthedocs.io/en/latest/functions.html "python-control function reference"
[hollot]: https://dna-pubs.cs.columbia.edu/publication/465 "Hollot et al., A Control Theoretic Analysis of RED"
[metastable]: https://pure.psu.edu/en/publications/metastable-failures-in-distributed-systems/ "Bronson et al., Metastable Failures in Distributed Systems"
[metastable2]: https://www.usenix.org/conference/osdi22/presentation/huang-lexiang "Huang et al., Metastable Failures in the Wild"
