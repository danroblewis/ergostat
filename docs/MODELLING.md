# Improving a model

A guide for someone new to system dynamics: how to tell that a model's structure is wrong, why
system dynamics says it is, and what to write in `ergostat.yaml` instead. Each guideline has the
same four parts: the **symptom** (what looks or behaves wrong), the **reason** (in system
dynamics' terms), the **fix** (in ergostat's YAML) and the **source**.

The words are system dynamics' own (Sterman's *Business Dynamics*): a **stock** keeps what
accumulates; a **flow** fills or drains a stock, at a rate per hour, through its **valve**; an
**auxiliary** is worked out at each moment from others and keeps nothing; a **connector** (a
`driven-by`, or what a block reads) carries information, never material, and carries it at once.
The format is `docs/SPEC.md`; the five structure checks below are what `ergostat check` reports.

## The tells

| What you see | What is usually missing | `ergostat check` says |
|---|---|---|
| A rate driven by another rate (`driven-by: +flow.x` on a flow) | a **stock** between them: the cause accumulates, and the effect follows what accumulated | `rate-driven-by-rate` |
| A stock that only fills (inflows, no outflow) | its **outflow**: what is in it leaves somehow | `stock-without-outflow` |
| An outflow that would keep running with its stock empty | the **stock** among the outflow's causes | `outflow-ignores-stock` |
| A decision that reacts to the true value the moment it changes | a **perceived** value: a stock that catches up with the true one, as people do | (not mechanical: read the decisions) |
| A link between two things counted in different units | a converting **auxiliary** (so many of one per one of the other) | `units-mismatch` |
| A cause far from its effect in time (a change that breaks things days later) | a **delay**: one stock or more holding what is on its way | `rate-driven-by-rate` when it is drawn rate to rate |
| An auxiliary that changes for no reason the model gives | its **causes**, or the word that it comes from outside (`exogenous: true`) | `auxiliary-without-causes` |
| A stock whose readings move more than its flows explain | a **flow** the model does not have (or a sensor reading wrongly) | the Model page's residuals |
| A replay that runs high or low (U_M), or swings too much or too little (U_S) | a wrong constant or gain; a missing flow or delay | the Model page (`ergostat fit`) |

## 1. A rate driven by a rate: a missing stock

**Symptom.** A flow is `driven-by` another flow. On the diagram a connector runs from one valve
to another. The model then says, for instance, that alerts fire *as* ramps go ahead.

**Reason.** In system dynamics a connector is instantaneous: the effect at its head depends on
the cause at its tail *now*. A rate following a rate says the alert rate this hour depends on
the ramp rate this hour. When the effect comes later (a flag ramped without review sits in
production and may break its service hours later, or never), something accumulates in between:
the ramps live and not yet broken. That something is a stock, and the delay is the time things
spend in it. Forrester's rule for rate equations is that a rate depends on levels (stocks), not on
other rates: a rate cannot be observed at an instant, only what it has accumulated.

**Fix.** Give what the first flow moves a stock to go into, drain that stock by the flows that
end its stay, and drive the effect from the stock (or from the flow that ends the stay). This is
what `examples/the-job` does with unreviewed ramps:

```yaml
stocks:
  unreviewed-ramps-live:
    unit: ramps
    sensor: {items: ramp, state: went-ahead}
flows:
  ramps-went-ahead:                     # was: alerts-fired driven-by +flow.ramps-went-ahead
    from: ramps-briefed
    to: unreviewed-ramps-live
  ramps-broke:
    from: unreviewed-ramps-live
    driven-by: +stock.unreviewed-ramps-live    # each one live may break: the more live, the more break
  ramps-proved-fine:
    from: unreviewed-ramps-live
    driven-by: +stock.unreviewed-ramps-live
  alerts-fired:
    to: alerts-to-draft
    driven-by: +stock.unreviewed-ramps-live
```

Measure the new stock honestly: if its items have no state for it, give them one (here the world
says when a ramp that went ahead broke or proved fine: `ramp.broke`, `ramp.proved-fine`). When what
you need to count is in the items' fields rather than their states, check how those fields fold:
each event's data replaces a field unless the kind says otherwise (`fold: {incidents: sum}`,
`{comments: append}`; SPEC §5a), and `ergostat item ID --history FIELD` shows every change and the
event that made it, so a count built on a field that was overwritten when it should have been
added to is found there.

**When it really is immediate**, say so on the link, written out, and the finding is answered:
a release fixes what it fixes as it goes live; the next document is needed the moment the last is
approved.

```yaml
    driven-by:
      - cause: +flow.docs-approved
        instant: true                   # nothing between: the next document is needed at once
```

**Source.** Sterman, *Business Dynamics* (2000), ch. 6 (stocks and flows: only flows change
stocks, and stocks are where delays and memory live), ch. 11 (delays: a material delay is a stock
in transit); Forrester, *Industrial Dynamics* (1961) and *Principles of Systems* (1968), on rate
equations depending on levels.

## 2. An inflow without an outflow: a missing outflow

**Symptom.** A stock has flows that fill it and none that drains it. Run long enough, the model
says it can only grow; the real one does not (tickets get closed, files get deleted, people
leave).

**Reason.** A stock changes only through its flows. If the real stock falls and the model has no
outflow, the fall is unexplained: the model is wrong about where things go. Most real stocks have
an outflow, often one nobody thinks of because it is slow (expiry, attrition, forgetting).

**Fix.** Add the outflow, and say what drives it (usually the stock itself: an outflow takes from
what is there):

```yaml
flows:
  tickets-closed:
    from: open-tickets
    driven-by: +stock.open-tickets
```

A **running total** that by its nature never drains (money spent so far, hypotheses kept so far)
is a stock without an outflow on purpose; say so and the finding goes:

```yaml
stocks:
  ai-spend:
    unit: USD
    cumulative: true
```

**Source.** Sterman ch. 6 (the conservation of material in stock and flow networks) and ch. 21
(structure assessment: does the model conserve what it moves?).

## 3. An outflow that ignores its stock: extreme conditions

**Symptom.** An outflow is driven by something other than its stock (fixes driven by deploys
only). Imagine the stock empty: the model still drains it, below zero.

**Reason.** Sterman's extreme-conditions test asks what a model does when an input is taken to an
extreme: with nothing to fix, nothing is fixed. An outflow must fall to zero as its stock does; the
simplest formulation is first-order, outflow = stock / time it stays (or a share of what is there).

**Fix.** Add the stock to what drives the outflow:

```yaml
flows:
  fixes:
    from: bugs-live
    driven-by:
      - +stock.bugs-live                # it takes a share of what is there
      - {cause: +flow.deployed, instant: true}
```

**Source.** Sterman ch. 21 (extreme conditions tests) and ch. 8 (first-order systems: an outflow
proportional to its stock).

## 4. A decision on the true value: a missing perceived stock

**Symptom.** A decision (a block, or a market in a simulation) reacts to the true state the moment
it changes: customers leave the instant a bug ships, a manager staffs up the instant the backlog
grows. Real decision makers see reports, averages and rumours, late.

**Reason.** Decisions can use only the information actually available to the decision maker
(Sterman's "Baker criterion"), and people form what they believe by adjusting it toward what they
see, gradually: an information delay. The perceived value is a stock (it keeps its value until new
evidence moves it). Leaving it out makes the model react faster, and oscillate less, than the
real system.

**Fix.** In ergostat a decision already reads a sensor, which is a measurement and not the truth,
so this is only a fix where the decision maker sees something slower than the sensor: a weekly
report, a reputation, a moving average. Make that a stock, filled by a two-way flow that closes
the gap toward the true value, and let the decision read it:

```yaml
stocks:
  perceived-quality:
    unit: share
    sensor: {run: ./reputation.sh}      # what customers believe, as a survey or the reviews say
flows:
  perception-catching-up:
    to: perceived-quality
    two-way: true
    driven-by: [+auxiliary.share-answered-right, -stock.perceived-quality]   # the gap closes over time
```

**Source.** Sterman ch. 11 (information delays and the smoothing of perceptions) and ch. 13
(modelling decision making: the Baker criterion; ch. 15 on bounded rationality).

## 5. Units that do not agree: a missing auxiliary

**Symptom.** A link joins two things counted in different units, with nothing between to convert
one into the other: actions filed following postmortems held, operations broken following tickets
deployed.

**Reason.** Every equation must balance its units with parameters that mean something in the real
world. A rate that follows a rate of something else moves so many of its own units for each of the
other's: a **coflow**, and that ratio (actions per postmortem) is a quantity of its own, worth
naming, measuring and questioning. A missing ratio is often a missing idea: "two or three actions
per postmortem" is a habit someone could change.

**Fix.** Name the ratio as an auxiliary (exogenous while nothing in the model moves it), and drive
the flow from both:

```yaml
auxiliaries:
  actions-per-postmortem:
    unit: actions/outage
    exogenous: true
flows:
  actions-filed:
    to: actions-to-plan
    driven-by:
      - {cause: +flow.postmortems, instant: true}
      - +auxiliary.actions-per-postmortem
```

Or, for an outflow, drive it from the stock it drains: it then takes a share of what is there, in
its own unit (guideline 3). `check` compares counts (alerts, ramps, tickets) with any per-hour
taken off, and leaves shares, percentages and compound units (`KB/MP`) alone.

**Source.** Sterman ch. 21 (dimensional consistency: the units test is the first test of a model),
ch. 12 (coflows).

## 6. A cause far from its effect: a missing delay

**Symptom.** Something happens long after what caused it (a decision now shows in the numbers next
week), but the diagram draws them side by side. The model then responds at once where the real
system responds late, and the real system overshoots where the model settles.

**Reason.** Delays are everywhere in real systems, and they are what make feedback oscillate.
A material delay is a stock of what is on its way (orders shipped, not yet delivered); a long or
spread-out delay is several stocks in a row (an aging chain), each draining into the next.

**Fix.** Put the stock (or stocks) of what is in transit between cause and effect, each measured
where it can be: `outages-to-review` in `examples/the-job` holds the outages declared and waiting
for their postmortem, so the actions they leave come when the postmortem is held, not when the
outage is declared.

**Source.** Sterman ch. 11 (delays) and ch. 12 (aging chains); Forrester (1961) on delays in
industrial systems.

## 7. An auxiliary with no causes: the boundary

**Symptom.** An auxiliary nothing drives, nothing sets and not marked as coming from outside.

**Reason.** Sterman's boundary-adequacy test asks which quantities the model explains
(endogenous), which it takes as given (exogenous) and which it leaves out. An auxiliary with no
causes is neither explained nor declared as given: the model cannot say why it changes.

**Fix.** Name what it is worked out from (`driven-by: [+stock.x, ...]`), or say it comes from
outside (`exogenous: true`: the weather, a price, a constant the model does not move).

**Source.** Sterman ch. 21 (boundary adequacy), ch. 1–3 (endogenous explanation: the model's
boundary is a choice to be stated).

## 8. Two smaller ones

- **A stock no flow moves** (`stock-without-flows`): a quantity with no memory is an auxiliary;
  one with memory needs the flows that change it.
- **A link with no sign** (`unsigned-link`): every loop through it is of unknown polarity. Write
  the sign: `+` when the effect moves the same way as the cause, `-` the opposite way (Sterman ch. 5,
  link polarity).

## 9. Quiet is not absent: a part the record has not exercised

A flow that has not moved yet is not evidence that it does not exist. Points on a benchmark are
lost rarely (an outage), a queue of the owner's messages is empty until the owner writes, and a
record of a few hours may never exercise them. In Sterman's terms (ch. 21), the record has not
exercised that structure, so its rate cannot be identified from the data: a statement about
identifiability, not about the boundary. A modeller keeps declared structure with its stated
reason, and waits for, or makes, the record that tests it.

**What ergostat says.** `not-exercised`, a finding on the part (Check, `ergostat findings`, the
part's side panel): the span of record it covers, and why (it never moved; or it held one value, so
there is no variation to identify a parameter from), with the suggestion that a step test or a
planned disturbance would exercise it. Nothing proposes removing it, the calibration holds an
estimate of a parameter that acts only through it (inconclusive, not proposed), and the judge does
not pass a change to it on record that has not moved it. The finding clears the moment the part
moves.

**What may still be removed.** Only structure ergostat inferred that the record shows to be
redundant: a part (or a link) marked `inferred: ergostat.model-change/<id>`, which ergostat writes on
everything a model change adds, that explains nothing or carries exactly another part's information
over a long, varied record (a twin). The proposal says which and why, and waits for the owner:
removing structure is never written by the judge's policy. A declared part (no `inferred:`) is never
proposed for removal, described or not. The key stays when you accept or edit an inferred part; take
it away to make the part your own.

## Reading what `ergostat check` says

`check` refuses a model with errors (a reference that does not exist, units that disagree between
a flow and its stock) and reports findings, which are questions to answer, not failures. Each
names the part and its file and line, says what it found in plain words, and ends with the fix and
the YAML that writes it. Read them in this order:

1. **Structure** (`rate-driven-by-rate`, `stock-without-outflow`, `outflow-ignores-stock`,
   `units-mismatch`, `auxiliary-without-causes`, `stock-without-flows`): the model says something
   about how the world works that system dynamics says cannot be right. Fix these first: every
   loop drawn from a wrong structure is wrong too.
2. **Signs** (`unsigned-link`, `equation-sign`): the loops through an unsigned link are of unknown
   polarity, so the diagram cannot say which reinforce and which balance; a link whose equation
   moves its effect the other way from the sign drawn makes every loop through it wrong.
3. **Control** (`missing-feedback`, `unjudgeable-goal`, `acting-on-its-own`, `competing-commands`,
   `own-disturbance`, `unguarded-limit`): what is wanted and whether anything serves it.

A finding may be answered without changing the structure, when the model is right and the check
cannot know it: `instant: true` on a link that really is immediate, `cumulative: true` on a
running total, `exogenous: true` on an input from outside. Write the reason beside it as a
comment, so the next reader can disagree.

## Reading the Model page: the model against the record

The Model page (and `ergostat fit`) runs the model over the last day of record at most, whatever the
window above it shows, and reads it the way the record was made: a stock at its reading's moment,
a counted flow by what it moved in each bucket, a rate a sensor averages over ten minutes by the
model's own ten-minute average. It shows three things, each as itself:

- **Model fit**: the stocks an equation moves, replayed (every stock integrated from its flows).
  These alone make the total and its history across versions.
- **Equations, inputs as measured**: each equation against its own readings with every input as
  measured, no stock integrated. This is Homer's partial-model test, the sharpest test of one
  equation; **Equations, replayed** is the same equation on inputs the replay has integrated, which
  have drifted when another equation is wrong. Read the first to judge the equation, the second to
  see what it does in the model. A flow measured only by its stock's `changes:` is judged by its
  stock's replay instead (its own readings are the stock's, differenced).
- **Accounting**: stocks moved only by measured flows. They test no equation: their replay is the
  sum of what was measured, so an error there is a measurement's, or a flow the model lacks (read
  the residuals), never a sign that an equation is wrong.

**R²** is how much of the measured variation the replay moves with; **MAPE** how far off it is, as
a share of what was measured (where readings reach 0, the error as a share of their mean or range:
a percentage of almost nothing says nothing). **Theil's statistics** say what kind of error it is
(Sterman ch. 21), and the page says it in words when the error is large:

- **U_M large (bias)**: the replay runs high or low throughout. A constant is wrong (a base rate,
  a share), or an inflow or outflow is missing (and the residual says which).
- **U_S large (unequal variation)**: the replay swings more, or less, than the record. A gain is
  wrong (a coefficient too large or small), or a delay is missing that would smooth it.
- **U_C large (unequal covariation)**: the error is point-by-point, at other moments: noise, or a
  timing difference. This is where a good fit's error should be; a model need not follow the noise.

A high R² beside a large U_M is a model that moves at the right moments by the wrong amount. A
series with fewer than ten points, or a record shorter than three of its slowest time constant,
says "too little record" instead of numbers: a fit of a few points, or of a record the model has
not had time to answer, says nothing. A replay that blew up (a value clamped) is marked not valid
and has no total.

## Reading the residuals: evidence of what is missing

A stock's **residual** is the change its readings show minus the change its known flows explain.
The model's flows say how much should have come in and gone out; the sensor says what happened;
the difference is what the model does not explain (`ergostat residual`, and the Model page's residuals).

- **A persistent positive residual** (the stock rises more than its inflows explain): an inflow is
  missing, or an outflow is overestimated. Ask what else brings things in.
- **A persistent negative residual**: an outflow is missing (guideline 2), often a slow one.
- **"would have to run backwards to explain it"**: a flow the model estimates from the residual
  would need the wrong sign: the structure, not the size, is wrong.
- **A residual that comes and goes with something else** (with deploys, with the time of day):
  that something is a cause the model leaves out, a candidate `driven-by`.
- **A residual that jumps once**: a sensor that read wrongly, more often than a missing flow; set
  the reading aside (`ergostat sensor NAME --forget-above V`) rather than add a flow for it.

A residual is evidence, never noise to be ignored: either the model is missing a flow or a stock,
or a measurement is wrong, and both are worth knowing.

## Improving from data: system identification

System identification is inferring a model from measured inputs and outputs. Given a structure,
it can estimate its sizes: how much of a stock drains per hour (a time constant), how long a delay
is (from when a cause's change shows in its effect, by cross-correlation), how strongly a cause
drives a flow, and how sure each estimate is. With care it can also propose structure: which
candidate causes explain a flow at all (sparse regression over many candidates), whether a delay
is one stock or several (the shape of the response), whether a residual follows something
measured. Its limits are as real: it needs the inputs to have varied (a cause that never moved
cannot be measured, and a flow that never moved says nothing about whether it exists: §9), it finds
correlation and not cause, it is biased inside a closed loop (the
controller makes the input follow the output), and different structures can fit the same data
equally well. The model's structure is still a claim people make and data tests.

**What ergostat does.** Equations and parameters are written in the model (`docs/SPEC.md` §7b):
`equation: base + k * stock.unreviewed-ramps-live`, each parameter with its value and unit, and
`estimate: true` on the ones to fit. ergostat replays the model over the record (each stock
integrated from its flows, each equation worked out, everything else as measured), and says how
well the replay fits (`ergostat fit`, the Model page). It estimates the parameters marked to fit, by
weighted least squares on the partial-model test of each equation they appear in and the replay of
each stock they move, with a standard error for each and the correlation of those fitted together,
on the record but its last fifth. It proposes a value only when the record supports it: the record
spans three of the slowest time constant the value touches, the estimate is not at its bound (a
thousand times the value written: a question of structure), the record tells it apart from the
others, it is more than two standard errors and 2% from the value written, and it fits the last
fifth better. It fits a coefficient to each declared cause of a measured flow that has no equation,
by least squares on what was measured; an outflow as its stock over a time (first-order control),
only when it names its stock as a cause; a one-way flow never below 0. Each is a **proposal**, with
its reason, the fit before and after, and the YAML edit: nothing changes until the owner accepts it
(`ergostat accept ID`, or Accept beside the part on the page, or in the Model page's review queue).
It also proposes **structure** where a check or an estimate gives a concrete fix (SPEC §12b): a stock
between a rate and the rate that follows it, an outflow for a stock nothing drains (sized by Little's
law), a converting auxiliary, a sign flipped, a guard, an auxiliary marked exogenous, a term with no
effect taken out with its link when ergostat inferred the link, and SD Lab's simplifications kept to structure
with no declared reason that the record shows to be redundant (an inferred flow that explains nothing, two flows
merged, a twin or lone stock removed), each waiting for the owner. A part the model declares is never proposed for
removal because the record has not moved it (§9: quiet is not absent). What it does not yet do is find a
stock, a delay or a cause the model lacks from the pattern in the residuals, or replace a part by
another form: a residual and a poor fit say where to look, and the guidelines above say what to write. A `driven-by` the equation leaves out is drawn with its sign and flagged
**size-unknown**: its size is not known.

Write an equation in the model's own terms first (Sterman ch. 13: every parameter should mean
something in the real world, and be measurable in principle): a first-order outflow is the stock
over the time things stay (`stock.x / time-in-x`), a coflow so many of one unit per another
(`alerts-per-outage * flow.outages`), a perceived value a `SMOOTH` of the true one, a pipeline a
`DELAY3` (an outflow that is a material delay of its stock's own inflow, `DELAY3(flow.in, T)`,
drains that stock: the delay's stages are what is in it). A moving average over the last L lags by
L/2, half its length: the first-order smoothing with its lag has a time of L/2, not L (Sterman ch.
11.5). Write time in hours: a duration (`value: 30m`) or a rate per hour; a unit counting time in
minutes or days is refused, since its value would be read as hours. A sensor that reports an average
over a window says so (`averages: 10m`), so the model is read through the same window. Mark `estimate: true` what you cannot know from the code or the process, and give it what
you believe as its value: the estimate starts there.

**Sources.** Ljung, *System Identification: Theory for the User* (2nd ed., 1999); Sterman ch. 21
(parameter estimation, and behaviour reproduction as a test); Oliva, "Model calibration as a
testing strategy for system dynamics models", *European Journal of Operational Research* (2003);
Brunton, Proctor and Kutz, "Discovering governing equations from data by sparse identification of
nonlinear dynamical systems", *PNAS* (2016).

## Testing and using a model

Once the structure reads right and the replay follows the record, system dynamics tests the model and
then uses it (Sterman ch. 21). ergostat does each where the model already is, and none of them
changes it by itself.

- **Calibrate** (the Model page's Calibrate; `ergostat proposals --calibrate`). Three ways, and they
  answer different questions. *Each part alone* fits a parameter to what it touches with everything
  else as measured: the sharpest test of one equation, and where a wrong equation elsewhere cannot
  pull it off. *Each system alone* is Homer's partial model: the system's stocks integrated, what
  comes in from outside it as measured, so a system is calibrated as if the rest were exactly right.
  *Every stock integrated* integrates every stock: the values that make the model as a whole follow
  the record, which compensate for each other's errors if a structure is wrong somewhere. What a
  decision sets is still taken as measured (the blocks are not simulated), so every loop through a
  decision stays open; the page lists them, and calls it "the whole model" only when there are none.
  A parameter's `range` bounds every calibration: an estimate that runs to an end of it is said, not
  proposed (the record wants a value the model says it cannot have: the range, or the structure, is
  wrong). Values that
  agree across the three are believable; a value the whole model wants and its part alone does not
  is a question about the structure between them. Each result is a proposal with its fit before and
  after.
- **What if** (a valve's or an auxiliary's panel). Type another value over a parameter's (a time
  with its unit, like `20s`): every chart draws the replay and the projection with it, in blue, beside
  the model's own, and its fit on the record is shown beside it, stock by stock and in total, before
  anything is kept. A value the model cannot run (one that divides by 0) is said, and never proposed. This is how a model is
  used: "what happens to the backlog if reviews take twice as long?" Nothing is saved; **Propose these**
  makes every value you are trying one proposal, with its fit on the record, which you then accept or
  dismiss.
- **Sensitivity** (the causes strip's shaded fan). Write what a number might be (`range: [0.1, 0.5]`)
  where the code or the process says so; a number estimated is sampled by its standard error. The fan
  is where nine in ten, and half, of two hundred runs over those ranges fall (parameters estimated
  together drawn together, as their correlation says); **Spread over the record** draws the same over
  the replay. A wide fan says the
  projection depends on what is not known: measure that, or say so when you use it. A narrow fan
  around a projection that is wrong says the structure is wrong, not the numbers.
- **Extreme conditions** (`ergostat check`, **extreme-conditions**). The equations alone, pushed to
  the extreme: every stock empty with nothing coming in, nothing coming in, each input alone at 0 and
  at a hundred times its largest, and each estimated or timed parameter alone at its extremes (its
  range's ends, else a hundredth and a hundred times it). Each failure names what caused it. A real queue never holds fewer than nothing, a one-way flow never runs back, a rate never
  divides by an empty stock: when the model does, an equation is wrong where it was never tested,
  and will be wrong there when the system gets there (guideline 3 is the structural form of this test).
- **Loop dominance** (a feedback loop's panel). Which loop drives the behaviour, and when, by the
  Loops That Matter method, on the replay at its integration step: each link scored by how much of its
  effect's change its cause made, a loop's score the product of its links', and at each stock its share
  of the scores of the loops through that stock, from −1 (a balancing loop drives everything there) to
  +1 (a reinforcing one). Loops of stocks that do not interact are never compared, and no loop is named
  where two are tied or where a loop through the stock cannot be scored. Growth with a reinforcing loop near +1 that
  turns over to a balancing loop is the S-shape; a goal-seeking loop that dominates all the time is a
  controller doing its job. A loop through a decision with several inputs is not scored: how much of
  the decision's change came from each input is not written in the model.

## Letting the model improve itself

The checks, the fit, the residuals and the proposals above wait for someone to look. The model can also be kept
true the way anything else in ergostat is kept: as a control loop (`docs/SPEC.md` §12e). Measure the model's
quality with one of ergostat's built-in measures (`sensor: {builtin: ergostat.model.fit}`, the scaled error of its
replay; or `ergostat.model.unexplained`, `.unidentified-loops`, `.open-findings`), hold it with a goal, and give
the goal a block that reviews the model while it is off.

That block is any block: reviewing the model is a job, not a kind of block. An `ai` block given a prompt like a
senior modeller's (the examples' `prompts/improver.md`: look for bad practice by the guidelines above and Sterman's
tests, for what is probably missing or hidden, for what disagrees with the system's own code and documents, and for
what could be simpler) reads the model with ergostat's tools and proposes; so can a program that applies rules, or a
person. Each proposal is a line, `{"propose": {...}}`, with its edit and its reasons, and **every reason needs
evidence ergostat can check**: a finding (`finding:stock-without-outflow@stock.ideas`), a statistic of the fit
(`fit:stock.quality.um`), a residual, a line of the code or the documents, or one of the rules here
(`rule:missing-delay`). A proposal that does not compile, has no evidenced reason, or clearly worsens the fit is
refused, with why; `ergostat improve --try FILE` (the MCP tool `try_change`) says so beforehand.

Every change to the model, the block's and ergostat's own calibrations and structural proposals alike, is an item
(`ergostat.model-change`, Items and the review queue; its page keeps each field's history, so the reasons as made and
as checked, and each verdict, stay readable), and a judge (`type: judge`, a built-in block) tests each the
way a rollout tests a build: beside the model as it is, on the record that comes after it was made, over the whole
of that record, its halves and its quarters. It passes only when it is better in every window (or, for a change the
fit cannot see, no worse anywhere and answering findings), and fails otherwise, with the windows as its evidence.
This matters because a change fitted to the record it was found on will always look good on that record: the judge
looks only at record the change has not seen (Sterman ch. 21, behaviour reproduction; Ljung ch. 16,
cross-validation).

Who writes a passed change is the owner's choice, in the judge's `accept:`: by default nothing is written by
itself. A sensible start is to let a parameter's value be written once passed (`accept: {parameter: auto}`), since
the structure stays as people declared it, and to keep every change to the structure for the owner to read in the
review queue, the judge's verdict beside it; a change that removes structure always waits for the owner,
whatever the policy. Everything written is recorded with its reason and its effect
(`ergostat.model.changed`), and committed by the owner.

## A checklist for reviewing a model

1. Run `ergostat check`; answer every structure finding, by a change or by a word with a reason.
2. For each stock: what fills it, what drains it, and does the drain depend on what is there?
3. For each `driven-by` on a flow: does the effect come at once? If not, where does the cause
   wait (the stock), and what ends its wait (the flows out of it)?
4. For each link: is it signed, and do its units convert?
5. For each decision: what does the decision maker actually see, and how late?
6. For each long delay between cause and effect: is the stock of what is in transit in the model?
7. On the Model page: which stocks the replay does not follow, and how (Theil's U_M, U_S, U_C); which
   are not explained (the residuals), which way, and what moves with them?
8. For each auxiliary: is it explained by the model, or declared as coming from outside?
9. Calibrate each part alone and the whole model: do the values agree? Where they do not, look at the
   structure between them.
10. Give the numbers you are unsure of a `range`, and read the fan before you act on a projection.
11. For each part the record has not exercised (`not-exercised`): keep it with its reason, and plan
    the step test or disturbance that would exercise it, rather than removing it.

## Sources

- John D. Sterman, *Business Dynamics: Systems Thinking and Modeling for a Complex World*
  (Irwin/McGraw-Hill, 2000): ch. 5 (causal loop diagrams, link polarity), ch. 6 (stocks and flows),
  ch. 8 (first-order systems), ch. 11 (delays), ch. 12 (aging chains and coflows), ch. 13 (modelling
  decision making), ch. 15 (bounded rationality), ch. 21 (truth and beauty: validation and model
  testing: boundary adequacy, structure assessment, dimensional consistency, extreme conditions,
  behaviour reproduction); and Sterman, "Appropriate summary statistics for evaluating the historical fit
  of system dynamics models", *Dynamica* 10(2), 1984 (R², MAPE, Theil's inequality statistics).
- Jack Homer, "Partial-model testing as a validation tool for system dynamics", *System Dynamics
  Review* 28(3), 2012.
- Jay W. Forrester and Peter M. Senge, "Tests for building confidence in system dynamics models",
  *TIMS Studies in the Management Sciences* 14, 1980 (extreme conditions, sensitivity).
- Kim Schoenberg, Pål Davidsen and Robert Eberlein, "Understanding model behavior using the Loops that
  Matter method", *System Dynamics Review* 36(2), 2020 (loop dominance).
- Michael D. McKay, Richard J. Beckman and William J. Conover, "A comparison of three methods for
  selecting values of input variables in the analysis of output from a computer code", *Technometrics*
  21(2), 1979 (Latin hypercube sampling).
- Jay W. Forrester, *Industrial Dynamics* (MIT Press, 1961) and *Principles of Systems*
  (Wright-Allen, 1968): levels and rates, and the information that rate equations may use.
- The references under "Improving from data" above.
