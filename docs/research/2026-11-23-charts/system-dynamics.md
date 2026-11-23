# System dynamics and flow charts for ergostat

Research of 2026-11-23. Scope: diagrams and charts from system dynamics (SD), plus the operations-flow charts closest to stocks and flows.

## Read this first

**Five conclusions that should change what gets built:**

1. **Stock-flow reconciliation is the most valuable chart here, and most tools do not have it.** If a stock's change does not equal inflow minus outflow, every chart built on that stock is suspect. It should run before the others and gate them.
2. **Do not rely on people to read stocks from flow charts.** Booth Sweeney and Sterman found that highly educated adults fail simple bathtub tasks. Cronin, Gonzalez and Sterman found the error survives changes of display, context and motivation. A better picture will not fix this, so ergostat should compute the accumulation and show it.
3. **A common flow-community claim about Little's law is too strong.** L = λW over a finite window is an identity and needs neither stationarity nor an empty system (Little 2011, LL.2), *provided* λ counts items present at the start and W counts only time inside the window. The "stable system" assumptions apply when you substitute the average cycle time of *completed* items, which is what most tools do. So ergostat should compute the exact form and report the gap to the naive form.
4. **Completed-only cycle-time statistics are biased in exactly the situation where people look at them.** When work is stuck, the stuck items are absent from the sample. Treat open items as right-censored.
5. **Loop dominance, archetypes and Sobol indices describe the model, not the system.** They are worth having only with a calibrated model, and each must say so on its face. An archetype cannot be identified from a time series alone.

**New input shapes needed.** The six existing shapes do not cover three things:

| New shape | Contents | Used by |
|---|---|---|
| **Structure graph** | Typed nodes (stock, flow, auxiliary, constant), signed edges, units, delays, loops, subsystem and provenance | CLD, SFD, boundary, policy, trees, loop charts |
| **Ensemble** | N runs of the model: run id, parameter draw, seed, scenario, series | Fan, policy comparison, sensitivity, screening |
| **Item spans** | One row per item per state: entered, left (null if open), with censoring explicit | CFD, aging, survival, scatter, delay profile, VSM |

Phase plots also need **points with order preserved**, a small extension of the points shape.

**Evidence labels** on each source in the [reference list](#sources). DOIs were checked against Crossref; many publisher pages refuse automated requests, so those links were not opened:

- **[read]**: I read the relevant text this session.
- **[record]**: I confirmed that the publication exists (DOI, catalogue or abstract) but did not read the full text.
- **[book]**: a standard book I did not open. Claims attributed to it come from prior knowledge and secondary sources. Chapter numbers are especially worth checking.

**Marked uncertain** in the text with *(unverified)*. The ergostat product itself was not inspected, so nothing here says what it already has.

**Abbreviations used for how to obtain a chart:** PromQL; PromQL + transform; SQL (over item events); Structure (the system model's structure); Simulation.

## Contents

- [A. Model structure](#a-model-structure) (1-7)
- [B. Behavior and accumulation](#b-behavior-and-accumulation) (8-14)
- [C. Loop dominance](#c-loop-dominance) (15-17)
- [D. Uncertainty, policy and sensitivity](#d-uncertainty-policy-and-sensitivity) (18-23)
- [E. Calibration and validation](#e-calibration-and-validation) (24-28)
- [F. Delays and aging](#f-delays-and-aging) (29-30)
- [G. Operations flow](#g-operations-flow) (31-41)
- [H. Learning and communication](#h-learning-and-communication) (42-43)
- [Left out on purpose](#left-out-on-purpose)
- [Ranked top 15](#ranked-top-15)
- [Analytical workflows](#analytical-workflows)
- [Shared infrastructure](#shared-infrastructure)
- [Sources](#sources)

---

## A. Model structure

### 1. Causal loop diagram: must-have

1. **Aliases:** CLD, influence diagram (loosely; decision analysis uses that term differently), feedback diagram.
2. **Question / decision:** What feedback could produce this behavior? Decide which loop to test or break, e.g. whether retries feed the load that causes them.
3. **Reading:** Trace each loop; an even number of negative links makes it reinforcing, an odd number balancing. Good: few named loops, delays marked, one story each. Bad: a hairball, unnamed loops, no delays.
4. **Needs:** Variables, signed causal links, delay marks, loop names.
5. **Shape:** New: structure graph.
6. **Obtain:** Structure. Derive it from the model rather than drawing it by hand, so it cannot disagree with the equations.
7. **Misuse / prevention:** CLDs hide accumulation, and standard polarity definitions break on flow-to-stock links (Richardson 1986, 1997). Polarity can also flip across the operating range. *Prevent:* mark stocks in the CLD, label links as fitted, declared or hypothesized, and warn where a nonlinear function's slope changes sign. Refuse to show a loop as "confirmed" from correlation.
8. **Software / ops:** Yes. More failed merges → more retries → more queue load → longer waits → staler branches → more failed merges (reinforcing).
9. **Priority:** Must-have: it is the shortest explanation of why a system behaves as it does.
10. **Sources:** [Sterman 2000][sterman2000], [Richardson 1986][rich1986], [Richardson 1997][rich1997].

### 2. Stock-and-flow diagram: must-have

1. **Aliases:** SFD, level-and-rate diagram, Forrester diagram.
2. **Question / decision:** Where does work accumulate, what moves it, and what controls each rate? Decide where to intervene: inflow, outflow, or the rule that sets them.
3. **Reading:** Boxes are stocks, valves are flows, clouds are the model boundary. Good: units balance, every stock has a real flow, sources and sinks are deliberate. Bad: flows from auxiliaries into stocks with no conservation, or clouds hiding a stock that matters.
4. **Needs:** Stocks, flows, auxiliaries, constants, equations, units, initial values. A live view also needs current values.
5. **Shape:** New: structure graph, optionally joined to latest time-series values.
6. **Obtain:** Structure, with PromQL for live values.
7. **Misuse / prevention:** Drawing a rate as a stock (a "queue length per minute") or a gauge as a flow. *Prevent:* run a unit check; refuse to bind a counter's rate to a stock; mark each element as measured, inferred or assumed.
8. **Software / ops:** Yes. Queued → Running → Awaiting merge → Merged, with a rework flow from failed checks back to Queued.
9. **Priority:** Must-have: it is ergostat's core object.
10. **Sources:** [Forrester 1961][forrester1961], [Sterman 2000][sterman2000], [Ford 2009][ford2009].

### 3. Subsystem diagram: useful

1. **Aliases:** Sector diagram, sector map, model overview.
2. **Question / decision:** What are the major parts and what crosses between them? Decide ownership and the scope of a change.
3. **Reading:** Blocks are sectors; arrows carry material, information or money. Good: few, thick, labeled interfaces. Bad: everything connected to everything, which means the partition is wrong.
4. **Needs:** Sector assignment for each variable, cross-sector links.
5. **Shape:** New: structure graph, aggregated.
6. **Obtain:** Structure.
7. **Misuse / prevention:** Mistaking the org chart for system structure. *Prevent:* record sector ownership explicitly, and report the share of links that cross sectors.
8. **Software / ops:** Yes. Intake, build, merge and incident sectors, with engineer time as the shared resource crossing all of them.
9. **Priority:** Useful: the entry view for a large model, but it adds no analysis.
10. **Sources:** [Morecroft 1982][morecroft1982], [Sterman 2000][sterman2000].

### 4. Policy structure diagram: useful

1. **Aliases:** Decision-function diagram (Morecroft).
2. **Question / decision:** What information does each decision rule actually see, and how late? Decide whether to fix the rule or fix its input.
3. **Reading:** Each policy is a node with its information inputs and the flow it sets. Good: inputs are observable and timely. Bad: a rule fed by a stale or proxy signal, or one that ignores the supply line.
4. **Needs:** Decision points, information sources, perception delays.
5. **Shape:** New: structure graph, filtered to decision nodes.
6. **Obtain:** Structure.
7. **Misuse / prevention:** Writing the *stated* policy rather than the policy in use. *Prevent:* compare the declared rule with its observed input-output behavior and show the difference.
8. **Software / ops:** Yes, and well suited. An autoscaler or work scheduler is literally a policy. Example: a worker pool sized on queue length alone, ignoring work already started, will overshoot.
9. **Priority:** Useful: the best structural view for finding bad control rules.
10. **Sources:** [Morecroft 1982][morecroft1982], [Morecroft 2007][morecroft2007], [Sterman 1989][sterman1989].

### 5. Model boundary chart: useful

1. **Aliases:** Boundary table, endogenous/exogenous/excluded list.
2. **Question / decision:** What does the model explain, what does it take as given, and what does it ignore? Decide whether the model can answer this question at all.
3. **Reading:** Three columns. Good: the variables the question depends on are endogenous. Bad: the main driver is exogenous, which means the model cannot explain it.
4. **Needs:** Classification of every variable, plus a list of deliberate exclusions, which only a person or agent can supply.
5. **Shape:** New: structure graph, as a table.
6. **Obtain:** Structure for the first two columns. The excluded column is declared.
7. **Misuse / prevention:** An empty "excluded" column reads as completeness. *Prevent:* show "not declared" rather than empty, and warn when a policy test varies something exogenous.
8. **Software / ops:** Yes. If arrival rate is exogenous, the model cannot show that slow reviews reduce submissions.
9. **Priority:** Useful: cheap, and the honest caveat on every model answer.
10. **Sources:** [Sterman 2000][sterman2000], [Forrester and Senge 1980][fs1980].

### 6. Causes tree, uses tree and loop inventory: useful

*Added; not in the brief.*

1. **Aliases:** Causes/uses strip (Vensim), loop list, dependency tree.
2. **Question / decision:** What directly drives this variable, what does it affect, and which loops is it in? Decide what to inspect next.
3. **Reading:** Expand outward from one variable. Good: shallow and interpretable. Bad: an auxiliary with no causes, or a stock in no loop when the story needs one.
4. **Needs:** Model graph and a loop enumeration. Full enumeration can explode; large models need a heuristic ([Eberlein and Schoenberg 2020][eberlein2020]).
5. **Shape:** New: structure graph.
6. **Obtain:** Structure.
7. **Misuse / prevention:** Treating a partial loop list as complete. *Prevent:* state whether enumeration was exhaustive.
8. **Software / ops:** Yes. "What feeds merge wait?" expands to queue depth, runner capacity and flake rate.
9. **Priority:** Useful: the navigation primitive for every structural question.
10. **Sources:** [Eberlein and Schoenberg 2020][eberlein2020], [Sterman 2000][sterman2000].

### 7. Graphical function plot: useful

*Added; not in the brief.*

1. **Aliases:** Table function, lookup, effect curve.
2. **Question / decision:** What nonlinear relationship has the model assumed? Decide whether to measure it.
3. **Reading:** Plot the curve with observed operating points on top. Good: passes through a sensible reference point, saturates properly, and data covers the range used. Bad: the simulation runs where there is no data.
4. **Needs:** Table values, plus observed (x, y) pairs if any.
5. **Shape:** Points, plus the curve from the structure graph.
6. **Obtain:** Structure, with PromQL + transform for the overlay.
7. **Misuse / prevention:** Invented curves presented as findings, and silent extrapolation. *Prevent:* label origin (fitted or assumed), and show the share of simulated time spent outside the observed range.
8. **Software / ops:** Yes. Effect of schedule pressure on error rate in a review process.
9. **Priority:** Useful: these curves often carry the model's real assumptions.
10. **Sources:** [Sterman 2000][sterman2000], [Ford and Sterman 1998][fordsterman1998].

---

## B. Behavior and accumulation

### 8. Behavior-over-time graph: must-have

1. **Aliases:** BOT, BOTG, time plot.
2. **Question / decision:** What pattern is this: growth, goal-seeking, oscillation, S-shape, overshoot and collapse? The pattern narrows the candidate structures, and so the fix.
3. **Reading:** Read the mode, not the wiggles. Exponential growth suggests a dominant reinforcing loop, goal-seeking a balancing loop, oscillation a balancing loop with delay. Good: long enough to show the mode. Bad: a window shorter than the system's slowest delay.
4. **Needs:** One or more series, ideally with intervention annotations.
5. **Shape:** Time series.
6. **Obtain:** PromQL.
7. **Misuse / prevention:** Inferring structure from shape alone (different structures can produce one pattern); dual axes creating false correlation; plotting stocks and rates on one axis. *Prevent:* warn when the window is under about 3x the known delay; keep units on separate axes; word pattern labels as hypotheses.
8. **Software / ops:** Yes. Queue depth oscillating every few hours after an autoscaler change.
9. **Priority:** Must-have: the base chart of the field.
10. **Sources:** [Sterman 2000][sterman2000], [Meadows 2008][meadows2008].

### 9. Reference mode: useful

1. **Aliases:** Reference behavior pattern, dynamic hypothesis target.
2. **Question / decision:** What behavior are we trying to explain, and what would we want instead? Sets the model's purpose and the pass criterion.
3. **Reading:** A historical line, a "feared" future and a "hoped" future. Good: names a pattern and horizon before modeling. Bad: a single KPI target with no dynamics.
4. **Needs:** History, plus a drawn or declared expected path, with its author recorded.
5. **Shape:** Time series, with a declared series alongside.
6. **Obtain:** PromQL for history; the expected path is declared.
7. **Misuse / prevention:** Drawing the reference mode after seeing the model's output, which makes the test circular. *Prevent:* timestamp it and flag any edit made after a fit.
8. **Software / ops:** Yes. "Merge queue wait has climbed from 20 minutes to 3 hours over six weeks; we expect it to hold under 30."
9. **Priority:** Useful: a small feature that makes validation meaningful.
10. **Sources:** [Sterman 2000][sterman2000], [Forrester and Senge 1980][fs1980].

### 10. Stock-flow reconciliation: must-have (rank 1)

1. **Aliases:** Mass balance, conservation check, inventory reconciliation, bathtub check.
2. **Question / decision:** Does the measured stock equal its initial value plus inflows minus outflows? Decide whether the data and the model can be trusted, and where work is leaking.
3. **Reading:** Plot the measured stock, the integrated stock and the residual. Good: residual flat within measurement tolerance. Bad: *drift* means a missing flow; a *step* means a one-off loss, backfill or counter reset; *periodic* error usually means sampling misalignment.
4. **Needs:** A stock series, all inflow and outflow counters, and a start value. Exact results need item events.
5. **Shape:** Time series (three aligned series).
6. **Obtain:** PromQL + transform for an approximate result, SQL for an exact one:

   ```promql
   (stock - stock offset 1h)
     - (sum(increase(inflow_total[1h])) - sum(increase(outflow_total[1h])))
   ```

   `increase()` extrapolates to the window edges and adjusts for counter resets ([Prometheus functions][prom]), so non-zero residuals are expected. This needs a tolerance, and the labels on the two sides must match.
7. **Misuse / prevention:** Forcing the balance with a plug flow hides the finding. Treating a Prometheus residual as exact produces false alarms. *Prevent:* never auto-add a balancing flow; report the residual as "unexplained flow" with units; show which method was used; **lower confidence on every dependent chart when the balance fails.**
8. **Software / ops:** Yes. Items entered "in review" minus items left does not match the review count, revealing that cancelled items leave without an event.
9. **Priority:** Must-have: it is cheap and validates everything downstream.
10. **Sources:** [Sterman 2000][sterman2000], [Booth Sweeney and Sterman 2000][bathtub], [Cronin et al. 2009][cronin2009], [Prometheus functions][prom].

### 11. Goal-gap chart: must-have

1. **Aliases:** Goal-seeking chart, desired vs actual, error chart.
2. **Question / decision:** How far is the stock from its goal, is the gap closing, and how long will it take? Decide whether to add capacity or change the goal.
3. **Reading:** Plot actual, goal and the corrective flow. Good: the gap shrinks with a stable adjustment time. Bad: a steady-state gap (corrective flow saturated); oscillation around the goal (delay too long for the gain); **a goal drifting toward actual, the signature of eroding goals.**
4. **Needs:** Stock, the goal *as a versioned series*, the corrective flow.
5. **Shape:** Time series. The gap against corrective flow is two signals.
6. **Obtain:** PromQL + transform (gap, adjustment-time fit).
7. **Misuse / prevention:** Showing only today's goal rewrites history and hides drift. *Prevent:* store goal history, and warn if the goal has moved toward actual.
8. **Software / ops:** Yes. An SLO of 95% quietly restated to 90% after two missed quarters.
9. **Priority:** Must-have: it directly answers "are we getting there?" and exposes goal erosion.
10. **Sources:** [Sterman 2000][sterman2000], [Kim and Anderson 1998][archetypes].

### 12. Phase plot: useful

1. **Aliases:** Phase portrait, state-space plot, net rate vs stock.
2. **Question / decision:** Where are the equilibria, are they stable, and is there a tipping point? Decide how far the system can be pushed.
3. **Reading:** For one stock, plot net flow (y) against stock (x). A zero crossing is an equilibrium. It is stable if the slope there is negative, unstable if positive. For two stocks, a spiral inward is damped oscillation and a closed orbit is a limit cycle.
4. **Needs:** Stock and net flow with time order, or the model's rate equation.
5. **Shape:** Points with order preserved (small extension), or transfer function from the model when linearized.
6. **Obtain:** PromQL + transform from data; Simulation for the full field.
7. **Misuse / prevention:** Empirical plots mix regimes and confound by exogenous inputs, producing false "equilibria". Derivatives amplify noise. *Prevent:* color by time, smooth with a stated method, and refuse to label stability unless the crossing has data on both sides.
8. **Software / ops:** Yes. Net backlog growth against backlog shows the point past which interruptions outrun recovery.
9. **Priority:** Useful: strongest test for tipping behavior, but needs an expert or a guided reading.
10. **Sources:** [Sterman 2000][sterman2000], [Rudolph and Repenning 2002][rudolph2002].

### 13. Equilibrium and tipping chart: useful

1. **Aliases:** Rate-balance diagram, inflow-outflow vs stock.
2. **Question / decision:** At what stock level do inflow and outflow balance, and what level is the point of no return? Decide the operating limit and the admission-control threshold.
3. **Reading:** Plot inflow and outflow curves against the stock. Crossings are equilibria. Good: a wide margin from the operating point to the unstable crossing. Bad: outflow that *falls* as the stock rises, as when overload reduces capacity, which creates collapse.
4. **Needs:** Rate equations, or data covering high-load states.
5. **Shape:** Points for empirical curves; transfer function from a model when analytic.
6. **Obtain:** Simulation preferred; PromQL + transform if overload has been observed.
7. **Misuse / prevention:** Extrapolating the outflow curve into loads never seen, exactly where it matters. *Prevent:* draw unobserved regions as assumed, and refuse to state a numeric tipping point from data that never reached it.
8. **Software / ops:** Yes. Incident response: past some number of concurrent incidents, context switching cuts resolution rate and the stock runs away (Rudolph and Repenning's quantity-driven collapse has this form).
9. **Priority:** Useful: high value for resilience, limited by data at the extremes.
10. **Sources:** [Rudolph and Repenning 2002][rudolph2002], [Sterman 2000][sterman2000].

### 14. System archetypes: useful, as hypotheses only

1. **Aliases:** Systems archetypes, generic structures, system traps (Meadows).
2. **Question / decision:** Is this a known trap, and what is the known way out? Decide whether the current fix addresses the cause.
3. **Reading:** Match *structure and behavior together*:

   | Archetype | Data signature (necessary, not sufficient) | Ops example | Standard way out |
   |---|---|---|---|
   | Limits to success | Growth slows as a constraint utilization rises | Throughput flattens as runners saturate | Remove the limit before it binds |
   | Fixes that fail | Symptom improves, then returns worse after a delay | Retries cut failures now, add load later | Fix cause, tolerate short-term pain |
   | Shifting the burden | Symptomatic fix rises while fundamental capability falls | Manual re-runs rise, test investment falls | Reduce the symptomatic route, fund the fundamental |
   | Drifting (eroding) goals | Goal trends toward actual | SLO relaxed after each miss | Anchor goal externally |
   | Escalation | Two series ratchet up in response to each other | Teams inflate priorities | Unilateral de-escalation or shared limit |
   | Success to the successful | Allocation share diverges between peers | One team's PRs always go first | Allocate independently of past wins |
   | Tragedy of the commons | Individual use rises, shared yield per user falls | All teams flood a shared CI pool | Quotas or governance |
   | Growth and underinvestment | Demand falls after quality declines, capacity investment lags | Slow builds reduce use, justifying no investment | Invest ahead, hold the quality standard |

   Add the **capability trap** (Repenning and Sterman 2002), a form of shifting the burden and the most relevant one for engineering: working harder now erodes the capability that makes work possible.

4. **Needs:** Structure graph with loops, and the series on those loops, with delays.
5. **Shape:** New: structure graph, plus time series.
6. **Obtain:** Structure for the template match; PromQL + transform for the signature.
7. **Misuse / prevention:** The biggest in this list: archetypes are easy to see everywhere. Time series alone cannot identify one. *Prevent:* **refuse to name an archetype from data alone**; show "candidate", list the loops and evidence for and against, and state what test would falsify it.
8. **Software / ops:** Yes. See table.
9. **Priority:** Useful: a strong vocabulary for explanations, but a poor automatic detector.
10. **Sources:** [Senge 1990][senge1990], [Kim and Anderson 1998][archetypes], [Meadows 2008][meadows2008], [Repenning and Sterman 2001][rs2001], [Repenning and Sterman 2002][rs2002].

---

## C. Loop dominance

**Recommendation: implement Loops That Matter only.** Pathway participation and eigenvalue elasticity add little for this product and cost much more to do well.

### 15. Loops That Matter dominance timeline: must-have

1. **Aliases:** LTM, loop score chart, relative loop score.
2. **Question / decision:** Which loops drive the model's behavior in each period, and when does control shift? Decide which loop to act on *now*.
3. **Reading:** Stacked or lined relative loop scores (range -1 to 1) over time. A loop or set is dominant if it explains at least 50% of the change in the period. Good: clear phases that match the story. Bad: many loops near zero with no dominant set, so no simple explanation exists.
4. **Needs:** Model equations and a simulation run; link scores need partial recomputation at each step.
5. **Shape:** New: ensemble (one run) joined to the structure graph, output as a time series per loop.
6. **Obtain:** Simulation + Structure.
7. **Misuse / prevention:** Reading dominance as a fact about the real system. **LTM is undefined at equilibrium**: all scores are defined as 0 when nothing changes (Schoenberg et al.). So in a stable system it reports nothing, though loops are still holding it there. *Prevent:* label "in the model", grey out equilibrium periods rather than plotting zero, and gate on a passing fit.
8. **Software / ops:** Yes. Queue growth is first dominated by the arrival loop; after autoscaling catches up, the balancing capacity loop dominates; then a retry loop takes over during an outage.
9. **Priority:** Must-have: of the three methods, it is the one directly applicable to discrete and discontinuous models, which ops models are.
10. **Sources:** [Schoenberg et al. 2020][ltm], [LTM preprint][ltmarxiv], [Eberlein and Schoenberg 2020][eberlein2020], [Stella docs][stellaltm].

### 16. Pathway participation: niche

1. **Aliases:** PPM, Digest method.
2. **Question / decision:** For one chosen stock, which pathway most influences it in each behavior phase?
3. **Reading:** Time is split into phases by the sign of the stock's slope and curvature; each phase names its dominant structure.
4. **Needs:** Model equations, partial derivatives, a selected variable.
5. **Shape:** New: structure graph + ensemble.
6. **Obtain:** Simulation with derivatives.
7. **Misuse / prevention:** Depends on the chosen variable, and noisy or discrete behavior creates spurious phases. *Prevent:* do not apply to discontinuous models.
8. **Software / ops:** Weak. Ops models contain thresholds and discrete events.
9. **Priority:** Niche: LTM answers the same question with fewer assumptions.
10. **Sources:** [Mojtahedzadeh et al. 2004][ppm], [Digest conference paper][ppm2003].

### 17. Eigenvalue elasticity: niche

1. **Aliases:** EEA, LEEA, dominant-mode analysis.
2. **Question / decision:** Which loop gains most affect a behavior mode's decay rate or frequency? Decide which gain to change to damp an oscillation.
3. **Reading:** Eigenvalues give modes (real part: growth or decay; imaginary part: oscillation). A large elasticity means that loop's gain strongly moves the mode.
4. **Needs:** Differentiable equations, a linearization at each operating point, an independent loop set.
5. **Shape:** Transfer function from a model (plus structure graph).
6. **Obtain:** Structure + numeric linearization.
7. **Misuse / prevention:** Linearization is local, and thresholds break it. *Prevent:* refuse on non-differentiable models and show the operating point. It does have one real advantage over LTM: it can analyze equilibrium if the model is near-linear.
8. **Software / ops:** Partly. Useful for a smooth control loop such as an autoscaler; not for discrete work processes. The control-theory view likely covers this need better.
9. **Priority:** Niche: keep only if the control view already linearizes the model.
10. **Sources:** [Oliva EEA chapter][eea], [Kampmann 2012][kampmann2012], [Kampmann and Oliva 2006][ko2006], [Gonçalves 2009][goncalves2009].

---

## D. Uncertainty, policy and sensitivity

### 18. Monte Carlo fan chart: must-have

1. **Aliases:** Sensitivity graph, confidence bounds, uncertainty band, spaghetti plot.
2. **Question / decision:** Given what we do not know, what range of outcomes is plausible? Decide whether the result is firm enough to act on.
3. **Reading:** Nested percentile bands (commonly 50/75/95, plus min-max) with the base run. Good: narrow around the decision threshold, or clearly on one side of it. Bad: bands straddling the threshold, or a bimodal spread that a median hides.
4. **Needs:** Parameter distributions (ideally posterior from calibration), seeds, typically hundreds of runs. Vensim's docs suggest keeping runs under about 1,000 for practical reasons.
5. **Shape:** New: ensemble, summarized to bands per time.
6. **Obtain:** Simulation.
7. **Misuse / prevention:** **Bands are pointwise**: no single run need follow the 95% edge. Bands show only the uncertainty fed in, so made-up priors give made-up confidence, and structural error is absent. *Prevent:* overlay sample paths, state the source of each prior, label "parameter uncertainty only", and warn on bimodal outcomes.
8. **Software / ops:** Yes. Projected merge-queue wait after adding two runners, with arrival and flake rate uncertain.
9. **Priority:** Must-have: without it, every simulated answer overstates its certainty.
10. **Sources:** [Vensim sensitivity][vensim], [Arthur and Eberlein 1996][ae1996], [Britton et al. 1998][fan], [Struben et al. 2015][struben].

### 19. Policy and scenario comparison: must-have

1. **Aliases:** Policy run comparison, what-if chart, intervention analysis.
2. **Question / decision:** Does this change beat doing nothing, by how much, when, and at what cost? Decide whether to ship the policy.
3. **Reading:** Baseline vs policy, then the **difference with its band**, and the cumulative difference. Good: difference band clear of zero over the horizon that matters. Bad: an early gain that reverses (policy resistance), or a gain only under one assumption. Watch for **worse-before-better**, which is often the correct shape for capability investment and gets cancelled early.
4. **Needs:** Calibrated model, explicit policy change, shared random draws across arms, a horizon longer than the slowest delay.
5. **Shape:** New: ensemble, paired by draw.
6. **Obtain:** Simulation. Past changes can be evaluated on observed data, with caution.
7. **Misuse / prevention:** Comparing unpaired runs inflates noise; short horizons reward fixes that fail; testing a policy outside the data's range. *Prevent:* force common random numbers, warn when the horizon is less than about 3x the longest delay on the path, and show the range of validity.
8. **Software / ops:** Yes. Batch merges vs serial merges: higher throughput, but worse failure isolation and longer rework.
9. **Priority:** Must-have: this is the decision ergostat exists to support.
10. **Sources:** [Sterman 2000][sterman2000], [Repenning and Sterman 2001][rs2001], [Rahmandad and Sterman 2012][rgsr].

### 20. Tornado chart: useful

1. **Aliases:** One-at-a-time (OAT) sensitivity bar chart.
2. **Question / decision:** Which single assumptions move this outcome most? Decide what to measure next.
3. **Reading:** Bars sorted by outcome swing around base. Good: a few bars dominate, so effort is clear. Bad: bars crossing the decision threshold on unmeasured parameters.
4. **Needs:** Base case, low and high values for each parameter, 2k+1 runs.
5. **Shape:** Dimensions to measures.
6. **Obtain:** Simulation.
7. **Misuse / prevention:** OAT misses interactions and covers a tiny part of the input space (Saltelli et al. 2019). Arbitrary ±10% ranges make the ranking an artifact. *Prevent:* require justified ranges per parameter; label "local, no interactions"; offer Morris/Sobol when the model is strongly nonlinear.
8. **Software / ops:** Yes. Effect of flake rate, runner count and review time on merge lead time.
9. **Priority:** Useful: the cheap, readable first pass.
10. **Sources:** [Howard 1988][howard1988] *(as tornado origin: unverified)*, [Saltelli et al. 2019][saltelli2019].

### 21. Global sensitivity: Morris and Sobol: niche

1. **Aliases:** Elementary effects (Morris); variance-based indices, first-order S1 and total ST (Sobol).
2. **Question / decision:** Which parameters matter across the whole range, including interactions? Decide which to fix and which to calibrate.
3. **Reading:** Morris: mean effect vs spread; high spread means nonlinear or interacting. Sobol: ST near zero means safe to fix; ST much greater than S1 means interaction.
4. **Needs:** Input distributions, independent inputs for standard estimators, a scalar output (or one per time). Roughly r(k+1) runs for Morris, N(k+2) for the Saltelli design.
5. **Shape:** New: ensemble, output as dimensions to measures, with intervals.
6. **Obtain:** Simulation.
7. **Misuse / prevention:** Correlated inputs invalidate the standard decomposition; variance is a poor summary for heavy-tailed outputs such as latency; small N gives unstable indices. *Prevent:* show bootstrap intervals, warn on correlated priors and heavy tails, and cap run counts.
8. **Software / ops:** Partly. Justified only for a heavily used model with cheap simulation.
9. **Priority:** Niche: screening (entry 22) and a tornado answer most real questions.
10. **Sources:** [Morris 1991][morris1991], [Saltelli et al. 2010][saltelli2010], [Saltelli et al. 2019][saltelli2019].

### 22. Statistical screening: useful

1. **Aliases:** Ford-Flynn screening, correlation-over-time sensitivity.
2. **Question / decision:** Which parameters drive the output, and *when* in the run? Decide what to investigate at each phase.
3. **Reading:** Correlation between each parameter and the output across runs, plotted over time. Peaks show when a parameter has leverage.
4. **Needs:** An existing Monte Carlo ensemble with recorded parameter draws.
5. **Shape:** New: ensemble, output as a time series per parameter.
6. **Obtain:** Simulation (reuses the fan-chart runs at no added simulation cost).
7. **Misuse / prevention:** Correlation misses non-monotonic effects and is distorted by correlated draws. *Prevent:* use rank correlation, and label it as screening rather than attribution.
8. **Software / ops:** Yes. Flake rate matters during a surge; runner count matters only after the queue forms.
9. **Priority:** Useful: nearly free once ensembles exist, and more informative than a static tornado.
10. **Sources:** [Ford and Flynn 2005][fordflynn2005], [Taylor et al. 2010][taylor2010].

### 23. Parameter confidence and likelihood profile: useful

1. **Aliases:** Profile likelihood, payoff surface, bootstrap interval.
2. **Question / decision:** Does the data actually determine this parameter? Decide whether a fitted value can be used.
3. **Reading:** Plot fit against the parameter. Sharp minimum: identified. Flat valley: not identified. A ridge between two parameters: only their combination is known.
4. **Needs:** Calibration objective, error model, repeated optimization or bootstrap.
5. **Shape:** Points or distribution; new: ensemble for bootstrap.
6. **Obtain:** Simulation.
7. **Misuse / prevention:** Reported point estimates imply knowledge the data does not contain. Autocorrelated errors make intervals too narrow. *Prevent:* **show "not identifiable" rather than a number** on flat profiles, and use a block bootstrap.
8. **Software / ops:** Yes. A review-delay and a rework fraction often trade off against each other in lead-time data.
9. **Priority:** Useful: it prevents the most common calibration overclaim.
10. **Sources:** [Struben et al. 2015][struben], [Oliva 2003][oliva2003].

---

## E. Calibration and validation

### 24. Historical fit with Theil decomposition: must-have

1. **Aliases:** Simulated vs actual, Theil inequality statistics, U^M/U^S/U^C.
2. **Question / decision:** How well does the model reproduce history, and *what kind* of error remains? Decide whether to fix structure, parameters or nothing.
3. **Reading:** MSE = (S̄ − Ā)² + (s_S − s_A)² + 2(1 − r)s_S s_A, divided by MSE into U^M (bias), U^S (unequal variation), U^C (unequal covariation), summing to 1. Large U^M: systematic offset, often a parameter or initial value. Large U^S: amplitude or trend mismatch. Large U^C with small U^M and U^S: error is unsystematic, and may be noise the model should not fit. A phase shift also lands in U^C, so check the plot.
4. **Needs:** Simulated and observed series on one time base, same units.
5. **Shape:** Two signals (simulated, actual), with statistics.
6. **Obtain:** Simulation + PromQL, with a named transform.
7. **Misuse / prevention:** A good fit does not validate structure (Barlas: right behavior for the wrong reasons). Fitting and scoring the same data flatters. R² on trending series is near-meaningless. There is no standard pass threshold; 0.1 cutoffs seen online are rules of thumb. *Prevent:* show the decomposition with the overlay, mark in-sample vs holdout, and do not issue a "valid" badge.
8. **Software / ops:** Yes. A model of queue depth with high U^M has the wrong service rate; high U^C may just be bursty arrivals.
9. **Priority:** Must-have: the standard SD diagnostic, cheap, and it tells you what to fix.
10. **Sources:** [Sterman 1984][sterman1984], [Oliva 2003][oliva2003], [Barlas 1996][barlas1996], [Theil proportions][theilnote].

### 25. Residual diagnostics: useful

*Added; not in the brief.*

1. **Aliases:** Residual plot, ACF of residuals.
2. **Question / decision:** Is there structure left in the error? Decide whether the model is missing a mechanism.
3. **Reading:** Good: residuals look like noise. Bad: trends, periodicity (a missing daily cycle), or spikes aligned with known events (a missing exogenous input).
4. **Needs:** Fit residuals, event annotations.
5. **Shape:** Time series; autocorrelation as dimensions to measures.
6. **Obtain:** Simulation + PromQL + transform.
7. **Misuse / prevention:** SD models are not expected to fit noise, so demanding white residuals encourages overfitting. *Prevent:* use it to find missing structure, not as a pass test.
8. **Software / ops:** Yes. A weekly residual pattern reveals that weekend arrivals are not modeled.
9. **Priority:** Useful: fast route from "the fit is off" to the missing mechanism.
10. **Sources:** [Oliva 2003][oliva2003], [Struben et al. 2015][struben].

### 26. Model test scorecard: must-have

1. **Aliases:** Sterman's model tests, confidence-building tests, Table 21-4.
2. **Question / decision:** What has this model been tested for, and what has not? Decide what it may be used for.
3. **Reading:** One row per test: not run, passed, failed, not applicable, with evidence. Sterman's 12: boundary adequacy, structure assessment, dimensional consistency, parameter assessment, extreme conditions, integration error, behavior reproduction, behavior anomaly, family member, surprise behavior, sensitivity analysis, system improvement. *(The count of 12 and ten names are confirmed in secondary sources; "structure assessment" and "parameter assessment" are from memory of the book, unverified.)*
4. **Needs:** Automated checks for units, integration (halve the time step), extremes, fit and sensitivity; human or agent review for the others.
5. **Shape:** Dimensions to measures (test to status), linked to evidence.
6. **Obtain:** Structure + Simulation.
7. **Misuse / prevention:** Scorecards invite a false "validated". Forrester, Senge and Barlas treat validity as confidence relative to a purpose. *Prevent:* never compute one overall score, keep "not run" visible, and scope results to a question.
8. **Software / ops:** Yes. A model passes for "will more runners help?" but has not been tested for "what happens under an outage?"
9. **Priority:** Must-have: this is what makes model answers trustworthy and auditable.
10. **Sources:** [Sterman 2000][sterman2000], [Forrester and Senge 1980][fs1980], [Barlas 1996][barlas1996], [SDM-Doc][sdmdoc], [Rahmandad and Sterman 2012][rgsr].

### 27. Extreme-conditions test chart: useful

1. **Aliases:** Stress test, limit test.
2. **Question / decision:** Does the model behave sensibly when inputs go to zero or very large values? Decide whether it can be used outside normal operation.
3. **Reading:** Small multiples of each extreme with an expected invariant. Good: zero capacity gives zero outflow, stocks never go negative. Bad: output from nothing, negative queues.
4. **Needs:** A list of extreme cases and asserted invariants.
5. **Shape:** New: ensemble (one run per case), with pass/fail as dimensions to measures.
6. **Obtain:** Simulation.
7. **Misuse / prevention:** Clamping with MAX(0, ...) hides the structural error. *Prevent:* flag such clamps on stocks, and generate standard cases automatically.
8. **Software / ops:** Yes. With zero runners, nothing merges and the queue grows at arrival rate.
9. **Priority:** Useful: highest bug yield per unit of effort among the model tests. Surface it through the scorecard rather than as a page.
10. **Sources:** [Sterman 2000][sterman2000], [Barlas 1996][barlas1996].

### 28. Behavior reproduction and holdout: useful

1. **Aliases:** Backtest, out-of-sample test, partial-model test, family member test.
2. **Question / decision:** Does the model predict data it was not fitted to, or a similar system? Decide whether to trust forecasts.
3. **Reading:** Fit period, a marked cut, then forecast vs actual with bands. Good: actuals inside bands and the mode preserved. Bad: good in-sample and poor after the cut. For partial tests, drive one sector with real inputs and compare its output.
4. **Needs:** Enough history for a holdout that includes a regime change or intervention.
5. **Shape:** Two signals, plus a new ensemble for bands.
6. **Obtain:** Simulation + PromQL.
7. **Misuse / prevention:** A holdout from the same quiet regime proves little; a cut chosen after looking is leakage. *Prevent:* fix the cut before fitting, and say whether the holdout contains any change in regime.
8. **Software / ops:** Yes. Fit before a CI migration, then test whether the model predicts the queue after it.
9. **Priority:** Useful: the strongest empirical test available, limited by the data.
10. **Sources:** [Homer 2012][homer2012], [Oliva 2003][oliva2003], [Barlas 1996][barlas1996].

---

## F. Delays and aging

### 29. Delay profile: must-have

1. **Aliases:** Residence-time distribution, transit-time distribution, distributed lag, impulse response.
2. **Question / decision:** How long is the delay, what shape is it, and is it material or information? Decide the delay structure and how aggressively a controller may react.
3. **Reading:** Plot the transit-time distribution with its fit. For a cascade of n first-order stages (mean τ), transit time is Erlang with CV = 1/√n, so **n ≈ 1/CV²** is a first guess at order. CV near 1: first-order, well mixed. Low CV: pipeline. CV above 1: a mixture, so split the population first. Separate material delays (conserve quantity) from information delays (perception, no conservation).
4. **Needs:** Item spans for material delays. Input and output series for information delays.
5. **Shape:** Distribution (with censoring, using item spans), or two signals for an estimated lag.
6. **Obtain:** SQL for material delays; PromQL + transform (cross-correlation or deconvolution) for information delays.
7. **Misuse / prevention:** Cross-correlation peaks are confounded by daily cycles and feedback; using only completed items understates delay; the mean delay changes with load. *Prevent:* remove seasonality first, include open items, show delay by load band, and label a lag as "consistent with", not causal.
8. **Software / ops:** Yes. Review wait is a mixture: most under an hour, with a long tail for items waiting on a specific person.
9. **Priority:** Must-have: delay is what makes these systems hard, and the wrong order changes the model's behavior.
10. **Sources:** [Sterman 2000][sterman2000], [Vensim delays][vensimdelay], [iseesystems delay builtins][iseedelay].

### 30. Aging chain and cohort chart: useful

1. **Aliases:** Cohort chart, vintage chart, age-band stacked area, coflow.
2. **Question / decision:** How old is what is in this stock, and are older cohorts leaving? Decide whether to change service order or clear old work.
3. **Reading:** Stacked age bands over time, or retention by start cohort. Good: age bands stable. Bad: the oldest band keeps thickening, meaning work is being starved behind newer work.
4. **Needs:** Item spans with start times, or a model with an explicit aging chain.
5. **Shape:** New: item spans, aggregated to time series by band.
6. **Obtain:** SQL. Simulation for a modeled chain.
7. **Misuse / prevention:** Recent cohorts are incomplete and look better (right-censoring). *Prevent:* shade incomplete cohorts and never compare them directly with mature ones.
8. **Software / ops:** Yes. Tech-debt tickets older than 90 days grow while new items are served first.
9. **Priority:** Useful: the stock-level view of what aging WIP shows per item.
10. **Sources:** [Sterman 2000][sterman2000], [Hines, Molecules][hines].

---

## G. Operations flow

### 31. Cumulative flow diagram: must-have

1. **Aliases:** CFD, N-curves (queueing and traffic), arrival-departure curves.
2. **Question / decision:** Is work entering faster than leaving, and in which stage does it pile up? Decide where to limit WIP or add capacity.
3. **Reading:** Slope is rate. Vertical band height is WIP in that stage. Parallel bands mean stable flow; a **widening band is a growing queue**; a flat top line means nothing is finishing. The horizontal distance is an individual item's time **only under FIFO**. The *area* between curves is total item-time under any discipline, which is why Little's law survives reordering.
4. **Needs:** Timestamped state transitions with an ordered workflow.
5. **Shape:** Time series (cumulative per state), derived from new item spans.
6. **Obtain:** SQL. PromQL over per-state entry counters gives an approximation only.
7. **Misuse / prevention:** Backward moves, deleted items and re-entry break monotonic curves. Stacked areas make upper bands hard to read. Reading horizontal distance as cycle time under priority scheduling is wrong. *Prevent:* count re-entries explicitly, show a band-width panel, and state the queue discipline before offering a horizontal readout.
8. **Software / ops:** Yes. The "awaiting review" band widens while "in build" stays constant, so review is the constraint.
9. **Priority:** Must-have: the most information-dense view of a stock-flow chain.
10. **Sources:** [Vacanti 2015/2025][vacanti], [Reinertsen 2009][reinertsen], [MIT cumulative diagrams][mitcum].

### 32. Little's law check: must-have

1. **Aliases:** Flow balance, L = λW.
2. **Question / decision:** Do WIP, rate and time agree? Are the measurements consistent, and what would cutting WIP do?
3. **Reading:** Compute exact form over [0, T]: L = A/T, λ = S(T)/T, W = A/S(T), where A is the area under WIP and S(T) counts items present at the start plus arrivals. This **holds exactly** and is a data check. Then compare with the naive form (completed-item mean cycle time × throughput). A large gap means the system is not in balance or that aged work is missing from the sample.
4. **Needs:** Item spans, or a WIP series plus arrival count and starting WIP.
5. **Shape:** Dimensions to measures (L, λ, W, gap), per window; time series if rolled.
6. **Obtain:** SQL for exact. PromQL + transform: `avg_over_time(wip[w])` gives L.
7. **Misuse / prevention:** Using it to *forecast* an individual item; assuming cutting WIP automatically cuts time (true only if throughput holds); treating the law as requiring stationarity. Vacanti's assumptions (arrivals ≈ departures, all started work finishes, stable age) govern the approximation with completed-item times. *Prevent:* show both forms, name which assumption fails, and refuse to give a per-item forecast from a mean.
8. **Software / ops:** Yes. Average WIP 40 at 10 items/day implies 4 days in system. If reported cycle time is 2 days, look for old open items missing from that statistic, or for arrivals outrunning departures.
9. **Priority:** Must-have: a free consistency check across three core metrics.
10. **Sources:** [Little 2011][little2011], [Vacanti 2015/2025][vacanti].

### 33. Aging WIP chart: must-have

1. **Aliases:** Work item age chart, aging work in progress.
2. **Question / decision:** Which open items are at risk right now? Decide what to unblock today.
3. **Reading:** One dot per open item, x = stage, y = current age, with percentile lines from historical times *to leave that stage or finish*. Good: dots low and moving right. Bad: items above the 85th percentile, particularly in early stages, where they have most of the process still ahead.
4. **Needs:** Open item spans, plus history for the percentile lines.
5. **Shape:** New: item spans, displayed as points.
6. **Obtain:** SQL.
7. **Misuse / prevention:** Percentiles computed from completed-only data are too low; mixing item classes makes lines meaningless; encouraging people to close old items to tidy the chart. *Prevent:* use censoring-aware percentiles, split by class when n permits, show n, and mark items closed without completion.
8. **Software / ops:** Yes. A PR open nine days in "awaiting CI" when 85% clear that stage in four hours.
9. **Priority:** Must-have: the single most actionable daily chart, and it directly answers "why isn't this done?"
10. **Sources:** [Vacanti 2015/2025][vacanti], [Kanban Guide][kanbanguide].

### 34. Cycle-time scatterplot: useful

1. **Aliases:** Lead-time scatterplot, control chart (Jira's misnomer).
2. **Question / decision:** How long does work take, and is predictability changing? Decide what service expectation to quote.
3. **Reading:** One dot per finished item by finish date, percentile lines. Good: a stable band. Bad: rising upper percentiles, clusters (distinct work types), gaps followed by batches.
4. **Needs:** Completed items with start and finish.
5. **Shape:** Points.
6. **Obtain:** SQL.
7. **Misuse / prevention:** It omits open items, so it looks best when things are worst; means and ±σ are wrong for skewed data. Grouped by *start* date, recent cohorts are biased short. *Prevent:* overlay open items at current age as hollow markers, use percentiles, never σ limits.
8. **Software / ops:** Yes. Build-and-merge times split into two clusters, revealing a cache-miss path.
9. **Priority:** Useful: familiar and good for spotting clusters, but the survival curve is what should supply the numbers.
10. **Sources:** [Vacanti 2015/2025][vacanti].

### 35. Survival curve for work items: must-have

*Added; not in the brief.*

1. **Aliases:** Kaplan-Meier curve, time-to-completion curve.
2. **Question / decision:** What is the probability an item is still open after t, counting open items correctly? Decide service levels and detect stuck populations.
3. **Reading:** Falling step curve with confidence band. Median and p85 are read off directly. Good: steep, then low. Bad: a long plateau, meaning a population that effectively never finishes. If the curve never falls below 15%, **p85 is undefined, and the tool should say so.**
4. **Needs:** Duration and completed-or-open flag per item. Abandoned items are a competing outcome, not censoring.
5. **Shape:** New: item spans, output as a distribution with censoring.
6. **Obtain:** SQL + named transform.
7. **Misuse / prevention:** KM assumes censoring is independent of outcome. Treating cancellations as censored is wrong because they often are the stuck items. *Prevent:* model cancelled as a competing risk, show the at-risk count, and cut off the curve when at-risk n is small.
8. **Software / ops:** Yes. Median incident time-to-resolve stays flat while the share still open after 7 days doubles.
9. **Priority:** Must-have: it fixes the main statistical bias across every flow chart.
10. **Sources:** [Kaplan and Meier 1958][km1958]. *(Application to flow metrics is my inference; I found no standard flow reference for it.)*

### 36. Throughput run chart and process behavior chart: useful

1. **Aliases:** Run chart; XmR, individuals chart, Shewhart chart.
2. **Question / decision:** Did the rate really change, or is this noise? Decide whether to investigate or leave it alone.
3. **Reading:** Run chart: median plus run and crossing signals. XmR: limits at mean ± 2.66 × average moving range; the moving-range upper limit is 3.268 × average. Good: stable within limits. Bad: a point outside the limits or a sustained run on one side, meaning a real change.
4. **Needs:** A regular count series, 20+ baseline points preferred, intervention markers.
5. **Shape:** Time series.
6. **Obtain:** PromQL + transform (limits and rules).
7. **Misuse / prevention:** Low counts with many zeros, strong weekly seasonality and autocorrelation all distort limits. Applying many rules raises false alarms. Throughput target pressure produces gaming. *Prevent:* compare like days, default to few rules, use median-based run rules on low counts, and recompute limits only at declared changes.
8. **Software / ops:** Yes. Merges/day after a CI change: is the drop outside routine variation?
9. **Priority:** Useful: stops people from reacting to noise; best as an overlay on the time-series chart rather than a separate chart.
10. **Sources:** [Wheeler 2000][wheeler], [Nelson 1984][nelson1984], [Anhøj and Olesen 2014][anhoj2014].

### 37. Throughput Monte Carlo forecast: useful

1. **Aliases:** "When will it be done?", how-many/when forecast, burn-up forecast.
2. **Question / decision:** When will these N items finish, or how many finish by a date? Decide what commitment to make.
3. **Reading:** Distribution of finish dates with p50, p85, p95. Good: a tight range. Bad: a wide range, which is the honest answer to a bad commitment.
4. **Needs:** Recent throughput samples, remaining count, and an estimate of scope growth.
5. **Shape:** Distribution; internally a new ensemble (resampled, no model).
6. **Obtain:** SQL + named transform. No SD model needed.
7. **Misuse / prevention:** It assumes the future resembles the sample and that the item mix holds. Ignoring scope growth and rework gives systematically early dates (see the 90% syndrome). Daily resampling breaks autocorrelation. *Prevent:* show the sample window, require a growth assumption, block-resample, and refuse when throughput shows a recent shift.
8. **Software / ops:** Yes. 60 tickets left in a migration; p85 finish date given observed weekly merges and discovered work.
9. **Priority:** Useful: high stakeholder value and simple, but it should not be mistaken for a causal forecast.
10. **Sources:** [Vacanti 2015/2025][vacanti], [Ford and Sterman 2003][ninety].

### 38. Operating curve: useful

*Added; not in the brief.*

1. **Aliases:** Queueing curve, latency-utilization curve, VUT curve, Kingman curve.
2. **Question / decision:** How close to the knee are we, and what does more utilization cost in wait? Decide capacity and WIP caps.
3. **Reading:** Wait against utilization. Kingman's approximation: W_q ≈ (ρ/(1−ρ)) × ((c_a² + c_s²)/2) × τ. Wait grows nonlinearly with ρ and proportionally with variability. Good: operating left of the knee. Bad: on the steep part, where a small demand rise causes a large wait.
4. **Needs:** Utilization, wait, arrival and service variability per window, across a range of load.
5. **Shape:** Points; transfer function from a model for the fitted curve.
6. **Obtain:** PromQL + transform.
7. **Misuse / prevention:** Kingman is a single-server heavy-traffic approximation; multi-server pools and non-renewal arrivals differ. The "85% rule" is folklore, because the knee depends on variability. Windows mix regimes. *Prevent:* plot observed points with fit, name the approximation, and never publish a universal threshold.
8. **Software / ops:** Yes. CI runners at 92% with bursty arrivals, showing why adding 10% capacity cuts wait far more than 10%.
9. **Priority:** Useful: the clearest argument against maximizing utilization.
10. **Sources:** [Kingman 1961][kingman1961], [Hopp and Spearman][factoryphysics], [Reinertsen 2009][reinertsen].

### 39. Value stream map: useful

1. **Aliases:** VSM, material and information flow map; flow-efficiency breakdown.
2. **Question / decision:** Across the end-to-end process, where is the time spent waiting rather than working? Decide which handoff or stage to redesign.
3. **Reading:** Stages with process time, wait time and percent complete-and-accurate, with a timeline underneath. Bad: wait far greater than touch time, many handoffs, low first-pass yield.
4. **Needs:** Stage durations, handoffs, rework rates. **Touch time is usually not observable from events**: "in progress" does not mean someone is working.
5. **Shape:** Dimensions to measures (stage to wait, active, yield), plus structure.
6. **Obtain:** SQL + Structure. Touch time needs instrumentation or sampling.
7. **Misuse / prevention:** Reporting flow efficiency from status timestamps overstates it. Using averages hides the tail. A static map goes stale. *Prevent:* label touch time as measured or estimated, show p50 and p85, and generate the map from events so it stays current.
8. **Software / ops:** Yes. Commit to deploy is 3 days, of which about 40 minutes is compute.
9. **Priority:** Useful: strong for finding the constraint, provided wait and touch are not faked.
10. **Sources:** [Rother and Shook][rother], [Reinertsen 2009][reinertsen].

### 40. Rework cycle chart: useful

*Added; not in the brief.*

1. **Aliases:** Rework loop, first-pass yield, 90% syndrome chart, undiscovered rework.
2. **Question / decision:** How much of the apparent progress will come back? Decide whether reported "percent done" can be believed.
3. **Reading:** Reported progress vs true completion, with rework discovered over time. Bad: progress races to about 90%, then stalls as latent defects surface.
4. **Needs:** Reopen and failure events, defect discovery time. Undiscovered rework is a **hidden stock**, inferred only through a model.
5. **Shape:** Time series; model-based estimate from new ensemble.
6. **Obtain:** SQL for observed; Simulation for the hidden stock.
7. **Misuse / prevention:** Presenting the estimated hidden stock as a measurement. *Prevent:* draw it as inferred, with a band.
8. **Software / ops:** Yes. Merged work reverted or reopened within 14 days; a project stuck at "almost done".
9. **Priority:** Useful: rework is a major reason software plans fail, and standard flow charts cannot see it.
10. **Sources:** [Ford and Sterman 1998][fordsterman1998], [Ford and Sterman 2003][ninety], [Abdel-Hamid 1984][ahm].

### 41. Sankey and flow map: niche

1. **Aliases:** Sankey diagram, routing flow, alluvial (over time).
2. **Question / decision:** Over a period, where does work go, and what share takes each route? Decide which route to remove.
3. **Reading:** Width is quantity. Good: inputs equal outputs at each node. Bad: large rework or abandonment branches.
4. **Needs:** Edge totals (from, to, count) over a fixed window, conserved at each node.
5. **Shape:** Dimensions to measures (two dimensions, one measure).
6. **Obtain:** SQL.
7. **Misuse / prevention:** **I found no evidence that Sankeys are standard in SD practice**; their home is energy and material accounting. They erase time and accumulation and draw feedback poorly, so a rework loop looks like a side branch. *Prevent:* show the imbalance at each node as stock change, and do not offer it as a model view.
8. **Software / ops:** Partly. Share of tickets routed to triage, auto-closed, escalated or reworked.
9. **Priority:** Niche: an attractive summary that hides exactly what SD exists to show.
10. **Sources:** [Schmidt 2008][schmidt2008].

---

## H. Learning and communication

### 42. Flight simulator: niche

1. **Aliases:** Management flight simulator, microworld, Beer Game style simulation.
2. **Question / decision:** Can a person learn to manage this system by trying decisions in compressed time? Supports training rather than a specific decision.
3. **Reading:** Learner sets a policy each period, then sees outcomes and debrief. Good: learner's mental model changes and transfers. Bad: gaming the score.
4. **Needs:** A validated model, decision controls, scoring, debrief.
5. **Shape:** New: ensemble, interactive.
6. **Obtain:** Simulation.
7. **Misuse / prevention:** Learning from an unvalidated model teaches wrong lessons with conviction. Evidence of effectiveness is thin: McCormack and Ford (1998, SD conference) say knowledge of how to build effective ones is limited. *Prevent:* gate on the test scorecard.
8. **Software / ops:** Partly. An incident-load drill is plausible, but it is a product of its own.
9. **Priority:** Niche: costly to build; the policy comparison gives most of the value.
10. **Sources:** [Sterman 1989][sterman1989], [Sterman 1994][sterman1994], [DiBello 2006][mfs].

### 43. Stock-and-flow dashboard: useful

1. **Aliases:** Control panel, management cockpit, flow dashboard.
2. **Question / decision:** What is the state of the system, and does anything need action? Supports the daily operating review.
3. **Reading:** Pair each stock with its inflow, outflow, goal and data confidence. Good: answers "accumulating or draining, and why". Bad: disconnected KPI tiles with green arrows.
4. **Needs:** The charts above, a structural grouping, and goals.
5. **Shape:** Composite of time series and dimensions to measures, laid out by structure graph.
6. **Obtain:** PromQL and SQL, arranged by Structure.
7. **Misuse / prevention:** Showing flows without computed accumulation invites the stock-flow failure. Period-over-period arrows amplify noise. *Prevent:* always show the computed net change, apply process-behavior limits to indicators, and show failed reconciliation on the tile.
8. **Software / ops:** Yes. Merge system panel: queue, arrivals, merges, failure rate, wait vs goal.
9. **Priority:** Useful: the delivery surface for the must-haves rather than a separate analysis.
10. **Sources:** [Cronin et al. 2009][cronin2009], [Booth Sweeney and Sterman 2000][bathtub].

---

## Left out on purpose

- **Burndown chart.** A worse burn-up: it hides scope change. Use entry 37 or 40.
- **Velocity chart.** Story points are not a stock or a flow, and the metric is easily gamed.
- **Iceberg model, connection circles.** Facilitation aids, not data charts.
- **Spider/radar for model quality.** Encourages the single-score misuse of entry 26.
- **Cost-of-delay / CD3 charts.** Good sequencing logic from Reinertsen, but it needs economic inputs that the observed data does not contain. Revisit if ergostat starts recommending order of work.
- **Separate charts for each Sterman test.** Keep one scorecard that drills to evidence.

---

## Ranked top 15

Ranked by decisions enabled, how many other charts depend on it, and cost given ergostat's data.

| # | Chart | Why here | Needs a model? |
|---|---|---|---|
| 1 | Stock-flow reconciliation (10) | Gates trust in everything else | No |
| 2 | Behavior-over-time graph (8) | Base view, with annotations and limits | No |
| 3 | Stock-and-flow diagram, live (2) | The product's central object | Structure |
| 4 | Cumulative flow diagram (31) | Finds where work is piling up | No |
| 5 | Aging WIP (33) | Most actionable daily view | No |
| 6 | Goal-gap (11) | "Are we getting there?", exposes eroding goals | No |
| 7 | Little's law check (32) | Free consistency check | No |
| 8 | Survival curve (35) | Removes the completed-only bias | No |
| 9 | Delay profile (29) | Delay drives behavior and model order | No |
| 10 | Historical fit with Theil (24) | Gate for all simulated claims | Yes |
| 11 | Model test scorecard (26) | States what a model may be used for | Yes |
| 12 | Monte Carlo fan chart (18) | Honest simulated answers | Yes |
| 13 | Policy comparison (19) | The decision the product exists for | Yes |
| 14 | Causal loop diagram, derived (1) | Explanation in one view | Structure |
| 15 | Loops That Matter timeline (15) | Says which loop is in control now | Yes |

**Build order differs from rank:** the first nine need no simulation, so they deliver value even when no trustworthy model exists yet. Items 10-13 must ship together, because a fan chart or policy comparison without a fit and scorecard is unjustified confidence.

---

## Analytical workflows

Each step says what would send you elsewhere. Every workflow begins with reconciliation on the stocks involved.

### "Why isn't this done?" (one item)

1. **Aging WIP (33):** is it really abnormal for its stage?
2. **Item timeline** (from item spans): where did the time go, and how many re-entries?
3. **Delay profile (29):** is this stage's wait typical or in the tail?
4. **CFD (31):** is the stage congested for everyone? If yes, go to the next workflow. If no, the cause is specific to the item: a blocker, a dependency, or an owner.

**Output:** the current stage, time over expected, whether the cause is item-specific or systemic, and what would release it.

### "What is holding everything up?" (the system)

1. **Reconciliation (10):** can the data be trusted?
2. **CFD (31):** which band is widening?
3. **Operating curve (38):** is that stage capacity-bound, or is it starved or blocked?
4. **Value stream map (39):** is it waiting or working?
5. **Policy structure (4) and CLD (1):** which rule or loop keeps it there?
6. **LTM (15),** if a calibrated model exists: is that loop dominant now?

**Output:** a named constraint with evidence, and whether it is capacity, policy, or upstream batching. A widening band is not always the constraint: it can be a downstream block backing up, which is why step 3 exists.

### "Will this policy change help?"

1. **Reference mode (9):** state expected behavior *before* simulating.
2. **Scorecard (26) and fit (24):** is the model fit for this question? If not, stop and say so.
3. **Boundary (5):** does the policy act on something endogenous?
4. **Policy comparison (19):** paired runs over a long enough horizon. Check for worse-before-better.
5. **Fan chart (18) and screening (22):** does the benefit survive uncertainty, and which parameter could reverse it?
6. **Extreme conditions (27):** does the policy fail badly under stress?
7. **After shipping: BOT with process limits (36) and residuals (25):** record the prediction and judge it against what happens.

**Output:** expected effect with range, time to payoff, the assumption it depends on, and the observation that would prove it wrong.

### "Did something actually change?"

1. **Process behavior chart (36):** signal or noise?
2. **Reconciliation (10):** a real change, or a change in instrumentation?
3. **Annotated BOT (8):** what happened at that time?
4. **Survival curves before and after (35):** did the whole distribution move or only the tail?

### "When will it be done?"

1. **Reconciliation (10)** of the remaining scope.
2. **Throughput chart (36):** is the recent rate stable enough to sample?
3. **Rework (40):** how much scope will come back?
4. **Monte Carlo forecast (37):** report p50 and p85, not one date.
5. **Aging WIP (33):** is anything already at risk of breaking the forecast?

### "Why does this keep coming back?"

1. **BOT over a long window (8):** recurring pattern?
2. **Goal-gap (11):** is the goal drifting?
3. **CLD (1) with archetype candidates (14):** which structures could explain it?
4. **LTM (15):** does the suspected loop actually dominate in the model?
5. **Policy comparison (19):** symptomatic fix vs fundamental fix over a long horizon.

### "Can I trust this model?"

1. Reconciliation (10) → 2. Extreme conditions (27) → 3. Fit and Theil (24) → 4. Residuals (25) → 5. Parameter identifiability (23) → 6. Holdout (28) → 7. Scorecard (26), scoped to the question.

---

## Shared infrastructure

In order of leverage:

1. **Item-span store.** One row per item per state, open items included, with re-entry and terminal reason (completed, cancelled, abandoned). Feeds at least 9 charts. Censoring must be a first-class field.
2. **Conservation ledger.** For each stock: its declared flows, the residual, the tolerance and the method. Other charts read its status and lower their confidence.
3. **Model graph API.** Typed nodes, signed edges, units, delays, loops, sectors, provenance (measured, fitted, declared, assumed). Every structural chart is a query on it.
4. **Ensemble runner.** Seeded and reproducible, with parameter draws stored, common random numbers across scenarios, run provenance, a cost cap and cached results. Serves fan, policy, screening, tornado, extremes and holdout.
5. **Claim labels, enforced at render time.** Each chart states what its result is: *observed*, *derived*, *fitted*, *simulated* or *hypothesis*. Model-derived charts carry the model version and scorecard state.
6. **Refusal and warning gate.** A shared set of preconditions with stated reasons: too few points, window shorter than the delay, failed balance, unidentified parameter, extrapolation, censoring too heavy.
7. **Time alignment layer.** Common step, counter-reset handling, extrapolation awareness, and gap marking across PromQL and SQL sources, so that two-signal charts compare like with like.
8. **Named statistical transforms.** Rolling and exact Little's law, Kaplan-Meier with competing risks, XmR and run rules, Theil decomposition, lag estimation, block bootstrap, and Erlang fit. Each should be tested once and reused.
9. **Annotation and intervention log.** Deployments, config and policy changes, goal changes and incidents, shown on every time axis. Needed for attribution and for holdout cuts.
10. **Versioned goals and reference modes.** With authorship and timestamps, so goal drift is detectable and reference modes cannot be quietly fitted to the output.

---

## Sources

Evidence labels are defined at the top.

**System dynamics: books**

- [Sterman, *Business Dynamics*][sterman2000] (2000) **[book]**
- [Forrester, *Industrial Dynamics*][forrester1961] (1961) **[book]**
- [Meadows, *Thinking in Systems*][meadows2008] (2008) **[book]**
- [Senge, *The Fifth Discipline*][senge1990] (1990) **[book]**
- [Ford, *Modeling the Environment*][ford2009], 2nd ed. (2009) **[book]**
- [Morecroft, *Strategic Modelling and Business Dynamics*][morecroft2007] (2007) **[book]**

[sterman2000]: https://search.worldcat.org/search?q=Sterman+Business+Dynamics "Sterman, Business Dynamics"
[forrester1961]: https://search.worldcat.org/search?q=Forrester+Industrial+Dynamics+1961 "Forrester, Industrial Dynamics"
[meadows2008]: https://www.chelseagreen.com/product/thinking-in-systems/ "Meadows, Thinking in Systems"
[senge1990]: https://search.worldcat.org/search?q=Senge+The+Fifth+Discipline "Senge, The Fifth Discipline"
[ford2009]: https://search.worldcat.org/search?q=Ford+Modeling+the+Environment "Ford, Modeling the Environment"
[morecroft2007]: https://www.oreilly.com/library/view/strategic-modelling-and/9780470012864/ "Morecroft, Strategic Modelling and Business Dynamics"

**System dynamics: papers and documentation**

- [Richardson 1986][rich1986], *Problems with causal-loop diagrams*, SDR 2 **[record]**
- [Richardson 1997][rich1997], *Problems in causal loop diagrams revisited*, SDR 13 **[record]**
- [Morecroft 1982][morecroft1982], *A critical review of diagraming tools for conceptualizing feedback system models*, Dynamica 8 **[record, via an unofficial scan]**
- [Forrester and Senge 1980][fs1980], *Tests for building confidence in SD models*, TIMS Studies 14 **[record, via secondary]**
- [Barlas 1996][barlas1996], *Formal aspects of model validity*, SDR 12 **[record]**
- [Sterman 1984][sterman1984], *Appropriate summary statistics*, Dynamica 10 **[record; formula checked against a [Theil proportions note][theilnote]]**
- [Oliva 2003][oliva2003], *Model calibration as a testing strategy*, EJOR 151 **[read abstract]**
- [Homer 2012][homer2012], *Partial-model testing*, SDR 28 (1983 paper reprinted) **[record]**
- [Struben, Sterman and Keith 2015][struben], in Rahmandad, Oliva and Osgood, *Analytical Methods for Dynamic Modelers* **[record]**
- [Rahmandad and Sterman 2012][rgsr], *Reporting guidelines*, SDR 28 **[record]**
- [SDM-Doc][sdmdoc] **[record]**
- [Schoenberg, Davidsen and Eberlein 2020][ltm], *Understanding model behavior using the Loops that Matter method*, SDR 36 **[record]**; [preprint][ltmarxiv] **[read]**
- [Eberlein and Schoenberg 2020][eberlein2020], *Finding the Loops that Matter* (arXiv) **[record]**
- [Mojtahedzadeh, Andersen and Richardson 2004][ppm], SDR 20 **[record]**; [conference version][ppm2003] **[read, excerpts]**
- [Oliva, *Eigenvalue elasticity analysis*][eea], chapter draft for Rahmandad et al. **[read, excerpts]**
- [Kampmann 2012][kampmann2012], *Feedback loop gains and system behavior*, SDR 28 **[record]**
- [Kampmann and Oliva 2006][ko2006], SDR 22 **[record]**
- [Gonçalves 2009][goncalves2009], SDR 25 **[record]**
- [Ford and Flynn 2005][fordflynn2005], *Statistical screening*, SDR 21 **[record]**
- [Taylor, Ford and Ford 2010][taylor2010], WSC **[record]**
- [Arthur and Eberlein 1996][ae1996], *Sensitivity simulation* **[record]**
- [Booth Sweeney and Sterman 2000][bathtub], *Bathtub dynamics*, SDR 16 **[record]**
- [Cronin, Gonzalez and Sterman 2009][cronin2009], OBHDP 108 **[record]**
- [Sterman 1989][sterman1989], *Misperceptions of feedback*, Management Science 35 **[record]**
- [Sterman 1994][sterman1994], *Learning in and about complex systems* **[record]**
- [DiBello 2006][mfs], *Developing effective management flight simulators*, MIT thesis **[record]**. McCormack and Ford (1998), *Impacts of Dynamic Decision Making and Policy Development Modes on the Causal Understanding of Management Flight Simulators*, SD conference **[record via search; no stable link found]**
- [Kim and Anderson 1998, *Systems Archetype Basics*][archetypes]: the eight archetype names checked in the text **[read, excerpts]**
- [Repenning and Sterman 2001][rs2001], CMR 43 **[record]**
- [Repenning and Sterman 2002][rs2002], ASQ 47 **[record]**
- [Rudolph and Repenning 2002][rudolph2002], *Disaster dynamics*, ASQ 47 **[read, excerpts]**
- [Ford and Sterman 1998][fordsterman1998], SDR 14 **[record]**
- [Ford and Sterman 2003][ninety], *Overcoming the 90% syndrome*, CERA 11 **[read, excerpts]**
- [Abdel-Hamid 1984][ahm], MIT thesis behind *Software Project Dynamics* (Abdel-Hamid and Madnick) **[record]**
- [Hines, *Molecules of Structure*][hines] **[record]**
- [Vensim sensitivity][vensim], [Vensim delays][vensimdelay], [isee delay builtins][iseedelay], [Stella LTM][stellaltm] **[vendor docs]**

**Flow, queueing and statistics**

- [Little 2011][little2011], *Little's Law as viewed on its 50th anniversary*, Operations Research 59 **[read: LL.1, LL.2 and proofs]**
- [Vacanti, *Actionable Agile Metrics for Predictability*][vacanti] **[book; assumptions confirmed through secondary sources]**
- [Reinertsen 2009, *The Principles of Product Development Flow*][reinertsen] **[book]**
- [Kanban Guide][kanbanguide] **[record]**
- [MIT 1.041 cumulative diagrams lecture][mitcum] **[record]**
- [Kingman 1961][kingman1961] **[record]**
- [Hopp and Spearman, *Factory Physics*][factoryphysics] **[book]**
- [Rother and Shook, *Learning to See*][rother] **[book]**
- [Wheeler, *Understanding Variation*][wheeler] **[book]**
- [Nelson 1984][nelson1984] **[record]**
- [Anhøj and Olesen 2014][anhoj2014] **[record]**
- [Kaplan and Meier 1958][km1958] **[record]**
- [Morris 1991][morris1991] **[record]**
- [Saltelli et al. 2010][saltelli2010] **[record]**
- [Saltelli et al. 2019][saltelli2019] **[record]**
- [Howard 1988][howard1988] **[record]**
- [Britton, Fisher and Whitley 1998][fan], Bank of England **[record]**
- [Schmidt 2008][schmidt2008], *The Sankey diagram in energy and material flow management* **[record]**
- [Prometheus query functions][prom] **[read: `increase()`]**

[rich1986]: https://doi.org/10.1002/sdr.4260020207
[rich1997]: https://doi.org/10.1002/(SICI)1099-1727(199723)13:3%3C247::AID-SDR128%3E3.0.CO;2-9
[morecroft1982]: https://www.scribd.com/doc/76291019/5
[fs1980]: https://www.oreilly.com/library/view/strategic-modelling-and/9780470012864/9780470012864_tests_for_building_confidence_in_models.html
[barlas1996]: https://doi.org/10.1002/(SICI)1099-1727(199623)12:3%3C183::AID-SDR103%3E3.0.CO;2-4
[sterman1984]: https://archives.albany.edu/concern/daos/nk322z25d
[theilnote]: https://economicsnetwork.ac.uk/showcase/cook_theil
[oliva2003]: https://doi.org/10.1016/S0377-2217(02)00622-7
[homer2012]: https://doi.org/10.1002/sdr.1478
[struben]: https://mitmgmtfaculty.mit.edu/jsterman/parameterandconfidence
[rgsr]: https://doi.org/10.1002/sdr.1481
[sdmdoc]: https://proceedings.systemdynamics.org/2021/abstracts/1028.html
[ltm]: https://doi.org/10.1002/sdr.1658
[ltmarxiv]: https://arxiv.org/abs/1908.11434
[eberlein2020]: https://arxiv.org/abs/2006.08425
[ppm]: https://doi.org/10.1002/sdr.285
[ppm2003]: https://proceedings.systemdynamics.org/2003/proceed/PAPERS/W11.pdf
[eea]: https://people.tamu.edu/~roliva/research/sd/amdm/EEA%20in%20AMDM.pdf
[kampmann2012]: https://doi.org/10.1002/sdr.1483
[ko2006]: https://people.tamu.edu/~roliva/research/sd/leea
[goncalves2009]: https://doi.org/10.1002/sdr.414
[fordflynn2005]: https://doi.org/10.1002/sdr.322
[taylor2010]: https://www.informs-sim.org/wsc10papers/038.pdf
[ae1996]: https://archives.albany.edu/concern/daos/t722ht33w?locale=en
[bathtub]: https://doi.org/10.1002/sdr.198
[cronin2009]: https://doi.org/10.1016/j.obhdp.2008.03.003
[sterman1989]: https://doi.org/10.1287/mnsc.35.3.321
[sterman1994]: https://typeset.io/pdf/learning-in-and-about-complex-systems-59iuqj6a45.pdf
[mfs]: https://dspace.mit.edu/handle/1721.1/36775
[archetypes]: https://thesystemsthinker.com/wp-content/uploads/2016/03/Systems-Archetypes-Basics-WB002E.pdf
[rs2001]: https://cmr.berkeley.edu/2001/08/43-4-nobody-ever-gets-credit-for-fixing-problems-that-never-happened-creating-and-sustaining-process-improvement
[rs2002]: https://doi.org/10.2307/3094806
[rudolph2002]: https://doi.org/10.2307/3094889
[fordsterman1998]: https://doi.org/10.1002/(SICI)1099-1727(199821)14:1%3C31::AID-SDR141%3E3.0.CO;2-5
[ninety]: https://doi.org/10.1177/106329303038031
[ahm]: https://dspace.mit.edu/handle/1721.1/38235
[hines]: https://ocw.mit.edu/courses/15-875-applications-of-system-dynamics-spring-2004/854417cbe079d97707d06fbaafbc1d23_molecules.pdf
[vensim]: https://www.vensim.com/documentation/sensitivity.html
[vensimdelay]: https://vensim.com/documentation/mgu09_material_and_information_delays.html
[iseedelay]: https://www.iseesystems.com/resources/help/v3/Content/08-Reference/07-Builtins/Delay_builtins.htm
[stellaltm]: https://www.iseesystems.com/resources/help/v3/Content/05b%20-LoopsThatMatter/LoopDiscovery.htm
[little2011]: https://doi.org/10.1287/opre.1110.0940
[vacanti]: https://s3.amazonaws.com/samples.leanpub.com/aamfp-10th-sample.pdf
[reinertsen]: https://search.worldcat.org/search?q=Reinertsen+Principles+of+Product+Development+Flow
[kanbanguide]: https://kanbanguides.org/english/
[mitcum]: https://web.mit.edu/1.041/www/lectures/L3-cumulative-diagram-2026sp.pdf
[kingman1961]: https://doi.org/10.1017/S0305004100036094
[factoryphysics]: https://search.worldcat.org/search?q=Hopp+Spearman+Factory+Physics
[rother]: https://www.lean.org/store/book/learning-to-see/
[wheeler]: https://search.worldcat.org/search?q=Wheeler+Understanding+Variation
[nelson1984]: https://doi.org/10.1080/00224065.1984.11978921
[anhoj2014]: https://doi.org/10.1371/journal.pone.0113825
[km1958]: https://doi.org/10.1080/01621459.1958.10501452
[morris1991]: https://doi.org/10.1080/00401706.1991.10484804
[saltelli2010]: https://doi.org/10.1016/j.cpc.2009.09.018
[saltelli2019]: https://doi.org/10.1016/j.envsoft.2019.01.012
[howard1988]: https://doi.org/10.1287/mnsc.34.6.679
[fan]: https://www.bankofengland.co.uk/quarterly-bulletin/1998/q1/the-inflation-report-projections-understanding-the-fan-chart
[schmidt2008]: https://doi.org/10.1111/j.1530-9290.2008.00004.x
[prom]: https://prometheus.io/docs/prometheus/latest/querying/functions/
