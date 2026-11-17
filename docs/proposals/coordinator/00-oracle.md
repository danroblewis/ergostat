# 00. The method we are held to

Status: reference, 2026-11-17. The first of the Coordinator notes. It says how a system dynamics
practitioner and a control engineer would each go about designing the Coordinator (the control system
that a long AI agent session was: [harness-as-control-system.md](../harness-as-control-system.md)),
what each would expect to be handed at every step, and what each would ask when reviewing it. Every
later note in this folder is held to it. Its words are fixed in [01-terminology.md](01-terminology.md).

The owner's standard: a control engineer and an SD practitioner reading the work should find it normal
and methodical, the way their own textbooks and practice would do it. **Surprising only in the subject,
never in the method or the words.** So this note invents nothing. It sets out the two disciplines'
processes as their texts set them out, then the two bridges that carry them to supervising agents
(Leveson's STAMP, Ashby's requisite variety), then the checklist.

Citations name a chapter or section only where it is known; otherwise the book alone. Where a detail
should be checked against the source before it is quoted elsewhere, it is listed at the end.

## 1. How to use this note

Each step below has three parts:

- **What the step is**, as the discipline's own texts say it.
- **What it produces**: the deliverable, in the form a practitioner expects to see it (a model boundary
  chart is a three-column table, not a paragraph; a cause and effect matrix is a matrix, not a list of
  rules).
- **Review questions**, numbered (SD-1, CE-1, ST-1, AV-1). These are the checklist (section 6). A design
  note for the Coordinator answers each question that applies, or says why it does not.

Both processes are iterative. Sterman stresses that the steps of the modelling process are revisited
in any order as understanding grows (*Business Dynamics*, ch. 3); the control lifecycle loops back from
commissioning and from every management-of-change review. The order below is the order of first
passes, not a waterfall.

## 2. System dynamics: the modelling process

The reference is Sterman, *Business Dynamics* (2000), ch. 3, "The Modeling Process", whose Table 3-1
gives the steps used below. Forrester's *Industrial Dynamics* (1961) is the origin; Morecroft's
*Strategic Modelling and Business Dynamics* (2nd ed., 2015) and Richardson and Pugh's *Introduction to
System Dynamics Modeling with DYNAMO* (1981) say the same process in other words, and add what is noted.

The first rule, before any step: **model a problem, not a system.** A model is built for a purpose, a
dynamic problem someone wants explained or a policy someone wants to choose, and everything (the
boundary, the level of aggregation, the time horizon, the tests) is judged against that purpose
(Forrester; Sterman ch. 3). A model "of the Coordinator" in general has no purpose and cannot be
validated.

### 2.1 Problem articulation (boundary selection)

**What.** Choose the theme: what is the problem, and why is it a problem? Name the key variables. Set
the time horizon: far enough back to see the problem emerge, far enough forward to capture the delayed
and indirect effects of the policies considered. Define the problem dynamically, as **reference modes**:
graphs of the key variables over time, both as they were and as they might go (Sterman ch. 3).

**Produces.**

- A **problem statement**: one paragraph naming the problem, whose problem it is, and the decision the
  model is for.
- **Reference modes**: behaviour-over-time graphs of the key variables, with units and dates on the
  axes, drawn from data where it exists and from the stakeholders' account where it does not, and
  labelled as which. Usually also the hoped-for and feared futures.
- The **time horizon**, with its reason (the longest delay that matters, several times over).

**Review questions.**

- SD-1. What decision is the model for, and who makes it?
- SD-2. Is the problem stated as a behaviour over time (a reference mode), not as an event or a wish?
- SD-3. Are the reference modes drawn from the record where the record exists, with units and dates?
- SD-4. Is the time horizon long enough to show the problem arising and the delayed effects of the
  policies considered?

### 2.2 Formulation of a dynamic hypothesis

**What.** A dynamic hypothesis is a working theory of how the problem arose: a feedback structure that,
endogenously, would produce the reference modes (Sterman ch. 3). Generate the initial hypotheses (the
stakeholders' theories, the literature's), keep the focus endogenous (explain the behaviour by the
interactions of the variables inside the boundary, not by outside shocks), and map the structure.

**Produces.**

- A **model boundary chart**: a table of three columns, the variables that are **endogenous**,
  **exogenous** and **excluded** (Sterman ch. 3). The excluded column is the one reviewers read first.
- A **subsystem diagram**: the sectors of the model, the flows of material, information and money
  between them, and who controls each.
- **Causal loop diagrams**, with every link's polarity and every loop named and marked R or B
  (Sterman ch. 5).
- **Stock and flow maps** of the main chains (Sterman ch. 6), including the conserved chains that run
  through the problem (here, items of work through their states).
- **Policy structure diagrams** (Morecroft): for each decision, the information it reads and the
  pressures it balances, drawn as the decision function's inputs.
- The **hypothesis stated in words**, against the reference modes: "this loop dominates first, so the
  backlog grows; then this one, so it overshoots".

**Review questions.**

- SD-5. Is there a dynamic hypothesis, stated before any fitting, that would produce the reference
  modes from inside the boundary?
- SD-6. Is there a model boundary chart, and is each excluded variable excluded on purpose, with a
  reason?
- SD-7. Is every link's polarity stated, every loop named R or B, and the loop expected to dominate in
  each phase of the reference mode said?
- SD-8. Is every decision shown with the information it actually uses (a policy structure diagram, or
  the equivalent)?

### 2.3 Formulation of a simulation model

**What.** Specify the structure and the **decision rules**; estimate parameters, behavioural
relationships and initial conditions; test for consistency with the purpose and the boundary (Sterman
ch. 3). The craft of this step is ch. 12 (coflows and aging chains), ch. 13 ("Modeling Decision
Making"), ch. 14 (formulating nonlinear relationships), and ch. 11 (delays). The principles a
practitioner applies as reflex:

- **Stocks and flows are kept apart, and conserved.** A stock changes only through its flows; a rate
  depends on stocks (and auxiliaries computed from them), never directly on another rate (Forrester).
- **Decision rules use only information the decision maker actually has**, when they have it: the
  **Baker criterion** (Sterman ch. 13). A decision reads perceived values, which lag the true ones, so
  perception is a stock (an information delay), not a free look at the truth (Sterman ch. 11).
- **Decision rules are robust**: they behave sensibly in extreme conditions (no stock drained below
  zero, no order with nothing to order from) and are formulated from how decisions are made, not how
  they should be made (bounded rationality: Sterman ch. 15; Morecroft's work on decision functions,
  for example "Rationality in the analysis of behavioral simulation models", *Management Science*
  31(7), 1985).
- **Every variable and parameter has a real-world meaning and units**, and every equation is
  dimensionally consistent.
- **Parameters are estimated below the level of the behaviour the model is meant to explain**: from
  direct observation, records and interviews about the part, not only by fitting the whole model to its
  output (Graham, "Parameter estimation in system dynamics modeling", in Randers (ed.), *Elements of
  the System Dynamics Method*, 1980). Calibration against the output is one source among several
  (Oliva, "Model calibration as a testing strategy for system dynamics models", *European Journal of
  Operational Research* 151, 2003).

**Produces.** The model itself (equations, units, a documented source for every parameter), a
**parameter table** (value, unit, source, confidence), and documentation good enough for another
modeller to reproduce the results (Rahmandad and Sterman, "Reporting guidelines for simulation-based
research in social sciences", *System Dynamics Review* 28(4), 2012).

**Review questions.**

- SD-9. Does every rate depend on stocks and auxiliaries, not on another rate, unless the dependence is
  truly instantaneous and said so?
- SD-10. Does every decision rule read only what that decision maker could know, with its perception
  delay (the Baker criterion)?
- SD-11. Does every parameter have units, a real-world meaning, and a stated source other than "fitted"
  where one exists?
- SD-12. Are decision rules formulated from how the actors behave, not how they ought to?

### 2.4 Testing

**What.** Sterman ch. 21 ("Truth and Beauty: Validation and Model Testing") treats validation as
building confidence that a model is fit for its purpose, never as proving it true. His Table 21-4,
adapted from Forrester and Senge ("Tests for building confidence in system dynamics models", *TIMS
Studies in the Management Sciences* 14, 1980), lists the tests:

| Test | The question |
|---|---|
| Boundary adequacy | Are the important concepts for the purpose endogenous? Does behaviour or a policy conclusion change when the boundary is extended? |
| Structure assessment | Is the structure consistent with what is known of the real system, at the right level of aggregation? Does it obey conservation laws? Do decision rules use only available information? |
| Dimensional consistency | Is every equation dimensionally consistent without parameters that have no real-world meaning? |
| Parameter assessment | Are the values consistent with what is known, numerically and descriptively? |
| Extreme conditions | Does each equation make sense at extreme values of its inputs? Does the model respond plausibly to extreme policies and shocks? |
| Integration error | Are the results sensitive to the time step or the integration method? |
| Behaviour reproduction | Does the model reproduce the behaviour of interest, qualitatively and quantitatively? |
| Behaviour anomaly | Do anomalous behaviours appear when assumptions are changed or removed (loop knockout)? |
| Family member | Can the model reproduce other instances of the same kind of system? |
| Surprise behaviour | Does the model generate behaviour not previously observed, and is it then found in the system? |
| Sensitivity analysis | Do numerical, behavioural or policy conclusions change under plausible variation of uncertain assumptions? |
| System improvement | Did the modelling process help change the system for the better? |

Behaviour reproduction is measured with summary statistics that say what kind of error is left, above
all Theil's inequality statistics, splitting the mean squared error into bias, unequal variation and
unequal covariation (Sterman, "Appropriate summary statistics for evaluating the historical fit of
system dynamics models", *Dynamica* 10, 1984). Barlas ("Formal aspects of model validity and validation
in system dynamics", *System Dynamics Review* 12(3), 1996) orders the tests: direct structure tests
first, then structure-oriented behaviour tests, and behaviour pattern tests last, because a model can
reproduce the data for the wrong reasons.

**Produces.** A **test report** with one entry per test above: what was done, what was found, what was
changed because of it. The fit against the reference modes, with Theil's breakdown per variable. A
**sensitivity analysis** (fans over the uncertain parameters) that says which conclusions hold across
them.

**Review questions.**

- SD-13. Were the structure tests passed before the behaviour was fitted?
- SD-14. Is each of Table 21-4's tests done, or said not to apply and why?
- SD-15. Is behaviour reproduction judged per variable, with the kind of error left (bias, variance,
  covariance), not as one scalar over the model?
- SD-16. Do the policy conclusions survive the sensitivity analysis?
- SD-17. Was a part removed or knocked out to show what each loop contributes (behaviour anomaly)?

### 2.5 Policy design and evaluation

**What.** Specify the scenarios (the environments the policies must work in); design new decision rules,
strategies and structures; ask "what if" of each; test the policies' sensitivity and robustness across
the scenarios; and test the interactions of policies (Sterman ch. 3). A policy in system dynamics is a
**decision rule**: the change is to how a flow is set, or to which information a decision reads, or to
the structure itself, not to one parameter's value. Leverage is found by asking which loops dominate
and how a policy shifts that dominance (Meadows, *Thinking in Systems*, on leverage points).

**Produces.** A **policy table**: each policy, the decision rule it changes (as an equation), the
scenarios it was run in, the result in each against the reference mode, and how robust it is. A
recommendation, with what the model cannot say.

**Review questions.**

- SD-18. Is each proposed change stated as a change to a decision rule or to structure, and simulated
  before it is made?
- SD-19. Is each policy tested across scenarios, not only in the one it was designed for?
- SD-20. Is the effect explained by the loops it strengthens or weakens, not only by its output?

### 2.6 What Forrester and Morecroft add

- **Forrester**: the alternation of levels and rates, the closed boundary as the ideal (Forrester's
  insistence that the behaviour is generated inside), and the observation that policies, not people,
  make the behaviour: blaming an actor is a failure to model the decision rule they follow.
- **Morecroft**: the decision function as bounded rationality made visible (each decision sees a
  partial view of the system, filtered); the policy structure diagram as the deliverable that shows it;
  and the habit of modelling with the people who make the decisions.

## 3. Control engineering: the design process

There is no single textbook chapter for the whole of it, because practice spans the loop (Franklin,
Powell and Emami-Naeini's chapter "Control System Design: Principles and Case Studies" outlines the
single-loop design steps: understand the process and the specifications, select sensors and
actuators, model, design a simple controller, evaluate, simulate with the nonlinearities, build), the
plant (Seborg, Edgar, Mellichamp and Doyle, *Process Dynamics and Control*), the control structure
(Skogestad and Postlethwaite, *Multivariable Feedback Control*, ch. 10; Skogestad, "Control structure
design for complete chemical plants", *Computers and Chemical Engineering* 28, 2004) and the standards
of the process industries (ISA-88, IEC 61511, ISA-101, ISA-18.2). The ten steps below are the order in
which an engineer would hand over the documents.

### 3.1 The plant: inputs, outputs and disturbances

**What.** Describe what is controlled. List the variables by their role: the **controlled variables**
(CV, y: what must be held), the **manipulated variables** (MV, u: what can be moved), the **disturbance
variables** (DV, d: what moves the plant and cannot be moved; measured or not), and the measurements
available. Count the degrees of freedom. Draw the plant.

**Produces.** A **process description** and a drawing of it (in a plant, a P&ID with instrument tags
per ISA-5.1; in computing, a block diagram of the plant with its queues and servers, as in Hellerstein
et al., *Feedback Control of Computing Systems*). A **variable list**: one row per variable, its role
(CV, MV, DV, measured only), unit, range, and how it is measured or moved.

**Review questions.**

- CE-1. Is every variable classed as CV, MV or DV, with its range and unit?
- CE-2. Is each disturbance said to be measured or not (which decides feedforward or feedback)?
- CE-3. Are the degrees of freedom counted, and does every MV have a purpose?

### 3.2 The control objectives and constraints

**What.** State what the control system is for: the operational objectives (Skogestad's top-down
analysis starts by defining the cost to minimise and the constraints to respect), the performance
specifications of each controlled variable (setpoint tracking, disturbance rejection, rise and settling
time, overshoot, steady-state error, noise sensitivity), the robustness required (gain, phase and delay
margins; the peak of the sensitivity function, Ms, typically under 2: Skogestad and Postlethwaite), and
the **constraints**, hard (never crossed) and soft (penalised). An objective is a reference to steer
towards; a constraint is a region not to leave. They are written separately because they are enforced
differently (sections 3.5 and 3.7).

**Produces.** A **functional specification**, or control philosophy: objectives in priority order,
specifications per CV as numbers, constraints marked hard or soft, and what happens when they conflict.

**Review questions.**

- CE-4. Is every objective measurable, with a number?
- CE-5. Are setpoints (steered to) kept apart from constraints (not crossed), and each constraint
  marked hard or soft?
- CE-6. Is the priority among objectives stated for when they conflict?

### 3.3 The control hierarchy and time-scale separation

**What.** Arrange control in layers, each slower than the one below and setting its references. Seborg
et al. (ch. 1) give the hierarchy of process control activities: measurement and actuation; safety,
environmental and equipment protection; **regulatory control**; real-time optimisation; and **planning
and scheduling**, with time scales from seconds at the bottom to days and weeks at the top. Skogestad
calls the middle layers the **regulatory** layer (stabilising, keeping the plant in its operating
range: fast, simple, usually single loops) and the **supervisory** layer (keeping the primary
controlled variables at their optimal setpoints, by setting the regulatory loops' references:
decentralised loops or MPC), with optimisation above. ISA-95 (IEC 62264) gives the same structure from
the enterprise side, with level 3, manufacturing operations (dispatching, detailed scheduling,
tracking), between the control system and business planning.

The rule that makes layers work is **time-scale separation**: each outer loop is several times slower
than the loop it sets, so the inner settles between the outer's moves and the two can be designed
separately (cascade design in Seborg et al.; Skogestad and Postlethwaite ch. 10). A layer that moves an
inner reference faster than the inner can follow is not a hierarchy; it is a coupled loop.

**Produces.** A **control structure diagram**: the layers, the loops in each, what each layer sets in
the one below, and each loop's time scale (closed-loop time constant or sampling period), with the
separation between neighbours stated as a ratio.

**Review questions.**

- CE-7. Is every function placed in a layer, with the layer's time scale?
- CE-8. Is each outer layer several times slower than the one it sets, and is the ratio stated?
- CE-9. Does each layer act only by setting references and modes of the layer below, never by moving
  its actuators directly?

### 3.4 Pairing measurements with actuators

**What.** Choose which MV controls which CV, and which CVs are controlled at all. In the top-down
analysis, select the primary controlled variables (those whose constant setpoints keep operation near
optimal: Skogestad's self-optimising control, "Plantwide control: the search for the
self-optimizing control structure", *Journal of Process Control* 10, 2000) and the throughput
manipulator. Then pair, bottom-up, using controllability (can the MV move the CV fast and far enough?),
interaction (the relative gain array: Bristol, "On a new measure of interaction for multivariable
process control", *IEEE Transactions on Automatic Control* 11, 1966), and observability (is the CV
measured, or estimated from what is?).

**Produces.** A **pairing table**: each loop, its CV, its MV, the reason for the pairing (gain, delay,
interaction), and the CVs left uncontrolled with why. For interacting loops, the RGA or its equivalent.

**Review questions.**

- CE-10. Is every controlled variable paired with exactly one manipulated variable, or explicitly
  handled by a multivariable controller?
- CE-11. Is the pairing justified by gain, delay and interaction, not by convenience?
- CE-12. Is every controlled variable observable (measured, or estimated with a stated estimator)?

### 3.5 Each loop's design

**What.** For each loop: the controller's form (on/off with hysteresis, P, PI, PID, or a model-based
law such as MPC), its tuning (SIMC: Skogestad, "Simple analytic rules for model reduction and PID
controller tuning", *Journal of Process Control* 13, 2003; lambda tuning), and the practical matters
that decide whether it works:

- **Sampling.** The sampling period against the closed-loop dynamics: a few to ten samples per rise
  time is the usual rule (Åström and Wittenmark, *Computer-Controlled Systems*), the hold included in
  the dead time.
- **Saturation and anti-windup.** Every actuator has limits; an integrating controller at a limit must
  not keep integrating (Åström and Hägglund, *Advanced PID Control*, §3.5). The limits are part of the
  design, not discovered in operation.
- **Feedforward**, from a measured disturbance, added before the error appears; never a substitute for
  feedback.
- **Cascade**, where an inner variable responds faster than the outer and catches disturbances first;
  **ratio**, **override (selector)** and **split-range** structures where the problem asks for them;
  **gain scheduling** where the process changes with the operating point (Seborg et al.; Åström and
  Hägglund).
- **Modes and transfer**: auto and manual, and bumpless transfer between them and between controllers.
- **Robustness**: the margins at the worst the process could be, not only at the nominal model.

**Produces.** A **loop sheet** per loop (in a plant, the instrument loop diagram of ISA-5.4 beside a
data sheet): the tag, CV, MV, controller form and tuning, sampling period, limits and anti-windup,
feedforward and cascade connections, modes, alarm limits, and the margins with the process model they
were computed on.

**Review questions.**

- CE-13. Does every loop have a stated controller form and tuning, with the process model it was tuned
  on?
- CE-14. Is the sampling period stated and justified against the loop's speed and the controller's own
  delay?
- CE-15. Are the actuator's limits stated, and is windup prevented?
- CE-16. Are feedforward, cascade and override used where the disturbances and constraints call for
  them, and nowhere else?
- CE-17. Are the margins stated, at the worst plausible process?

### 3.6 Modes and supervisory logic

**What.** Above and beside the continuous loops sits discrete logic: what state each unit is in, which
mode each loop is in, and which actions are allowed when. Two traditions say it.

- **ISA-88** (batch control; IEC 61512-1) separates the **physical model** (enterprise down to
  equipment and control modules), the **procedural control model** (procedure, unit procedure,
  operation, phase) and the **process model**, and gives each procedural element **states** (such as
  idle, running, holding, held, restarting, complete, stopping, stopped, aborting, aborted) with the
  commands that move between them, and **modes** (automatic, manual, and an intermediate mode in which
  the operator confirms transitions) that say who drives the transitions. It also separates the
  **recipe** (what to make and how: general, site, master and control recipes, the control recipe being
  the one used for one batch) from the equipment that runs it.
- **Supervisory control of discrete-event systems** (Ramadge and Wonham, "Supervisory control of a
  class of discrete event processes", *SIAM Journal on Control and Optimization* 25(1), 1987; Cassandras
  and Lafortune, *Introduction to Discrete Event Systems*, 2nd ed., 2008, ch. 3). The plant is an
  automaton generating events; events are partitioned into **controllable** (the supervisor may disable
  them) and **uncontrollable** (it may not); a specification is a language of allowed behaviour; a
  supervisor exists that achieves it exactly when the specification is **controllable** with respect to
  the plant, and otherwise the supremal controllable sublanguage is the most permissive supervisor that
  is safe. The supervisor should also be **nonblocking**: every reachable state can still reach a marked
  (completed) one.

**Produces.** A **state diagram** for each unit or kind of thing (states, events, which events are
controllable), a **mode table** (each mode, who drives transitions, which loops run), and the
**supervisor's specification**: what must never happen and what must always remain possible, with the
proof or test that it is controllable and nonblocking.

**Review questions.**

- CE-18. Does every unit or kind of work have a state diagram, with each event marked controllable or
  not?
- CE-19. Is every mode stated, with who drives the transitions in it and how transfer between modes is
  made bumpless?
- CE-20. Is the supervisor's specification written as allowed behaviour, and checked to be controllable
  (it never needs to disable an uncontrollable event) and nonblocking (work can always finish)?
- CE-21. Is the recipe (what is done) kept apart from the equipment (what does it)?

### 3.7 Layers of protection and interlocks

**What.** The basic process control system regulates; it is not trusted to keep the plant safe. Safety
is a separate set of layers (the "onion" of the CCPS: process design, the basic control system, alarms
and operator response, the safety instrumented system, physical protection, and emergency response
beyond), each an **independent protection layer** only if it is independent of the initiating cause
and of the other layers, effective, and auditable (CCPS, *Layer of Protection Analysis*, 2001). IEC
61511 (the process-industry application of IEC 61508) sets the lifecycle: **hazard and risk
assessment** (typically HAZOP: IEC 61882), **allocation** of safety functions to protection layers
(often by LOPA), the **safety requirements specification** for each safety instrumented function
(its trip condition, safe state, response time and required reliability as a safety integrity level),
design, validation, operation and maintenance, and **modification under management of change**. The
vocabulary is exact:

- a **permissive** is a condition that must hold before an action may start (a pump may not start until
  its suction valve reads open);
- an **interlock** prevents or forces an action when a condition holds;
- a **trip** takes the process to its **safe state** when a limit is crossed;
- a **bypass** disables a protective function on purpose, for a bounded time, authorised, recorded, and
  itself alarmed.

A protective function is designed to break the control loop, never to be steered through.

**Produces.** A **hazard register** (HAZOP worksheets: deviation, cause, consequence, safeguards,
actions), a **LOPA** table per hazard (initiating event frequency, each independent layer's
probability of failure on demand, the result against the tolerable frequency), a **safety requirements
specification**, and a **cause and effect matrix** (rows the initiating conditions, columns the
actions, each cell the logic): the standard deliverable for interlocks and permissives.

**Review questions.**

- CE-22. Is there a hazard analysis that lists what can go wrong, its consequence and its safeguards?
- CE-23. Is every protective function independent of the control function whose failure it guards
  against?
- CE-24. Is each protective function's trigger, safe state and response time stated (a cause and effect
  matrix)?
- CE-25. Are bypasses bounded in time, authorised, recorded and visible?
- CE-26. Is it impossible for a setpoint or a controller to drive the system through a protection
  layer?

### 3.8 The operator interface and alarms

**What.** The operator is the outermost loop, and sees the plant only through the interface. Two
standards govern it, with Hollifield and Habibi, *Alarm Management: A Comprehensive Guide*, and
Hollifield et al., *The High Performance HMI Handbook*, as their practice, and EEMUA 191 beside them.

- **ISA-101.01** (HMIs for process automation): an HMI **philosophy**, a **style guide** and a
  **toolkit**, and a lifecycle for them; a **display hierarchy**, level 1 the whole area's overview
  (key measures against their targets, abnormal states salient), level 2 a unit, level 3 detail (one
  loop), level 4 diagnostics; grey by default, colour reserved for the abnormal.
- **ISA-18.2** (IEC 62682), alarm management: an **alarm** is an indication to the operator of an
  abnormal condition that requires a timely response, so an alarm without a defined response is not an
  alarm. Its lifecycle: an **alarm philosophy**, identification, **rationalisation** (for each alarm:
  cause, consequence, the operator's corrective action, the time allowed to respond, the priority that
  follows from consequence and time), detailed design (deadbands, delays, state-based alarming and
  suppression), implementation, operation (shelving, out-of-service), maintenance, **monitoring and
  assessment**, management of change, and audit. Its performance is measured: on the order of 6 alarms
  an hour per operator is very likely acceptable and 12 the most manageable on average; a flood is more
  than 10 alarms in 10 minutes; standing (stale) and chattering alarms and time in flood are counted.

**Produces.** An **HMI philosophy** and display hierarchy, an **alarm philosophy**, a **master alarm
database** (every alarm, rationalised, with its limit, priority, response and time to respond), and
the alarm system's own **performance report**.

**Review questions.**

- CE-27. Does every interruption of the operator have a defined response, a priority and a time to
  respond (rationalised), or is it not an alarm?
- CE-28. Is the operator's alarm load measured and held within a stated rate, with floods, standing
  and chattering alarms counted?
- CE-29. Does the interface show the overview first, deviations from targets salient, and detail on
  demand?
- CE-30. Is every operator input a closed, typed act (a setpoint, a mode change, an acknowledgement, an
  override) and logged?

### 3.9 Identification and validation

**What.** The models the loops were designed on are learned from the plant and checked before they are
trusted. Ljung, *System Identification: Theory for the User* (2nd ed., 1999), gives the loop: prior
knowledge, **experiment design** (ch. 13: inputs that excite the dynamics persistently, within the
plant's limits; closed-loop data needs care because feedback correlates the input with the noise), the
data, the **model set** (ch. 4), the **criterion** (prediction error methods, ch. 7), the computed
model, and **validation** (ch. 16): on data not used to fit it, by simulation and prediction, with
**residual analysis**, the residuals white and uncorrelated with past inputs, a failure of either
naming what is missing. If it fails, return to an earlier step. A model is valid for a purpose, here
for designing a controller.

The controller is then validated too: in simulation against the nonlinear model, at the factory and
the site acceptance tests, at commissioning (loop checks, step tests), and in operation by **control
performance monitoring** (the Harris index: Desborough and Harris, "Performance assessment measures
for univariate feedback control", *Canadian Journal of Chemical Engineering* 70, 1992; oscillation
detection; time at limits).

**Produces.** An **identification report** per process model (experiment, data, model structure,
estimates with their uncertainty, validation on fresh data with residual tests) and a **performance
report** per loop in operation.

**Review questions.**

- CE-31. Is every process model identified from a designed experiment or a stated record, and
  validated on data it was not fitted to?
- CE-32. Are the residuals tested for whiteness and independence from the input, and what a failure
  means said?
- CE-33. Is closed-loop identification handled as such?
- CE-34. Is each loop's performance monitored in operation, with a measure that says when it has
  degraded?

### 3.10 Management of change

**What.** Any change to a running plant other than a replacement in kind (to its process technology,
equipment, procedures, control logic, setpoints beyond the established operating limits, or its
protection layers) is reviewed before it is made: its technical basis, its effect on safety and health,
modifications to operating procedures, the time needed, and the authorisation required; the documents
are brought up to date and the people affected are told and trained, and before restart a pre-startup
safety review confirms it is as designed (OSHA, Process Safety Management, 29 CFR 1910.119, paragraphs
(l) and (i); CCPS, *Guidelines for the Management of Change for Process Safety*, 2008). Temporary
changes carry their expiry. Changes are classed by risk, and some classes are pre-approved.

**Produces.** A **change request** per change (what, why, the hazard review, the authorisation, the
documents updated, the review before start-up, the close-out), and the record of all of them.

**Review questions.**

- CE-35. Is every change to the control system other than tuning within its approved range made
  through a recorded, reviewed and authorised change?
- CE-36. Is each change classed by its risk, with who may authorise each class?
- CE-37. Does each change say when it takes effect on running work, and is it applied without a bump?
- CE-38. Are temporary changes and bypasses given an expiry?

## 4. The bridges: supervising agents

The two processes above assume the machines are designed and their faults enumerated. Two bodies of
work carry them to a plant whose actors are people and AI agents, without leaving either discipline.

### 4.1 Leveson's STAMP and STPA

Leveson, *Engineering a Safer World* (2011), recasts safety as a control problem. In **STAMP**
(ch. 4), accidents result from inadequate enforcement of **safety constraints** by a hierarchical
**control structure**, not from chains of component failures. Every controller, human or automated, has
a **process model** (its belief about the state of what it controls); control goes wrong when that
model is wrong, when the control action is unsafe, or when feedback is missing or delayed. **STPA**
(ch. 8; Leveson and Thomas, *STPA Handbook*, 2018) is the analysis that follows:

1. Define the purpose: the **losses** to avoid, the system-level **hazards** that lead to them, and the
   system-level **constraints** that prevent them.
2. Model the **control structure**: controllers, the control actions they issue, the feedback they
   receive, layered from the owner down to the machines.
3. Identify **unsafe control actions**, for each control action in four ways: not provided when
   needed; provided when it causes a hazard; provided too early, too late or out of order; stopped too
   soon or applied too long.
4. Identify **loss scenarios**: why each unsafe control action could occur (a flawed process model,
   missing feedback, a conflicting controller) and why a safe action could be carried out wrongly.

This is the most direct form for a Coordinator: the owner, the Coordinator, the workers and the tools
are a control structure; a worker that pushes with failing tests is an unsafe control action "provided
when it causes a hazard", traceable to a flawed process model (it believed the tests passed) and to
feedback that was not independent (a pipe hid the exit code).

**Produces.** A **losses and hazards list**, **system-level constraints**, a **control structure
diagram**, an **unsafe control actions table** (control action × the four ways), and **loss scenarios**
with the requirements they give rise to. CAST (ch. 11) is the same frame applied to an incident after
the fact.

**Review questions.**

- ST-1. Are the losses and hazards stated, and each hazard tied to a constraint?
- ST-2. Is the control structure drawn, with every control action and every feedback path, owner to
  machine?
- ST-3. Is each control action examined in the four ways it can be unsafe?
- ST-4. For each controller, is its process model named (what it believes, from which feedback), and
  what happens when that model is wrong?
- ST-5. Is every incident analysed as a control failure (CAST), not as an actor's error?

### 4.2 Ashby's requisite variety, and the good regulator

Ashby, *An Introduction to Cybernetics* (1956), ch. 11: **only variety can destroy variety**. A
regulator can hold the outcome within a set no smaller than the variety of the disturbances divided by
the variety of its responses. Conant and Ashby ("Every good regulator of a system must be a model of
that system", *International Journal of Systems Science* 1(2), 1970) add that the simplest optimal
regulator is a model of what it regulates; the internal model principle (Francis and Wonham, 1976) is
the control engineer's version for classes of disturbance. Beer (*Brain of the Firm*, 1972; 2nd ed.,
1981) turns it into design: where a regulator lacks variety, **attenuate** the variety reaching it
(classify, filter, summarise) or **amplify** its own (delegate, add responses), and do both
deliberately.

This is why an AI agent is worth having in a control system at all (it has many responses), and why a
Coordinator built of fixed rules fails on what the session handled (one routing rule for every message
has a variety of one). It is also the test of every reduction in the parity notes: moving a function
down to a rule is safe only for the part of the disturbance variety the rule matches.

**Produces.** A **variety account** per regulator: the classes of disturbance it faces (counted from
the record), the classes of response it has, where the variety is attenuated before it (a classifier,
a display) and amplified behind it (delegation), and what falls outside, routed where.

**Review questions.**

- AV-1. For each regulator, are the classes of disturbance it faces counted from the record, and its
  responses against them?
- AV-2. Where a fixed rule replaces judgement, is the variety it does not cover named, and routed to
  something with more?
- AV-3. Is every attenuator (classifier, summary, display) measured for what it drops?
- AV-4. Does each regulator contain a model of what it regulates (the good regulator), and is that
  model the one in ergostat?

### 4.3 The human in the loop

Three works complete the bridge for the owner's part. Sheridan's supervisory control
(*Telerobotics, Automation, and Human Supervisory Control*, 1992) has the human plan, teach, monitor,
intervene and learn; Sheridan and Verplank's levels of automation (1978) and Parasuraman, Sheridan and
Wickens ("A model for types and levels of human interaction with automation", *IEEE Transactions on
Systems, Man, and Cybernetics A* 30(3), 2000) say, per function, how much the machine decides and how
much the human approves. Bainbridge ("Ironies of automation", *Automatica* 19(6), 1983) warns that the
more is automated, the less able the human is to take over when it fails. Lee and See ("Trust in
automation: designing for appropriate reliance", *Human Factors* 46(1), 2004) define **trust** as the
human's attitude to automation and ask that reliance match the automation's real capability.

- HU-1. Is the level of automation of each function stated (who decides, who approves)?
- HU-2. Can the owner take over each function, with the information needed to do so?
- HU-3. Is the owner's reliance on each machine calibrated against its measured performance?

## 5. How the two processes meet

ergostat holds one model and two perspectives (SPEC §1a). The two processes are not merged: each is
followed in its own terms, on the same structure. Where their steps correspond:

| System dynamics (Sterman ch. 3) | Control engineering | Bridges |
|---|---|---|
| Problem articulation, reference modes | Objectives and specifications (3.2) | Losses and hazards (STPA 1) |
| Model boundary chart | The plant's inputs, outputs and disturbances (3.1) | Variety of disturbances (Ashby) |
| Dynamic hypothesis: loops, stock and flow maps | Control structure and hierarchy (3.3), pairing (3.4) | Control structure diagram (STPA 2) |
| Decision rules (policy structure) | Each loop's controller (3.5), modes and supervisor (3.6) | Unsafe control actions (STPA 3) |
| Formulation: estimation from parts | Identification (3.9) | Process models (STPA 4) |
| Testing (ch. 21) | Validation, commissioning, performance monitoring (3.9) | Loss scenarios, CAST |
| Policy design and evaluation | Controller redesign under management of change (3.10) | Constraints enforced (STAMP) |
| (none) | Protection layers (3.7), operator interface and alarms (3.8) | Levels of automation (4.3) |

Where they differ, both are kept:

- **Boundary.** SD draws it from the purpose and wants the behaviour endogenous; control draws it
  around the plant and treats what comes from outside as disturbance. A Coordinator model needs both:
  the owner's corrections are a disturbance to the control view and, in the SD view, the output of a
  loop (owner attention, perceived quality) that may belong inside.
- **Validity.** SD builds confidence for a purpose; control identifies numbers with uncertainty. Each
  model claim is held to the stronger test that applies to it.
- **Policy versus controller.** SD's policy and control's controller are the same object, the rule that
  sets a flow from information; SD asks what behaviour it produces in the whole system, control asks
  whether its loop is stable, fast and robust. Both questions are asked of every decision rule.
- **What control has that SD lacks**: protection layers, modes and state logic, alarms, and
  management of change. **What SD has that control lacks**: the conserved chains of work and the
  feedback through the organisation's own perceptions and pressures. The Coordinator lives in both.

## 6. The checklist

A Coordinator design note (01 onwards in this folder, after this one and the terminology) is reviewed
against these. For each it says **done**, **not applicable (why)**, or **open**. It ships the
deliverables in their usual form.

**Deliverables expected, in order.**

1. Problem statement and reference modes from the record (SD-1 to SD-4).
2. Model boundary chart; variable list with CV, MV, DV roles (SD-6, CE-1 to CE-3).
3. Functional specification: objectives with numbers, constraints hard or soft, priorities (CE-4 to
   CE-6); losses, hazards and constraints (ST-1).
4. Dynamic hypothesis: CLDs with named loops, stock and flow maps, policy structure diagrams (SD-5,
   SD-7, SD-8).
5. Control structure diagram with layers and time scales; STPA control structure (CE-7 to CE-9, ST-2).
6. Pairing table (CE-10 to CE-12).
7. Loop sheets (CE-13 to CE-17); state diagrams, mode table, supervisor specification (CE-18 to CE-21).
8. Hazard register, cause and effect matrix for permissives, interlocks and trips; unsafe control
   actions table (CE-22 to CE-26, ST-3, ST-4).
9. Alarm philosophy and the owner's interruption budget; display hierarchy; the owner's typed acts
   (CE-27 to CE-30, HU-1 to HU-3).
10. Variety account per regulator (AV-1 to AV-4).
11. Model and parameter table, identification reports (SD-9 to SD-12, CE-31 to CE-33).
12. Test report per Table 21-4, fit with Theil's breakdown, sensitivity (SD-13 to SD-17).
13. Policy table across scenarios (SD-18 to SD-20).
14. Change classes and authorisation; when a change reaches running work (CE-35 to CE-38).
15. Performance monitoring in operation (CE-34); incidents analysed with CAST (ST-5).

**The questions most often failed**, from the parity notes and the review of the modelling subsystem
([parity/00-modeling-review.md](../parity/00-modeling-review.md)), to be read first:

- SD-2 and SD-5: no reference mode and no dynamic hypothesis before a change is fitted.
- SD-15: judging a model change by one scalar over the whole model.
- CE-5: setpoints and constraints not told apart (goals and the owner's rules in one mechanism).
- CE-8: no stated time-scale separation between the Coordinator's changes and the work they change.
- CE-23: the protective check living inside the block it protects against.
- CE-27: interruptions of the owner with no defined response or budget.
- AV-2: rules replacing judgement without saying which disturbances they leave uncovered.

## 7. To check against the source before quoting

- Sterman, ch. 3: Table 3-1 is the source of the step names used in 2.1 to 2.5; the exact sub-step
  wording should be quoted from the book.
- Sterman, ch. 21, Table 21-4: the test names are as given; the question column above paraphrases.
- ISA-88: the names of the example modes (automatic, semi-automatic, manual) and of the states are
  given from memory of Part 1; quote them from the standard.
- ISA-18.2: the alarm-rate figures (6 and 12 an hour; flood above 10 in 10 minutes) are as commonly
  quoted from its performance table; confirm against the current edition.
- Seborg et al.: the hierarchy of process control activities is in ch. 1; chapter numbers for the
  other topics vary by edition and are not given.
- OSHA 1910.119: paragraph (l) is management of change and (i) pre-startup safety review.

## Sources

Listed in [docs/READING.md](../../READING.md), with these beyond it: Forrester and Senge (1980);
Sterman (1984); Graham (1980); Barlas (1996); Oliva (2003); Rahmandad and Sterman (2012); Morecroft
(1985); Bristol (1966); Skogestad (2000, 2003, 2004); Desborough and Harris (1992); Ramadge and Wonham
(1987); CCPS, *Layer of Protection Analysis* (2001) and *Guidelines for the Management of Change for
Process Safety* (2008); OSHA 29 CFR 1910.119; IEC 61882 (HAZOP); ISA-5.1 and ISA-5.4; ISA-95 (IEC
62264); EEMUA 191; Leveson and Thomas, *STPA Handbook* (2018); Conant and Ashby (1970); Francis and
Wonham (1976); Sheridan and Verplank (1978); Parasuraman, Sheridan and Wickens (2000); Bainbridge
(1983); Lee and See (2004).
