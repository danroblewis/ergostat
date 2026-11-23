# Charts for modern control, identification, nonlinear dynamics and control performance monitoring

Research for ergostat, 2026-11-23. Classical control (Bode, Nyquist, root locus, PID tuning) is excluded because another agent covers it.

## Read this first

**Verdict.** 55 charts assessed: 15 must-have, 25 useful, 15 niche. The must-haves are mostly queueing, constraint, change and validation views. The famous modern-control charts (Hankel, singular values, Lyapunov, recurrence) are mostly useful or niche here, because they need a trustworthy model that ordinary telemetry rarely supports.

Five facts should shape the product:

1. **Production telemetry is usually closed-loop and unexcited.** Regressing output on input then recovers the *controller*, not the plant. In simulation, with true gains 0.5, 2 and 5 under a unit-gain controller, the naive estimate was -1.0 every time. Adding an external dither recovered the true parameters (a=0.499, b=1.997 against 0.5, 2).
2. **Autocorrelation breaks naive statistics.** An individuals chart on AR(1) data (phi = 0.9) with limits from the moving range flagged **34%** of in-control points, against 0.26% for independent data. Two *independent* AR(1) series (phi = 0.9) passed the usual lag-0 correlation significance test **52%** of the time (83% at phi = 0.99).
3. **The query can erase the phenomenon.** A 60 s oscillation has amplitude **0.0** after a 60 s or 120 s rectangular window (3.18 of a true 5 at 30 s). `rate(x[1m])` can therefore hide exactly the autoscaler oscillation being investigated. A scrape interval T also cannot represent periods below 2T.
4. **PromQL has no FFT, autocorrelation or cross-correlation function** ([functions reference][prom-fn]). Nearly every chart here needs a transform service outside PromQL.
5. **A flat controlled variable proves little.** A working autoscaler holds CPU near target while the disturbance moves into the replica count. Chart the actuator as well as the output, or SPC will report "in control" while the system absorbs a growing load.

Figures in points 1 to 3 and others marked *(simulated)* come from small numeric checks run for this report. They illustrate the mechanism and are not measurements of a real system.

## Legend

**Result shapes.** Existing: `TS` time series; `DM` dimensions to measures; `PTS` points; `DIST` distribution; `IO` two signals (input and output); `TF` transfer function from a model.

**New shapes needed** (four, used repeatedly):

| Shape | Contents | Why existing shapes fail |
|---|---|---|
| `CURVE±` | x, estimate, lower, upper, method, n_effective | ACF, spectra and impulse estimates are meaningless without their band |
| `GRID` | Labelled x and y axes, one or more values per cell | RGA, spectrograms, heatmaps, recurrence, vector fields |
| `TRAJ` | Time-ordered points in 2 or 3 states, with time retained | `PTS` loses order, and order is the whole content of a phase portrait |
| `SS` | A, B, C, D, sample time, state names, operating point, validity envelope | `TF` cannot represent states, and hides cancelled modes |

**How to obtain.** `P` plain PromQL; `P+T` PromQL plus a named transform; `SQL` over item events; `M` fitted or declared model; `X` active experiment.

**Priority.** **Must-have**, **useful** or **niche**. `[UNSURE]` marks a judgement or claim I could not firmly establish.

---

## A. State-space and structure

### 1. Eigenvalue and modal map (pole map, mode table, participation factors)
- **Question:** Which modes dominate, how fast do they decay, and which state does each live in? Decides whether a loop is slow, oscillatory or near instability.
- **Read:** Discrete time: inside the unit circle is stable, near 1 is slow, negative real is sample-to-sample ringing. Show time constant and damping as a table; few operators read the z-plane.
- **Data:** Fitted linear model around one operating point. Validity is local.
- **Shape / source:** `SS` to `PTS` + `DM` · `M`
- **Misuse → guard:** Reading fitted poles as physics. Show parameter uncertainty; refuse "stable" when the interval crosses the boundary. Flag negative real poles as possible sampling artefacts.
- **Ops:** Queue plus autoscaler: a pair with period about 8 minutes names the suspected oscillation.
- **Priority:** Useful. The compact summary of any fitted loop, but only as good as the fit.
- **Sources:** [Skogestad & Postlethwaite][skog]; [Hellerstein et al.][hell]

### 2. Controllability and observability (rank test, PBH test, Gramian ellipsoids)
- **Question:** Can this actuator move this state? Can these metrics reveal it? Decides whether to add an actuator or an instrument.
- **Read:** Rank deficiency is a binary failure. Small Gramian eigenvalues mean "technically possible, practically not". Show per-state bars.
- **Data:** `SS` model; Gramians need stability. Scaling changes Gramians, not rank.
- **Shape / source:** `SS` to `DM` · `M`
- **Misuse → guard:** Numerical rank on a poorly scaled model; treating a structural claim from a guessed model as fact. Require declared units and scaling; report the margin.
- **Ops:** A backlog behind a shared rate limiter: adding workers does not control it while the limiter is active.
- **Priority:** Useful. Asked as plain questions, these catch "this knob cannot fix that", without showing the mathematics.
- **Sources:** [Skogestad & Postlethwaite][skog]; [Moore 1981][moore]

### 3. Hankel singular values (HSV plot, balanced-state energy)
- **Question:** How many states does the input-output behaviour need? Decides model reduction order.
- **Read:** A sharp drop gives the order. For stable systems, the H-infinity truncation error is at most twice the sum of discarded values.
- **Data:** Stable LTI model (unstable part split off); well-scaled inputs and outputs.
- **Shape / source:** `SS` to `DM` · `M`
- **Misuse → guard:** Applying to unstable or poorly fitted models. Refuse for unstable parts. Note that balanced states are not physical stocks, so never relabel them as such.
- **Ops:** Weak. Could reduce a large fitted worker-pool model. `[UNSURE]` whether ergostat models will be large enough to need it.
- **Priority:** Niche. Software loop models are usually small, and balanced states destroy the named stocks users care about.
- **Sources:** [Moore 1981][moore]; [MATLAB hsvd][m-hsvd] (now marked not recommended in favour of `balred`)

### 4. Structural influence graph (structural controllability, driver nodes)
- **Question:** From the wiring alone, which nodes can drive the rest?
- **Read:** Unreachable or dilated parts indicate missing actuation.
- **Data:** Directed graph only. Assumes free, generic parameters.
- **Shape / source:** `GRID` or graph · `M`
- **Misuse → guard:** Network "driver node" counts depend strongly on assumed node dynamics ([Cowan et al. 2012][cowan] against [Liu et al. 2011][liu]). Show reachability only; do not publish a driver-node score.
- **Ops:** Reachability on a service dependency graph is useful; the formal theory adds little.
- **Priority:** Niche. Plain graph reachability delivers most of the value.
- **Sources:** [Lin 1974][lin]; [Liu et al.][liu]; [Cowan et al.][cowan]

---

## B. Multivariable views

### 5. Singular value plot (sigma plot, MIMO gain envelope)
- **Question:** What are the largest and smallest gains across all input directions at each frequency?
- **Read:** A large gap means strong directionality and ill-conditioning. Peaks in sensitivity indicate poor robustness.
- **Data:** MIMO `TF` or `SS`. Requires scaled signals.
- **Shape / source:** `TF` to `CURVE±` · `M`
- **Misuse → guard:** Singular values and condition number change with units. Refuse unless inputs and outputs have declared scales.
- **Ops:** Replicas and concurrency limit both acting on latency and error rate.
- **Priority:** Niche. Few ergostat users will have a validated MIMO frequency model.
- **Sources:** [Skogestad & Postlethwaite][skog]; [MATLAB sigma][m-sigma]

### 6. Relative gain array (RGA, Bristol array)
- **Question:** Which actuator should control which output, and will two loops fight? Decides pairing or decoupling.
- **Read:** Diagonal near 1 is good. Negative steady-state elements warn against that pairing. Large elements mean sensitivity to model error: the classic distillation example has lambda11 = 35.07, singular values 197.2 and 1.39, condition number 141.7 *(recomputed)*.
- **Data:** Steady-state gain matrix, preferably also at the crossover frequency. Needs each input moved independently.
- **Shape / source:** `GRID` · `M` or `X`
- **Misuse → guard:** Gains from closed-loop passive data are unreliable. Show gain provenance. RGA is scale-independent, so it does not show absolute importance. Never present it as a stability proof.
- **Ops:** HPA on CPU and a concurrency limiter both responding to latency: RGA reveals the pairing conflict.
- **Priority:** Useful. The most practical MIMO chart, and a 2x2 needs only four step tests.
- **Sources:** [Bristol 1966][bristol]; [Skogestad & Postlethwaite][skog]

### 7. Step-response matrix (interaction map)
- **Question:** When input j moves, what happens to each output, how far and how late?
- **Read:** Strong diagonal with small off-diagonals is decoupled. Off-diagonal delays reveal the propagation path.
- **Data:** Separate perturbation of each input, or a fitted MIMO FIR model. Open loop is best.
- **Shape / source:** Small multiples of `CURVE±` · `X` or `M`
- **Misuse → guard:** Filling cells from correlation. Mark each cell as experimental, fitted or unknown; leave unknown cells blank.
- **Ops:** Worker count against queue depth, downstream latency and database connections.
- **Priority:** Useful. Far easier to read than a transfer-function matrix.
- **Sources:** [Skogestad & Postlethwaite][skog]; [Ljung 2010][ljung]

### 8. Directionality plot (SVD input and output directions)
- **Question:** Which combination of actuators is strong or weak?
- **Read:** Loadings for the strongest and weakest directions. A weak direction needs large actuator moves.
- **Data:** Scaled gain matrix, usually at steady state.
- **Shape / source:** `DM` · `M`
- **Misuse → guard:** Scale-dependent, and the sign of a singular vector is arbitrary. Fix a sign convention and require scales.
- **Ops:** Rarely actionable: scaling two pools together versus trading capacity between them.
- **Priority:** Niche. Worth having only after RGA proves insufficient.
- **Sources:** [Skogestad & Postlethwaite][skog]

---

## C. System identification diagnostics

### 9. Excitation and identifiability card (data adequacy)
- **Question:** Can this record support a model at all? This gates every chart in this section.
- **Read:** Reports loop status (open, closed, unknown), input variance, input spectrum coverage, external excitation events, saturation fraction, gaps, effective sample size, and stationarity. Verdict: identifiable, weak or not identifiable.
- **Data:** Input, output and any setpoint or dither; actuator limits; scrape interval; annotations.
- **Shape / source:** `DM` + `CURVE±` · `P+T`
- **Misuse → guard:** This is the guard. **Refuse** a plant estimate from closed-loop data with no external excitation, unless a valid closed-loop method and a known signal exist.
- **Ops:** An HPA at constant replicas for a week has zero input excitation, so no replicas-to-latency gain can be learned.
- **Priority:** **Must-have.** It prevents the most damaging failure: a confident model of the controller, labelled as the plant.
- **Sources:** [Forssell & Ljung 1999][forssell]; [Ljung 2010][ljung]

### 10. Residual correlation (whiteness test; residual ACF plus input-residual CCF)
- **Question:** Has the model captured everything predictable? Decides accept, or which part to revise.
- **Read:** ACF inside the band: noise model adequate. Input-to-residual correlation at lags where input *leads*: missed dynamics. Under feedback, residuals leading the input are expected and are not a defect.
- **Data:** Validation residuals, input, usually at least several hundred samples. Linear test; stationary residuals.
- **Shape / source:** `CURVE±` · `M` + `P+T`
- **Misuse → guard:** Checking only training data; reading passes across many lags without correction. Default to held-out data; report a [Ljung-Box][ljungbox] statistic with adjusted degrees of freedom. A pass does not prove the model right.
- **Ops:** A daily residual ACF peak in a queue model means the arrival seasonality is unmodelled.
- **Priority:** **Must-have.** The standard, inexpensive test of whether to believe a fitted loop.
- **Sources:** [MATLAB resid][m-resid]; [residual analysis][m-resan]; [Ljung 2010][ljung]

### 11. Model versus held-out data (compare plot, simulation fit)
- **Question:** Does the model reproduce data it never saw?
- **Read:** Fit = 100(1 - ‖y-ŷ‖/‖y-mean(y)‖). 100 is perfect, 0 is no better than the mean, and it can be negative. Inspect transients, not only the score.
- **Data:** A separate validation segment from a *different* regime or period, with the same input.
- **Shape / source:** `IO` + `TS` · `M`
- **Misuse → guard:** One-step-ahead fit flatters any slow system, since "same as last value" scores highly. Default to free-run simulation; always show a naive persistence baseline. Warn when validation lies outside the training range.
- **Ops:** Fit queue depth on Monday to Thursday and simulate Friday's spike.
- **Priority:** **Must-have.** The one model-quality view a non-specialist can judge.
- **Sources:** [MATLAB compare][m-compare]; [Ljung 2010][ljung]

### 12. Model order selection curve (loss vs order, AIC, cross-validation)
- **Question:** How complex should the model be?
- **Read:** Choose the elbow on *validation* loss. Training loss always falls.
- **Data:** Candidate models on the same data, plus a validation split that respects time.
- **Shape / source:** `PTS` · `M`
- **Misuse → guard:** Random cross-validation folds leak future data. Enforce blocked splits; prefer the smaller model within noise.
- **Ops:** Choosing first or second order for a queue-plus-autoscaler model.
- **Priority:** Useful. Should usually run automatically and be shown only on request.
- **Sources:** [Ljung 2010][ljung]; [Pillonetto et al. 2014][pillonetto]

### 13. Prewhitened cross-correlation (lag plot, CCF)
- **Question:** Does X lead Y, by how much? Supplies a delay hypothesis.
- **Read:** A clear peak outside the band at a positive lag. Broad humps mean shared trend or autocorrelation.
- **Data:** Two regular series, with the input-whitening filter applied to both. Record much longer than the lag.
- **Shape / source:** `IO` to `CURVE±` · `P+T`
- **Misuse → guard:** Raw CCF on trending series is the most common false finding in operations (52% false positives at phi = 0.9, *simulated*). Prewhiten by default; never label a peak "cause". Correct for the number of pairs searched.
- **Ops:** Estimating pod-start delay between a scale event and capacity.
- **Priority:** Useful. Cheap, but a valid lag estimate is better obtained from #16.
- **Sources:** [Ljung 2010][ljung]; [Kantz & Schreiber][kantz]

### 14. Coherence (magnitude-squared coherence)
- **Question:** At which frequencies is Y linearly related to X? Decides where a frequency-response estimate can be trusted.
- **Read:** Near 1: linear relation with little noise. Low: noise, nonlinearity or unrelated signals. Trust only values above the significance floor.
- **Data:** Two stationary signals, many averaged segments.
- **Shape / source:** `IO` to `CURVE±` · `P+T`
- **Misuse → guard:** One segment gives coherence **exactly 1** ([MATLAB][m-coh]). Independent noise averaged about 0.26, 0.059 and 0.015 with 4, 16 and 64 segments *(simulated)*, close to 1/segments. Refuse below a minimum number of segments and draw the floor. Under pure feedback, high coherence reflects the controller.
- **Ops:** Does retry traffic track error rate at the 2-minute band?
- **Priority:** Useful. Valuable alongside an experiment, misleading on passive closed-loop data.
- **Sources:** [Carter et al. 1973][carter]; [Bendat & Piersol][bendat]; [MATLAB mscohere][m-coh]

### 15. Power spectrum and spectrogram (PSD, periodogram, STFT, waterfall)
- **Question:** Is there a periodic component, at what period, and when did it start? Finds oscillations and separates daily seasonality from control behaviour.
- **Read:** Narrow peak: periodic. A band that appears after a deploy implicates that deploy. Broad hump: resonance or narrowband noise.
- **Data:** Regular samples at raw resolution, detrended. Resolution is about 1/window; several cycles per window are required.
- **Shape / source:** `CURVE±` (PSD), `GRID` (spectrogram) · `P+T`
- **Misuse → guard:** Aliasing and pre-filtering by `rate[w]`, which can null a real oscillation (*simulated* above). Shade frequencies the scrape and window cannot show. State the observable period band on the chart.
- **Ops:** A 6-minute band in replicas and queue depth, starting at an HPA configuration change.
- **Priority:** **Must-have.** Oscillation is the signature failure of feedback systems, and time plots hide it.
- **Sources:** [MATLAB spectrogram][m-spec]; [Bendat & Piersol][bendat]

### 16. Impulse and step response estimate (FIR estimate, correlation analysis)
- **Question:** If I change this input, how much does the output move, how late, and for how long? Gives gain, delay and settling time.
- **Read:** Delay is the first lag outside the band; gain is the final step value; overshoot and undershoot appear directly.
- **Data:** Excited input with known timing, record several times the settling time. Regularised estimation helps on short records. Linear around one point.
- **Shape / source:** `IO` to `CURVE±` · `M`, ideally `X`
- **Misuse → guard:** Estimating from closed-loop data without excitation, or across regimes. Gate on #9; always draw the band.
- **Ops:** Add 2 workers and measure the queue-drain response, giving the delay needed to tune the autoscaler.
- **Priority:** **Must-have.** The most directly useful model artefact, readable without control theory.
- **Sources:** [MATLAB impulseest][m-imp]; [Pillonetto et al. 2014][pillonetto]; [Hellerstein et al.][hell]

### 17. Excitation design view (PRBS, chirp, multisine, step-test planner)
- **Question:** What test signal identifies this loop within safety limits and time?
- **Read:** Shows planned signal, spectrum against the frequency band of interest, amplitude limits, and expected duration. A PRBS has period up to 2^n - 1 and falls to half power near 0.44/T_clock.
- **Data:** Time-constant estimate, actuator limits, allowed output deviation, and sample period.
- **Shape / source:** `TS` + `CURVE±` · `X`
- **Misuse → guard:** Clock period shorter than the actuator can follow; chirps confounded by a transient disturbance. Require abort thresholds, approval and a rollback. Refuse without declared limits.
- **Ops:** A small PRBS on a rate limit in canary, within the error budget.
- **Priority:** Useful. This is the route to real plant models, but only after the guardrails exist.
- **Sources:** [MATLAB idinput][m-idinput] (PRBS, RBS, Gaussian, sine; no chirp); [Schroeder 1970][schroeder]

---

## D. Nonlinear dynamics

### 18. Measured phase portrait (phase plane, state trajectory)
- **Question:** How do two states evolve together? Reveals loops, overshoot, regimes and recovery paths that time plots hide.
- **Read:** Inward spiral: damped. Closed orbit: sustained oscillation. Two dense clusters: two regimes. Different outbound and return paths: hysteresis.
- **Data:** Two aligned state-like signals (for example replicas and queue depth) at matching resolution. No stationarity needed, because it is descriptive.
- **Shape / source:** `TRAJ` · `P+T` (alignment)
- **Misuse → guard:** A scatter without time order is not a phase portrait. Encode time; thin carefully. A 2D projection can show false crossings, so do not infer "chaos" or a limit cycle from the picture alone.
- **Ops:** Replicas vs queue depth: a repeating loop exposes autoscaler hunting immediately.
- **Priority:** **Must-have.** The highest insight-per-pixel view for feedback, needing only two ordinary series.
- **Sources:** [Strogatz][strogatz]; [Khalil][khalil]

### 19. Vector field with nullclines (direction field, flow field)
- **Question:** From any state, where does the system go, and where are its equilibria?
- **Read:** Nullcline crossings are equilibria. Arrows show stability and basins.
- **Data:** A two-state model, or dense measured data across states. Model-based unless coverage is excellent.
- **Shape / source:** `GRID` (two values per cell) · `M`
- **Misuse → guard:** Drawing arrows where no data exists. Mask or fade cells outside the fitted envelope.
- **Ops:** Queue depth vs retry rate: a second stable equilibrium at high backlog is the shape of a metastable failure `[UNSURE: an interpretation, needs model support per system]`.
- **Priority:** Useful. Excellent for explaining a declared two-stock model; rarely trustworthy from data alone.
- **Sources:** [Strogatz][strogatz]

### 20. Bifurcation diagram (equilibria vs parameter, hysteresis curve)
- **Question:** At what parameter value does behaviour qualitatively change? Decides safe limits.
- **Read:** Solid stable branches, dashed unstable. A fold (saddle-node) means sudden jump and hysteresis. Hopf: oscillation begins.
- **Data:** A validated nonlinear model, or a slow, controlled parameter sweep in both directions.
- **Shape / source:** `PTS` by branch · `M` or `X`
- **Misuse → guard:** One-direction sweeps miss hysteresis. Require up and down sweeps. Label model-derived branches as such.
- **Ops:** Sweep retry budget or arrival rate in a simulator to find where recovery fails.
- **Priority:** Useful. Valuable on declared models and load tests, not on passive production data.
- **Sources:** [Strogatz][strogatz]; [Bronson et al. 2021][bronson]

### 21. Poincaré section and return map (first-return map)
- **Question:** Is a repeating cycle stable, period-doubled or irregular?
- **Read:** One fixed point on the diagonal: periodic. Slope magnitude below 1: stable. Several points: higher period. A scattered cloud: noise.
- **Data:** Many cycles of a sustained oscillation, sampled well within each period.
- **Shape / source:** `PTS` · `P+T`
- **Misuse → guard:** Few cycles or arbitrary section placement. Require about 30 or more crossings.
- **Ops:** Peak-to-peak map of replica oscillations. A simple "this peak vs next peak" plot delivers most of the value.
- **Priority:** Niche. Software rarely gives enough clean cycles before someone intervenes.
- **Sources:** [Strogatz][strogatz]

### 22. Limit-cycle versus noise classifier (envelope and amplitude-distribution view)
- **Question:** Is this oscillation a self-sustained cycle, a forced periodicity, or filtered noise? Each has a different fix.
- **Read:** A limit cycle has steady amplitude. Narrowband noise has a wandering envelope. *Simulated* envelope CV: 0.10 for sine plus noise against 0.54 for a resonant AR(2); kurtosis -1.44 against 0.11. Cross-check for an external driver at the same period.
- **Data:** At least about 10 cycles, raw resolution, detrended; actuator and candidate driver series.
- **Shape / source:** `TS` + `DIST` + `CURVE±` · `P+T`
- **Misuse → guard:** Calling any spectral peak a limit cycle. Output three-way verdict with evidence, and "inconclusive" when cycles are few. A forced periodic signal also has steady amplitude, so the test **cannot** separate those without the driver check.
- **Ops:** An HPA flapping from delay plus tolerance band, versus a cron job driving load.
- **Priority:** **Must-have.** It answers a question operators actually ask, and the remedies are opposite.
- **Sources:** [Thornhill & Horch 2007][thornhill]; [Choudhury et al. 2004][choudhury]; [Strogatz][strogatz]

### 23. Describing function plot (harmonic balance, relay analysis)
- **Question:** Will this nonlinearity plus this linear loop sustain a limit cycle, at what amplitude and frequency?
- **Read:** Intersection of G(jw) with -1/N(A) predicts a cycle; crossing direction indicates stability.
- **Data:** Linear model, plus a known static nonlinearity (deadband, saturation, quantiser).
- **Shape / source:** `TF` + `CURVE±` · `M`
- **Misuse → guard:** An approximation that assumes the linear part filters harmonics. It can predict false cycles or miss real ones. Label as predicted and confirm by simulation.
- **Ops:** HPA has a declared structure: `ceil` quantisation, 10% tolerance, 15 s sync ([docs][hpa]). Whether the low-pass assumption holds is `[UNSURE]` and system-specific.
- **Priority:** Niche. Direct simulation of the declared loop is simpler and more accurate for software.
- **Sources:** [Khalil][khalil]; [Åström & Hägglund 1984][astrom-relay]

### 24. Lyapunov function and region of attraction (level sets, ROA)
- **Question:** From which states is recovery guaranteed?
- **Read:** V decreases along trajectories inside a level set. Largest such set estimates the ROA.
- **Data:** Explicit nonlinear model and candidate V.
- **Shape / source:** `GRID` · `M`
- **Misuse → guard:** The condition is sufficient only: failure to find V does not imply instability, and the estimate is usually conservative. A guarantee from a wrong model is worthless, so say "under this model".
- **Ops:** A declared queue-retry model could give a safe backlog limit. An empirical recovery map (#52) is usually more honest.
- **Priority:** Niche. Requires a model accuracy software systems seldom have.
- **Sources:** [Khalil][khalil]

### 25. Lyapunov exponent divergence curve (largest Lyapunov exponent)
- **Question:** Do nearby trajectories diverge exponentially (chaos)?
- **Read:** A linear region in log divergence vs time; its slope is the exponent.
- **Data:** Long, stationary, low-noise, deterministic series with good embedding.
- **Shape / source:** `CURVE±` · `P+T`
- **Misuse → guard:** Algorithms return a number for noise as well. Refuse without surrogate testing (#28) and a visible scaling region.
- **Ops:** Effectively no. Telemetry is noisy, nonstationary and externally driven. I would not ship it.
- **Priority:** Niche. "Is it chaotic?" changes no operational decision.
- **Sources:** [Rosenstein et al. 1993][rosenstein]; [Kantz & Schreiber][kantz]

### 26. Recurrence plot (RP, recurrence quantification analysis)
- **Question:** When does the system return to earlier states, and when does its regime change?
- **Read:** Diagonals: deterministic repetition. Blocks: laminar regimes. White bands: transitions.
- **Data:** Regular series; embedding and threshold choices.
- **Shape / source:** `GRID` · `P+T`
- **Misuse → guard:** Results depend on embedding and threshold, and over-embedding creates spurious diagonals ([Marwan 2011][marwan-pit]). Require sensitivity display and a surrogate baseline. O(n²) cost needs a downsampling limit.
- **Ops:** Spotting recurring incident-like regimes across weeks, though changepoints and seasonal comparison are simpler.
- **Priority:** Niche. Striking pictures, few decisions.
- **Sources:** [Eckmann et al. 1987][eckmann]; [Marwan et al. 2007][marwan]

### 27. Delay embedding (Takens reconstruction, lag plot)
- **Question:** Can a state portrait be reconstructed from one observed signal?
- **Read:** Structured geometry suggests low-dimensional dynamics. A shapeless cloud suggests noise. Choose delay by mutual information and dimension by false nearest neighbours.
- **Data:** Long, stationary series. Theorem assumes smooth deterministic dynamics.
- **Shape / source:** `TRAJ` · `P+T`
- **Misuse → guard:** Coloured noise can produce convincing shapes. Show a surrogate beside it; never call the axes real states.
- **Ops:** A simple lag plot helps when only queue depth exists. Full embedding rarely earns its complexity.
- **Priority:** Niche. Keep the simple lag plot as an option of #18.
- **Sources:** [Takens 1981][takens]; [Fraser & Swinney 1986][fraser]; [Kennel et al. 1992][kennel]

### 28. Surrogate data test (null-distribution plot)
- **Question:** Is the apparent nonlinearity or structure more than linear coloured noise could produce?
- **Read:** Observed statistic against the surrogate distribution; outside it rejects the linear-Gaussian null.
- **Data:** Stationary series; many surrogates.
- **Shape / source:** `DIST` · `P+T`
- **Misuse → guard:** Nonstationarity also rejects the null, so rejection does not by itself prove nonlinearity. Test stationarity first and state the exact null.
- **Ops:** Supporting check behind #22 and #26, and rarely a visible chart.
- **Priority:** Useful. Valuable as infrastructure that keeps the nonlinear charts honest.
- **Sources:** [Theiler et al. 1992][theiler]; [Kantz & Schreiber][kantz]

### 29. Input-output hysteresis loop (pv-op plot, stiction pattern)
- **Question:** Does the output follow the input differently on the way up and down? Reveals deadband, stabilisation windows and backlash.
- **Read:** A thin line: static. An ellipse: linear lag. A parallelogram or stepped shape: deadband or stiction-like behaviour.
- **Data:** Controller output and process variable; enough reversals.
- **Shape / source:** `IO` to `TRAJ` · `P+T`
- **Misuse → guard:** A lag alone creates a loop. Compare against the loop expected from the fitted delay. Stiction diagnosis can be fooled by an external sinusoidal disturbance.
- **Ops:** Desired vs actual replicas: the 300 s downscale stabilisation window ([HPA][hpa]) appears as a deliberate asymmetry.
- **Priority:** Useful. Cheap, and directly exposes actuator limitations.
- **Sources:** [Choudhury et al. 2004][choudhury]; [Thornhill & Horch 2007][thornhill]

### 30. Early-warning indicators (critical slowing down: rolling variance and lag-1 autocorrelation)
- **Question:** Is the system losing resilience before a transition?
- **Read:** Rising variance and autocorrelation *may* precede a fold.
- **Data:** Long, regular, detrended series with a slowly changing driver.
- **Shape / source:** `TS` + `CURVE±` · `P+T`
- **Misuse → guard:** False alarms are serious: reported false-alarm fractions at 90% detection ranged from 0% to 93% ([Boettiger & Hastings][boettiger-limits]), and selecting on past failures biases results ([prosecutor's fallacy][boettiger-pf]). **Do not alert on this.** Show as research only, with ROC evidence from the same system.
- **Ops:** Plausible before queue collapse; unproven in production software `[UNSURE]`.
- **Priority:** Niche. Attractive, but the evidence does not support acting on it.
- **Sources:** [Scheffer et al. 2009][scheffer]; [Boettiger & Hastings][boettiger-limits]

---

## E. Scheduling, prediction, estimation and adaptation

### 31. Gain schedule and operating-point map (local gain vs load)
- **Question:** How do gain and delay change with load? Decides whether one tuning is enough.
- **Read:** Flat: one controller is enough. Steep curve: schedule by load or linearise. Mark current position and sparse regions.
- **Data:** Local step responses or fitted gains binned by scheduling variable. Scheduling variable should vary slowly relative to the loop.
- **Shape / source:** `DM` or `GRID` with bands · `M` or `X`
- **Misuse → guard:** Interpolating into empty bins, or scheduling on a fast signal, which can destabilise a loop that is stable at each frozen point. Grey out unsupported regions.
- **Ops:** Latency sensitivity to replicas is tiny at 30% utilisation and huge near saturation.
- **Priority:** Useful. Queueing makes gain strongly load-dependent, so this is the right follow-on to #48.
- **Sources:** [Rugh & Shamma 2000][rugh]; [Hellerstein et al.][hell]

### 32. MPC horizon view (receding-horizon plot, prediction funnel)
- **Question:** What does the controller predict and plan, and which constraint shapes the plan?
- **Read:** Past, predicted output, planned moves and limits. Repeated divergence of realised from predicted output indicates model error.
- **Data:** Logged plan at each decision, constraints, state estimate. Needs an actual predictive controller.
- **Shape / source:** `TS` (versioned by decision time) · `M`
- **Misuse → guard:** Showing only the latest plan hides revision. Keep prediction vintages; show prediction error by lead time.
- **Ops:** Predictive autoscaling that plans capacity ahead of a forecast peak.
- **Priority:** Useful. Generalises to any forecast-driven controller, and the vintage store is needed for judging predictions anyway.
- **Sources:** [Rawlings, Mayne & Diehl][rawlings]

### 33. Constraint and saturation timeline (actuator-at-limit, windup view)
- **Question:** When was the controller unable to act, and which limit stopped it? Decides whether to tune or add capacity.
- **Read:** Bands where desired exceeds actual, or actuator is at min or max. Error growing during saturation, then overshoot after, indicates windup.
- **Data:** Desired and actual actuator values, declared limits, and limiter or throttle events.
- **Shape / source:** `TS` + `DM` (percentage at limit) · `P`, `SQL`
- **Misuse → guard:** Treating an unobserved limit as absent. Show "limit undeclared". Tuning advice must be suppressed while saturated, because the loop is effectively open.
- **Ops:** `kube_horizontalpodautoscaler_status_desired_replicas` against spec max; a rate limiter at its cap; a worker pool at full concurrency.
- **Priority:** **Must-have.** Saturation is the commonest reason a software loop fails, and the data is cheap.
- **Sources:** [Rawlings, Mayne & Diehl][rawlings]; [Hellerstein et al.][hell]; [HPA docs][hpa]

### 34. Kalman innovations (innovation sequence, NIS)
- **Question:** Is the state estimator consistent with reality?
- **Read:** Innovations should be zero-mean and white. Normalised innovation squared follows chi-square with degrees of freedom equal to measurement dimension. Too high: overconfident. Too low: noise overestimated.
- **Data:** Innovations and covariance from a running estimator.
- **Shape / source:** `TS` + `CURVE±` · `M`
- **Misuse → guard:** Outlier gating distorts the chi-square reference. Report the gating rate. Consistency is not correctness of the model structure.
- **Ops:** An estimator of true backlog from delayed metrics; only applies if ergostat runs one.
- **Priority:** Useful. Becomes essential the moment any estimator is deployed.
- **Sources:** [Kalman 1960][kalman]; [Mehra 1970][mehra]

### 35. Adaptive parameter trace (recursive estimate, forgetting-factor plot)
- **Question:** Are the estimated parameters converging, drifting or bursting?
- **Read:** Settling with a narrowing band is good. Drift during quiet periods signals lost excitation. Sudden bursts warn of instability.
- **Data:** Time-stamped parameters, covariance and an excitation measure.
- **Shape / source:** `TS` with bands · `M`
- **Misuse → guard:** Adaptation with poor excitation can drift, and unmodelled dynamics can destabilise it ([Rohrs et al.][rohrs]). Freeze adaptation when excitation is low, and show when it did.
- **Ops:** An autotuned concurrency limit whose latency baseline drifts during low traffic.
- **Priority:** Useful. Required before ergostat ever allows self-tuning.
- **Sources:** [Rohrs et al.][rohrs]; [Ljung 2010][ljung]

---

## F. Control performance monitoring and SPC

### 36. Minimum-variance benchmark (Harris index, CPI)
- **Question:** How much output variance could better feedback remove, given the delay?
- **Read:** Index from 0 to 1, with 1 equal to minimum-variance performance. Low means potential improvement, not a known cause.
- **Data:** Routine closed-loop error, a known delay, stationary periods without setpoint moves.
- **Shape / source:** `DM` + `TS` · `P+T` with declared delay
- **Misuse → guard:** Highly sensitive to delay. The benchmark may be unattainable or non-robust, and the index does not diagnose causes. Require a declared delay and show index across a delay range.
- **Ops:** Variance of queue delay about target under a worker autoscaler; less meaningful where holding a metric tight is not the goal.
- **Priority:** Useful. The rare benchmark obtainable passively, valuable for ranking many loops.
- **Sources:** [Harris 1989][harris]; [Desborough & Harris 1992][desborough]

### 37. Plant-wide oscillation map (spectral clustering, power spectral map)
- **Question:** Which signals share one oscillation, and so probably one source?
- **Read:** Rows are signals, columns are frequency. Vertical stripes indicate a shared disturbance.
- **Data:** Many regular series, common sampling, several cycles.
- **Shape / source:** `GRID` · `P+T`
- **Misuse → guard:** Sharing a frequency does not identify the source, and diurnal cycles dominate. Remove seasonality; label clusters as "common oscillation", not "root cause".
- **Ops:** One 7-minute cycle across HPA, queue, database connections and latency.
- **Priority:** Useful. Turns many alerts into one disturbance, a direct process-industry lesson for operations.
- **Sources:** [Thornhill & Horch 2007][thornhill]

### 38. Shewhart chart (individuals, X-bar and R, 3-sigma chart)
- **Question:** Has an unusual, large shift occurred?
- **Read:** Points beyond limits; 0.27% false-alarm rate if independent and normal.
- **Data:** Stable baseline, independent observations, rational subgroups.
- **Shape / source:** `TS` with limits · `P+T`
- **Misuse → guard:** Raw telemetry is usually autocorrelated and skewed (34% out of limits at phi = 0.9, *simulated*). Check autocorrelation and **refuse raw limits** above a threshold; chart residuals (#41).
- **Ops:** Weekly deployment failure proportion, which is closer to independent than per-second metrics.
- **Priority:** Niche. Useful as a form, but #41 is the version that survives telemetry.
- **Sources:** [NIST Shewhart][nist-shew]; Montgomery, *Introduction to Statistical Quality Control* (Wiley, no stable open link)

### 39. CUSUM (tabular cumulative sum, decision-interval chart)
- **Question:** Has the mean shifted slightly and persistently, and when?
- **Read:** Upper or lower sum crossing h; restart point estimates onset. With k = 0.5 sigma, in-control average run length is about 170 at h = 4 and 470 to 490 at h = 5 *(simulated)*.
- **Data:** Baseline mean and sigma; independent residuals.
- **Shape / source:** `TS` · `P+T` (stateful)
- **Misuse → guard:** Autocorrelation shortens run lengths. Apply to residuals and state expected false-alarm interval in time, not sigma.
- **Ops:** A 3% latency regression after a deployment, invisible on a 3-sigma chart.
- **Priority:** Useful. Best small-shift detector; delivered through #41.
- **Sources:** [Page 1954][page]; [NIST CUSUM][nist-cusum]

### 40. EWMA chart
- **Question:** Is there a small or gradual drift?
- **Read:** EWMA_t = λY_t + (1-λ)EWMA_(t-1), with limits ±k·s·√(λ/(2-λ)). NIST cites λ of 0.2 to 0.3 as usual.
- **Data:** Baseline; independent data assumed for the limits. Fairly robust to non-normality.
- **Shape / source:** `TS` · `P+T` (or experimental PromQL smoothing)
- **Misuse → guard:** A smoothed line alone is not a control chart. Show limits and effective memory. Autocorrelation still invalidates default limits.
- **Ops:** Slow memory-driven increase in per-request latency.
- **Priority:** Useful. Simple to explain and cheap to compute; delivered through #41.
- **Sources:** [Roberts 1959][roberts]; [Lucas & Saccucci 1990][lucas]; [NIST EWMA][nist-ewma]

### 41. Model-residual control chart (special-cause chart with CUSUM or EWMA)
- **Question:** Has the system departed from its *expected dynamics*, after seasonality, load and control action?
- **Read:** Residual within limits means behaving as predicted. Sustained excursion means a real change or a model failure. Chart the actuator as well.
- **Data:** A one-step or seasonal forecast, residual series, baseline period. Residuals approximately uncorrelated.
- **Shape / source:** `TS` · `P+T` or `M`
- **Misuse → guard:** Residual charts inherit model error, and can inflate false alarms ([review][sas-auto]). Check residual whiteness on baseline; display achieved false-alarm rate; retrain only with explicit approval so a fault is not absorbed.
- **Ops:** Latency given request rate and replicas: a drift shows even while the autoscaler hides it in CPU.
- **Priority:** **Must-have.** This is the valid form of SPC for autocorrelated, controlled telemetry.
- **Sources:** [Alwan & Roberts 1988][alwan]; [SAS on autocorrelation strategies][sas-auto]; [Hellerstein et al.][hell]

---

## G. Fault detection, isolation and change

### 42. Fault signature matrix (structured residuals, parity relations)
- **Question:** Which fault best explains the pattern of failed residuals?
- **Read:** Rows are residuals, columns are faults. Match observed pattern. Identical columns are not distinguishable.
- **Data:** Multiple model-based residuals and a declared fault model.
- **Shape / source:** `GRID` · `M`
- **Misuse → guard:** Treating an unlisted fault as the nearest listed one. Always include "unknown", and report which faults cannot be isolated.
- **Ops:** Separating slow database, lost workers and traffic surge in a pipeline model.
- **Priority:** Useful. The isolability check tells you which instrument to add.
- **Sources:** [Chow & Willsky 1984][chow]; [Isermann 2006][isermann]

### 43. T² and SPE monitoring with contribution plot (Hotelling, Q statistic)
- **Question:** Has the correlation structure across many metrics changed, and which metrics contribute?
- **Read:** T² high: unusual within the model plane. SPE high: correlation broken. Contributions suggest candidates only.
- **Data:** Many aligned metrics, stable training window, approximate stationarity.
- **Shape / source:** `TS` + `DM` · `P+T`
- **Misuse → guard:** Contribution **smearing** can highlight healthy variables and obscure faulty ones ([van den Kerkhof et al.][smear]). Label "contributors", never "root cause". Retrain policy must be explicit.
- **Ops:** Pod-level metric sets where the relationship between CPU and throughput breaks.
- **Priority:** Niche. Poor fit with churning label sets, and its output is easily over-read.
- **Sources:** [Qin 2003][qin]; [Venkatasubramanian et al. 2003][venkat]

### 44. Causal map (Granger, transfer entropy, delay-based propagation graph)
- **Question:** In which direction did a disturbance probably propagate?
- **Read:** Directed edges with lag and strength; candidate source has outgoing edges.
- **Data:** Many stationary series with sufficient lag resolution; no strong unmeasured common driver.
- **Shape / source:** Graph or `GRID` · `P+T`
- **Misuse → guard:** Predictive precedence is not causation, feedback loops produce edges both ways, and methods can name contradictory roots. Show as hypotheses, with the service topology as a prior, and correct for multiple tests.
- **Ops:** Whether database latency led API latency in an incident.
- **Priority:** Useful. Good for generating hypotheses, dangerous when presented as an answer.
- **Sources:** [Granger 1969][granger]; [Schreiber 2000][schreiber]; [Thornhill & Horch 2007][thornhill]

### 45. Changepoint view (PELT, Bayesian online changepoint, run-length plot)
- **Question:** Did level, variance or dynamics change, and when?
- **Read:** Change marks with uncertainty. A BOCPD run-length plot shows sudden collapse at a change.
- **Data:** Regular series; explicit cost model and penalty. Best on residuals.
- **Shape / source:** `TS` + annotations · `P+T`
- **Misuse → guard:** Penalties determine the count of changes, and autocorrelation causes spurious ones. Run on residuals; show sensitivity to the penalty.
- **Ops:** Dating when queue service rate fell, then matching to deployments.
- **Priority:** Useful. The automation behind #46 and #41.
- **Sources:** [Killick et al.][pelt]; [Adams & MacKay 2007][bocpd]

### 46. Event-aligned response (superposed epoch analysis, before/after panel)
- **Question:** What typically happens around a class of events? Did this deployment or scale-up change the output?
- **Read:** Overlay traces aligned at t=0 with median and band. A shift after zero that exceeds the pre-event spread is evidence of an effect.
- **Data:** Event timestamps, series around each. More events allow stronger claims. Needs matching controls for causal language.
- **Shape / source:** `TS` with relative time, or `CURVE±` · `P` + `SQL`
- **Misuse → guard:** Events chosen *because* the metric moved (reactive scale-ups) create false effects and regression to the mean. Distinguish scheduled from triggered events; show n; test against random placebo times.
- **Ops:** Median queue response to all scale-out events, showing actual pod-ready delay.
- **Priority:** **Must-have.** It gives real dynamics from natural experiments with no active test.
- **Sources:** [Haurwitz & Brier 1981][haurwitz]

### 47. Counterfactual impact plot (interrupted time series, synthetic control)
- **Question:** What would have happened without the change, and what is the estimated effect?
- **Read:** Observed vs predicted counterfactual, pointwise and cumulative effect with credible intervals.
- **Data:** Pre-period, and control series *unaffected by the intervention*.
- **Shape / source:** `TS` with bands · `M`
- **Misuse → guard:** Contaminated controls bias the result, and shared services often are contaminated. Require declared controls, a pre-period fit check and a placebo test.
- **Ops:** Effect of a retry-budget change on error rate, using an unaffected region as control.
- **Priority:** Useful. The strongest passive answer to "did this help?", where valid controls exist.
- **Sources:** [Brodersen et al. 2015][causalimpact]

---

## H. Queueing and software-specific control

### 48. Utilization-latency curve (hockey stick, load-response curve, knee plot)
- **Question:** How close are we to the knee, and how much headroom remains? Decides capacity and autoscaler target.
- **Read:** Flat, then steep. For M/M/1, R/S = 1/(1-ρ): 2 at 50%, 5 at 80%, 10 at 90%, 20 at 95%, 100 at 99%. Plot p50 and p99 with the current point. More servers move the knee right. Higher variability raises the curve ([Kingman][kingman]).
- **Data:** Utilisation of the true bottleneck, latency distribution, wide load range, short windows, stable workload mix.
- **Shape / source:** `PTS` with fit · `P+T`, better with `X`
- **Misuse → guard:** CPU may not be the bottleneck; averaged utilisation hides bursts; closed-loop load generators understate latency ([coordinated omission][wrk2]). Mark sparse load ranges and refuse extrapolation past observed load.
- **Ops:** Choose HPA target from where p99 turns up.
- **Priority:** **Must-have.** The most decision-relevant single chart for software capacity.
- **Sources:** [Kingman 1961][kingman]; [Hellerstein et al.][hell]; [Dean & Barroso 2013][tail]

### 49. Universal Scalability Law fit (USL, throughput vs concurrency)
- **Question:** Where does adding concurrency stop helping or start hurting? Is the limit contention or coherency?
- **Read:** X(N) = γN / (1 + α(N-1) + βN(N-1)). α is contention, β coherency. N_max = √((1-α)/β). β > 0 means retrograde throughput.
- **Data:** At least six steady-state (N, X) points, ideally controlled load, one workload mix, spanning the curve.
- **Shape / source:** `PTS` + `M` · `P+T` or `X`
- **Misuse → guard:** Fits to narrow ranges are unstable; extrapolated N_max is often fiction. Show parameter intervals and observed range. Gunther describes production mixed-workload use as an active research area, so warn on that.
- **Ops:** Choosing a worker pool's maximum concurrency.
- **Priority:** Useful. Excellent from a load test, unreliable on passive production data.
- **Sources:** [Gunther, USL][usl]; [*Guerrilla Capacity Planning*][gcap]

### 50. Little's law consistency plot (L vs λW)
- **Question:** Do the queue, throughput and latency metrics agree? If not, instrumentation is wrong or work is escaping.
- **Read:** Points on y = x. Persistent gap: missing work, retries counted differently, timeouts, or a wrong boundary.
- **Data:** Same system boundary for in-flight L, completion rate λ and time in system W. Long enough window that the start and end backlog are small relative to throughput.
- **Shape / source:** `PTS` + `TS` · `P`: `sum(inflight)` against `sum(rate(dur_sum[w]))`
- **Misuse → guard:** Duration recorded only on completion misses in-flight stuck work, so the law appears violated during incidents. Warn on non-steady windows; use it as an instrumentation check, not as a forecast.
- **Ops:** A worker pool whose claimed 200 ms latency cannot match its in-flight count.
- **Priority:** **Must-have.** Nearly free, and it validates the signals every other queue chart depends on.
- **Sources:** [Little 2011][little]

### 51. Cumulative arrival-departure curves (N-curves, cumulative flow diagram)
- **Question:** When did backlog build, how large, and how long did items wait?
- **Read:** Vertical gap is work in system. Horizontal gap is time in system (under FIFO). Slopes are arrival and service rates. Parallel lines mean stable; widening means overload.
- **Data:** Arrival and completion counters or item events, same boundary, no lost items.
- **Shape / source:** `TS` (two cumulative series) · `P`, or `SQL` (more exact)
- **Misuse → guard:** Counter resets and dropped work break the curves. Reconcile against known exits; state when the horizontal reading is invalid (non-FIFO, retries).
- **Ops:** Item pipeline stages, showing which stage starves or floods the next.
- **Priority:** **Must-have.** The native chart for stocks and flows, and it needs only counters.
- **Sources:** [Newell 1982][newell]; [Little 2011][little]

### 52. Offered load versus goodput map (congestion collapse, metastability hysteresis)
- **Question:** Does throughput collapse under overload, and does it *recover* when load falls? Decides on load shedding and retry budgets.
- **Read:** Goodput tracks offered load to capacity. A flat line is graceful; a falling line is collapse. If the return path stays low after load falls, the system is metastable: a sustaining loop is holding it down.
- **Data:** First-attempt demand separately from retries, goodput, errors and timeouts. Time-ordered. Up and down load path.
- **Shape / source:** `TRAJ` · `P+T`, `X` to establish capacity
- **Misuse → guard:** Without separating retries, offered load is itself contaminated by the feedback. Refuse the "metastable" label unless the trigger has ended and the degradation persisted.
- **Ops:** Retry storm: after a brief database slowdown ends, retries keep the service saturated.
- **Priority:** **Must-have.** It shows the failure mode most specific to software feedback.
- **Sources:** [Bronson et al. 2021][bronson]; [Huang et al. 2022][huang]; [Jacobson 1988][jacobson]

### 53. Latency heatmap (time vs latency histogram)
- **Question:** How is latency distributed over time? Are there modes, bands or a tail that percentiles hide?
- **Read:** Bimodal bands reveal cache hit and miss, or retry timeouts. A rising tail with a stable median indicates queueing or a subset fault.
- **Data:** Histogram series with buckets suited to the range, aggregated before quantiles.
- **Shape / source:** `GRID` · `P`: `sum by (le)(rate(x_bucket[w]))`
- **Misuse → guard:** Classic-bucket `histogram_quantile` assumes a uniform distribution within a bucket ([docs][prom-fn]), so a p99 inside a wide bucket is an interpolation. Show bucket bounds; never average percentiles. Warn about coordinated omission in load tests.
- **Ops:** Retry at a 1 s timeout appears as a distinct band at 1 s and 2 s.
- **Priority:** **Must-have.** Essential for seeing the tail that control decisions act on.
- **Sources:** [Gregg, latency heatmaps][gregg]; [Prometheus histograms][prom-hist]; [Tene, wrk2][wrk2]

### 54. Variance-time plot (burstiness, aggregated variance, Hurst estimate)
- **Question:** Does burstiness fade as the time window grows? Decides buffer sizing and whether smoothing will help.
- **Read:** Log variance vs log aggregation. Slope -1: short-range dependence. Shallower slope (-β, with H = 1 - β/2): long-range dependence.
- **Data:** Fine-grained arrivals over a long, stationary window, spanning several decades of scale.
- **Shape / source:** `CURVE±` · `P+T`, `SQL`
- **Misuse → guard:** Trends and level shifts mimic long-range dependence. Detrend and report H with an interval. Scrape-interval counters limit the fine end.
- **Ops:** Testing whether queue sizing based on Poisson arrivals is badly optimistic.
- **Priority:** Niche. Useful for capacity specialists, seldom needed day to day.
- **Sources:** [Leland et al. 1994][leland]

### 55. AIMD phase plot (Chiu-Jain vector diagram)
- **Question:** Do competing clients converge to efficient, fair sharing?
- **Read:** Two clients' rates as axes. Trajectory converges to the intersection of the efficiency and fairness lines, with a sawtooth around it.
- **Data:** Per-client allowed rates, congestion signals, ideally few clients.
- **Shape / source:** `TRAJ` · `P+T`
- **Misuse → guard:** The classic result assumes synchronised feedback. With many clients, show the fairness index rather than the plot.
- **Ops:** Adaptive concurrency limits on two callers sharing a backend.
- **Priority:** Niche. A special case of #18, relevant only to AIMD-style limiters.
- **Sources:** [Chiu & Jain 1989][chiu]; [Jacobson 1988][jacobson]; [RFC 8289][codel] for a delay-based control loop

---

## Ranked top 15

Ranked by decisions supported, feasibility from passive telemetry, and resistance to misreading.

| Rank | Chart | Entry | Why here |
|---:|---|---:|---|
| 1 | Utilization-latency curve | 48 | Sets capacity and autoscaler targets |
| 2 | Constraint and saturation timeline | 33 | Says whether the controller could act at all |
| 3 | Event-aligned response | 46 | Real dynamics from natural experiments |
| 4 | Offered load vs goodput | 52 | Exposes collapse and failed recovery |
| 5 | Little's law consistency | 50 | Validates the queue signals |
| 6 | Latency heatmap | 53 | Shows modes and tails hidden by percentiles |
| 7 | Cumulative arrival-departure curves | 51 | The native stock-and-flow chart |
| 8 | PSD and spectrogram | 15 | Finds and dates oscillation |
| 9 | Limit cycle vs noise | 22 | Separates causes with opposite fixes |
| 10 | Measured phase portrait | 18 | Shows the loop itself from two series |
| 11 | Model-residual control chart | 41 | Valid drift detection under feedback |
| 12 | Excitation and identifiability card | 9 | Stops false plant models |
| 13 | Model vs held-out data | 11 | Plain test of predictive value |
| 14 | Residual correlation | 10 | Shows what the model missed |
| 15 | Step and impulse estimate | 16 | Gain, delay and settling time |

**Build order differs from rank.** #9 must ship before #10, #11 and #16. The aligned sampling layer must ship before #15, #18 and #22.

**Most likely to be overbuilt:** Lyapunov exponents (#25), recurrence plots (#26), delay embedding (#27) and early-warning alerts (#30).

---

## Analytical workflows

### W1. Did this change the system?
1. Check signal validity and Little's law (#50).
2. Mark the change and view the event-aligned response (#46).
3. Test the residual for a shift (#41), then date it (#45). If the shift predates the change, stop.
4. Check the actuator and constraints (#33). The change may have moved effort, not outcome.
5. Estimate the effect against unaffected controls (#47).
6. If dynamics may have changed, compare step responses before and after (#16).

**Output:** changed, not detected, or confounded, with effect size and interval. "No change detected" must state the smallest detectable effect.

### W2. Is this oscillation a limit cycle or noise?
1. Re-query at raw resolution, and confirm the period is observable (#15).
2. Check for persistent narrow peak and when it began (#15).
3. Test envelope and amplitude distribution (#22), with a surrogate if marginal (#28).
4. Look for an external driver at that period: cron, batch or upstream (#37, #13).
5. If there is none, inspect replicas against queue (#18) and desired against actual (#29, #33).
6. Confirm by a safe change: alter tolerance or delay in simulation or canary. A true limit cycle changes amplitude or period with the loop; a forced one keeps the driver's period.

**Output:** self-sustained, forced, resonant noise or inconclusive.

### W3. Can we trust this model?
#9 identifiability, then #11 held-out fit, #10 residuals, #16 step response with bands, #31 validity across load. Failing any step limits the model's allowed use: explanation only, simulation, or control.

### W4. Why won't it recover?
#33 is something at a limit? #51 is backlog still widening? #52 did goodput fail to return after load fell? #53 are timeout or retry bands present? Then test a sustaining loop by reducing retries or shedding load. Only then call it metastable (#19 or #20 can explain it, on a declared model).

### W5. How much capacity do we need, and where's the limit?
#50, then #48 on the true bottleneck, #49 from a load test, #31 for how gain changes with load, #54 for burstiness, and #33 to check actuators can reach the required value in time.

### W6. Are two controllers fighting?
#37 shared oscillation, #18 trajectory across their outputs, #7 step-response matrix, #6 RGA. Then re-pair, decouple or separate time scales.

### W7. Is it the controller, the plant or the disturbance?
#33 saturated? If so, stop tuning. #36 could feedback do better? #29 actuator nonlinearity? #16 did the plant change? #41 is a new disturbance present? This sequence is the core of control performance assessment.

### W8. Is it safe and worthwhile to run an experiment?
#9 shows what passive data cannot answer. #17 designs the smallest test. #33 confirms headroom. Run with abort limits. Validate with #16, #10 and #11, and record the result as a versioned model.

---

## Shared infrastructure

In order of leverage:

1. **Faithful signal access.** Fetch raw samples onto a regular grid, with a gap mask and no hidden smoothing. Carry scrape interval, range window and step as metadata. Compute the observable period band for every chart.
2. **Loop role metadata.** Declare or infer with confirmation: output, actuator, setpoint, disturbance, limits, delay, units, scale, boundary, and open or closed status. Most guards depend on this.
3. **Validity gate.** A shared `refuse / warn / show with confidence` engine with explicit checks: closed loop, excitation, stationarity, autocorrelation, sample size, coverage, saturation and gaps. Refusals explain what data would fix them.
4. **Transform service.** Detrend, deseasonalise, resample, align, prewhiten, ACF/CCF, Welch PSD, STFT, coherence, Hilbert envelope, CUSUM/EWMA, changepoints. PromQL cannot do these.
5. **Uncertainty as data.** `CURVE±` everywhere, with effective sample size accounting for autocorrelation. Bootstrap for time series and surrogate generation live here.
6. **Model registry.** Versioned `SS`/`TF` models with origin (fitted or declared), training window, validation results, operating envelope and allowed use.
7. **Event and annotation store.** Deployments, config changes, scale events, incidents, experiments, each marked **scheduled or reactive**, because #46 and #47 depend on that.
8. **Prediction vintages.** Store what was predicted at decision time for #32, #34 and #41, and to judge models honestly.
9. **Multiple-testing control.** Any "search across all metrics" view (#13, #37, #44, #45) needs false-discovery control and must report how many pairs it searched.
10. **Experiment harness.** Signal generation, limits, approval, abort, rollback and logging. Needed only for `X` charts, but it unlocks reliable identification.
11. **Time-ordered rendering.** One `TRAJ` renderer and one `GRID` renderer cover around a third of this catalogue.

## Excluded, deliberately

- **Structured singular value (mu) plots, H-infinity weighting views:** need formal uncertainty models that ergostat users will not have.
- **Correlation dimension, entropy spectra, Koopman/DMD spectra:** no operational decision depends on them, and they are easily fooled by noise.
- **Wavelet scalograms:** only marginal gain over a spectrogram, with more parameters. `[UNSURE]`: may be worth revisiting for very bursty signals.
- **Standalone bicoherence:** keep it as a possible internal test for #22 or #29. It can misattribute external sinusoidal disturbances.

## Verification notes

- **Checked directly:** Prometheus functions, Kubernetes HPA defaults, NIST EWMA and CUSUM, the USL formula and guidance, MATLAB `sigma`, `hsvd`, `mscohere`, `spa`, `spectrogram` and `idinput` pages. Search excerpts were used for MATLAB `resid`, `compare`, `impulseest`.
- **Citation metadata only:** journal DOIs were confirmed to resolve to the stated title and author in Crossref, but most paywalled papers were **not read in full**. Claims attributed to them are standard results or come from abstracts and excerpts.
- **From standard knowledge, not re-read:** the textbook content of Khalil, Strogatz, Ljung (*System Identification: Theory for the User*), Montgomery, and Hellerstein et al. Check chapter-level details before quoting them in product copy.
- **Links not confirmed by an automated check:** the Khalil WorldCat search and the MIT copy of Rohrs et al. were rate-limited (HTTP 429) when tested. MathWorks blocks plain link checks, so its pages were confirmed through page fetches or search results instead.
- **Simulated:** closed-loop bias, I-chart false alarms, spurious correlation, coherence bias, rate-window nulls, envelope statistics and CUSUM run length. These used small synthetic cases with fixed parameters.
- **Thresholds such as "about 10 cycles" and "30 crossings" are engineering rules of thumb**, not published limits. Tune them against ergostat's own data.

## References

[strogatz]: https://doi.org/10.1201/9780429492563 "Strogatz, Nonlinear Dynamics and Chaos"
[khalil]: https://search.worldcat.org/search?q=bn%3A0130673897 "Khalil, Nonlinear Systems, 3rd ed., ISBN 0-13-067389-7"
[skog]: https://folk.ntnu.no/skoge/book/ "Skogestad & Postlethwaite, Multivariable Feedback Control"
[hell]: https://www.wiley.com/en-us/Feedback+Control+of+Computing+Systems-p-9780471266372 "Hellerstein, Diao, Parekh & Tilbury"
[ljung]: https://doi.org/10.1016/j.arcontrol.2009.12.001 "Ljung, Perspectives on system identification"
[rawlings]: https://sites.engineering.ucsb.edu/~jbraw/mpc/ "Rawlings, Mayne & Diehl, Model Predictive Control"
[moore]: https://doi.org/10.1109/TAC.1981.1102568
[lin]: https://doi.org/10.1109/TAC.1974.1100557
[liu]: https://doi.org/10.1038/nature10011
[cowan]: https://doi.org/10.1371/journal.pone.0038398
[bristol]: https://doi.org/10.1109/TAC.1966.1098266
[forssell]: https://doi.org/10.1016/S0005-1098(99)00022-9
[ljungbox]: https://doi.org/10.1093/biomet/65.2.297
[pillonetto]: https://doi.org/10.1016/j.automatica.2014.01.001
[carter]: https://doi.org/10.1109/TAU.1973.1162496
[bendat]: https://doi.org/10.1002/9781118032428
[schroeder]: https://doi.org/10.1109/TIT.1970.1054411
[kantz]: https://doi.org/10.1017/CBO9780511755798
[rosenstein]: https://doi.org/10.1016/0167-2789(93)90009-P
[eckmann]: https://doi.org/10.1209/0295-5075/4/9/004
[marwan]: https://doi.org/10.1016/j.physrep.2006.11.001
[marwan-pit]: https://arxiv.org/abs/1007.2215
[takens]: https://doi.org/10.1007/BFb0091924
[fraser]: https://doi.org/10.1103/PhysRevA.33.1134
[kennel]: https://doi.org/10.1103/PhysRevA.45.3403
[theiler]: https://doi.org/10.1016/0167-2789(92)90102-S
[scheffer]: https://doi.org/10.1038/nature08227
[boettiger-limits]: https://arxiv.org/abs/1204.6231
[boettiger-pf]: https://arxiv.org/abs/1210.1204
[astrom-relay]: https://doi.org/10.1016/0005-1098(84)90014-1
[choudhury]: https://doi.org/10.1016/j.automatica.2004.03.022
[thornhill]: https://doi.org/10.1016/j.conengprac.2006.10.011
[rugh]: https://doi.org/10.1016/S0005-1098(00)00058-3
[kalman]: https://doi.org/10.1115/1.3662552
[mehra]: https://doi.org/10.1109/TAC.1970.1099422
[rohrs]: https://dspace.mit.edu/bitstream/1721.1/2861/1/P-1302-15633517.pdf
[harris]: https://doi.org/10.1002/cjce.5450670519
[desborough]: https://doi.org/10.1002/cjce.5450700620
[page]: https://doi.org/10.1093/biomet/41.1-2.100
[roberts]: https://doi.org/10.1080/00401706.1959.10489860
[lucas]: https://doi.org/10.1080/00401706.1990.10484583
[alwan]: https://doi.org/10.1080/07350015.1988.10509640
[sas-auto]: https://support.sas.com/documentation/cdl/en/qcug/66857/HTML/default/qcug_shewhart_sect557.htm
[nist-shew]: https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc32.htm
[nist-cusum]: https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm
[nist-ewma]: https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc324.htm
[chow]: https://doi.org/10.1109/TAC.1984.1103593
[isermann]: https://doi.org/10.1007/3-540-30368-5
[qin]: https://doi.org/10.1002/cem.800
[venkat]: https://doi.org/10.1016/S0098-1354(02)00160-6
[smear]: https://skoge.folk.ntnu.no/prost/proceedings/ecc-2013/data/papers/0912.pdf
[granger]: https://doi.org/10.2307/1912791
[schreiber]: https://doi.org/10.1103/PhysRevLett.85.461
[pelt]: https://arxiv.org/abs/1101.1438
[bocpd]: https://arxiv.org/abs/0710.3742
[haurwitz]: https://doi.org/10.1175/1520-0493(1981)109%3C2074:ACOTSE%3E2.0.CO;2
[causalimpact]: https://arxiv.org/abs/1506.00356
[kingman]: https://doi.org/10.1017/S0305004100036094
[tail]: https://doi.org/10.1145/2408776.2408794
[usl]: http://www.perfdynamics.com/Manifesto/USLscalability.html
[gcap]: https://doi.org/10.1007/978-3-540-31010-5
[little]: https://doi.org/10.1287/opre.1110.0940
[newell]: https://doi.org/10.1007/978-94-009-5970-5
[bronson]: https://doi.org/10.1145/3458336.3465286
[huang]: https://www.usenix.org/conference/osdi22/presentation/huang-lexiang
[jacobson]: https://doi.org/10.1145/52325.52356
[gregg]: https://www.brendangregg.com/HeatMaps/latency.html
[prom-fn]: https://prometheus.io/docs/prometheus/latest/querying/functions/
[prom-hist]: https://prometheus.io/docs/practices/histograms/
[wrk2]: https://github.com/giltene/wrk2
[leland]: https://doi.org/10.1109/90.282603
[chiu]: https://doi.org/10.1016/0169-7552(89)90019-6
[codel]: https://www.rfc-editor.org/rfc/rfc8289
[hpa]: https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/
[m-hsvd]: https://www.mathworks.com/help/control/ref/dynamicsystem.hsvd.html
[m-sigma]: https://www.mathworks.com/help/control/ref/dynamicsystem.sigma.html
[m-resid]: https://www.mathworks.com/help/ident/ref/resid.html
[m-resan]: https://www.mathworks.com/help/ident/ug/what-is-residual-analysis.html
[m-compare]: https://www.mathworks.com/help/ident/ref/compare.html
[m-coh]: https://www.mathworks.com/help/signal/ref/mscohere.html
[m-spec]: https://www.mathworks.com/help/signal/ref/spectrogram.html
[m-imp]: https://www.mathworks.com/help/ident/ref/impulseest.html
[m-idinput]: https://www.mathworks.com/help/ident/ref/idinput.html
