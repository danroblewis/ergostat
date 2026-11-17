# 16. Reporting truthfully

Status: exploration, 2026-11-17. One of sixteen ([harness-as-control-system.md](../harness-as-control-system.md) §5,
function 16; [harness-parity-plan.md](../harness-parity-plan.md) §2.16 and its §4 log). It judges the claims built
last night (SPEC §12g) and proposes where the Coordinator's truthfulness should live in a model instead.

## 1. What the harness does, and why it is worth having

For the owner, the long session is the state estimator: what the owner believes about the project is mostly what
the session said. So the session's reports are the owner's sensor, and the owner's outer loop (what to ask for next,
what to accept, when to intervene) is only as good as that sensor. Pushing with failing tests, or calling something
built that was half built, did not just produce one bad report; it moved the owner's picture away from the
project, and every later decision was made on the wrong picture.

Taken apart, what a Coordinator does when it reports well is four different things:

- **Integrity of a reading.** It says what it saw, not what it hoped: "tests pass" because the exit code was read,
  not because the summary scrolled by. This comes from the context window holding the tool output right next to the
  sentence being written, and from training toward honesty and toward separating verified from assumed ("I ran it";
  "I did not check the UI"). It fails exactly where the window holds something misleading (`pytest | tail` exits 0).
- **Validity of the measure.** It notices when the thing it measured is not the thing wanted: the tests pass but
  test the wrong thing; the fit improved and the page is still unusable. This comes from holding the owner's words
  and the work in one context, so the gap between them is visible while working. This is where an agent can
  identify a goal mid-work that nobody wrote down.
- **Selection.** Of everything true, it picks what the owner needs at the level the owner needs it, and leaves the
  rest available. It answers "where are we?" with three lines, not three hundred.
- **Calibration.** It marks how sure it is: done, done but untested, probably done, not known. And it corrects
  itself later ("I said X earlier; it was wrong").

The first is per-statement honesty, which the owner suspects is hard or infeasible to guarantee per item. The other
three are, for a Coordinator, what a control engineer would call metric quality and display design. That reframing
is the core of this note.

## 2. Classical parallels

**Sensor validation and fault detection and isolation (FDI).** Control engineering never trusts one sensor it
cannot check. Hardware redundancy (two or three sensors, voting), analytical redundancy (a model predicts what the
sensor should read; the difference is a *residual*), parity equations (relations that hold among measurements when
nothing is faulty: the parity space), and plausibility limits. A residual over its threshold is a detected fault;
which residual fired isolates it. ergostat's claim checks are hardware redundancy: an independent second instrument
re-reads what the block said.

**Data reconciliation and gross-error detection** (the process industries). Flows into and out of a unit must
balance; measurements that do not are adjusted by least squares, and one that cannot be reconciled is flagged as a
gross error. A block that says it moved 12 while the stock it drains fell by 3 is a gross error.

**Quality flags and provenance** (SCADA, OPC UA). Every value travels with a status (good, uncertain, bad), a
timestamp and its source (measured, substituted, manual, estimated). The display shows a substituted value
differently from a measured one. This is calibration, made structural.

**The rework cycle and the 90% syndrome** (system dynamics: Cooper; Ford and Sterman, including their paper on
concealing rework, "the liar's club"). Work done flows into *work believed done*, but a fraction of it carries
undiscovered flaws, which sit in a stock of **undiscovered rework** until testing, review or use finds them and
sends them back. Reported progress counts the undiscovered rework as done, so it runs ahead of real progress, and
the project sits at "90% done" for a long time. The gap between perceived and actual progress is a stock; it is
drained by discovery, whose rate depends on how much checking is done and with what delay. This is the closest
classical model of the harness's failure: overstatement is not one lie; it is an accumulation of unchecked "done".
It is also SD's perceived-versus-actual stock (MODELLING.md §4, a decision on the true value).

**Goodhart's law and surrogation; eroding goals.** A measure held as a target drifts away from what it stood for;
the eroding-goals archetype lowers the setpoint to meet performance. Good modelling of setpoints means measures
chosen, and checked, for their validity.

**Alarm management and high-performance displays** (ISA-18.2, EEMUA 191, ISA-101). Report only what needs action,
rationalise alarms, show overview first and detail on demand. This is selection.

**Where they fall short.** FDI assumes a known fault class (bias, drift, stuck) and a model of the sensor; an
agent's report is open text with no bounded fault class. Reconciliation needs a balance to hold; most of a
Coordinator's statements are not quantities. The rework cycle estimates how much is hidden, never which item. And
alarm rationalisation is done offline by engineers; the harness re-selects for every question. The harness's honesty
generalises to statements no check exists for. ergostat cannot copy that; it can make sure that what is reported is
mostly things the model measured, flagged by how they were known.

## 3. What ergostat already has

Honestly, quite a lot, and not mostly in the claims:

- **Measured versus set.** A sensor's reading is shown as measured; an auxiliary a block sets is shown as set by it
  (SPEC §6). That is provenance already.
- **Commanded versus moved** (SPEC §9.1): the gap between what a controller asked and what a block reports it
  moved is recorded as evidence of saturation. With the stock's own sensor it is a reconciliation.
- **Residuals** (`ergostat.model.unexplained`, §12e): a stock's change its flows do not explain. A block that
  reports flow it did not move shows up here; this is analytical redundancy.
- **The prediction check** (§12f.4): every change written to the model is re-judged on record it never saw. The
  model's own statements about the world are tested. This is the strongest truthfulness in ergostat.
- **Item state reached through a checked tool.** image-squeeze's `lab.py submit` commits, runs the tests itself and
  abandons the hypothesis when they fail; the `testing` state cannot be reached with failing tests. The developer
  cannot misreport this, because the report and the act are the same call and the call carries its test. This is
  exactly the owner's "translate the claim into a test in the artifact", and it predates claims.
- **Claims and trust** (§12g, built last night): a block's `claim` line, checked by ergostat after the run, never by
  the claimant; `tests` re-run where the claim says; unchecked never counted; trust as built-in measures by block,
  rung and model; a contradicted claim a finding.
- **The intent judge** (§12i): finished work judged against confirmed decisions and the owner's messages, and
  `ergostat.intent.false-done`, the share of accepted work the owner later found not done, with its tests-alone
  twin. That second measure is the rework cycle's discovered-after-acceptance flow, already counted.
- **Goal status with hysteresis, findings, needs-attention**: the start of a display.

### Judging the claims

The design follows the right principle (the check belongs to the model, not to the one being checked; FDI's
independence), and the `tests` check catches a real failure from this project's history. But:

1. **Most checks restate the record.** `state`, `exit`, `level` and most of `changed` compare a sentence about the
   record with the record. Where the effect is already recorded, the claim adds a sentence and a regex. Only `tests`
   and declared checks measure the world afresh, and those are better placed on the transition itself (as
   `lab.py submit` does), where the false state cannot be entered at all, instead of after the run, when the item
   has already moved and every reader has seen it.
2. **Silence scores best.** A block that claims nothing is never contradicted; the contradiction rate depends on
   what the block chose to say. As a trust measure it is biased toward the quiet.
3. **The goal it feeds has no loop.** `developer-honest` in image-squeeze is held by nothing (its own description
   says so): missing feedback by ergostat's own definition. A measure with no actuator is a dashboard tile, which is
   fine, but then it should be modelled as one, not as a goal.
4. **Classification by words** is the rule rung parsing free text, brittle both ways.
5. It is per-item truthfulness, which the owner rightly doubts can be the foundation.

Claims are worth keeping where the owner pointed: AI blocks with a review step, where an AI's own statement of what
it did is a useful brief for the reviewer and a cheap first check. They are not the core of reporting.

## 4. Candidate designs

### A. The rework cycle, with an observer of what is hidden

Model "done" as SD models it: every completable kind's acceptance flow fills *reported done*; a fraction of it is
undiscovered rework; discovery flows (a test that fails later, the intent judge holding it, the owner reopening it,
a correction naming it) drain it into *known rework*, which returns to the work queue. Undiscovered rework is not
measurable; it is **estimated**, by an observer whose parameters (the rework fraction and the time to discover)
are identified from the record: how much accepted work came back, and how long after. The report then shows done
and, beside it, the expected share still to come back, the 90% syndrome made visible.

A balancing loop closes on it: when the estimated hidden rework rises past its goal, checking effort rises (review
depth, the intent judge's model, which claims are re-tested, how much of a sample the owner is asked to look at).
That is the one place the trust measure becomes a valve (2.10's dynamic adjustment of delegation reads the same
estimate).

- **Ladder:** rule and program (an `expr` for the estimate, a `proportional` or `onoff` controller on review
  depth); nothing here needs AI.
- **Drawn:** SD view, the aging chain work queue → reported done → (discovery) → known rework → work queue, with
  the hidden stock as an auxiliary drawn dashed (estimated); control view, an observer block feeding a controller
  whose actuator is checking effort, the discovery flow the feedback path.
- **Modeling subsystem:** fits the rework fraction and discovery time like any parameter (§12b), judged on held-out
  record; proposes splitting by kind or block where one fraction fits badly. Neighbourhood: the kind's chain and its
  checks. It never pauses running work; the estimate updates every reading, the parameters change by proposal.
- **Measured:** the observer's calibration (predicted come-backs over a month against those that came back);
  `ergostat.intent.false-done` held below its goal; on the parity benchmark, the session's two failing-test pushes
  and its overstated builds replayed as accepted work that came back.

```yaml
# a sketch, for one completable kind (hypothesis); names illustrative
parameters:
  rework-fraction: {value: 0.1, unit: share, estimate: true}     # identified from what came back
  time-to-discover: {value: 2d, estimate: true}
stocks:
  reported-done:
    unit: hypotheses
    sensor: {items: hypothesis, state: kept}
  known-rework:
    unit: hypotheses
    sensor: {items: hypothesis, state: proposed, where: {reopened: true}}
flows:
  accepted: {from: experiments, to: reported-done}
  rework-found:                                   # tests later, the intent judge, the owner's reopen or correction
    from: reported-done
    to: known-rework
    sensor: {items: hypothesis, entering: proposed, where: {reopened: true}, over: 1d}
auxiliaries:
  hidden-rework:                                  # the observer: not measured, estimated (drawn dashed)
    unit: hypotheses
    driven-by: [+flow.accepted, -flow.rework-found]
    equation: flow.accepted * rework-fraction * time-to-discover
  review-depth: {unit: share}                     # read by the intent judge and the claim checks
goals:
  little-hidden:
    auxiliary: hidden-rework
    hold: "<= 1"
blocks:
  check-harder:
    type: proportional
    goal: little-hidden
    gain: 0.2
    min: 0.1
    max: 1
    out: auxiliary.review-depth
```

### B. Interlocked transitions: the claim becomes a test before the state

Generalise `lab.py submit`. A state of a kind that *asserts a fact* ("testing" asserts the tests pass; "deployed"
asserts the health check answers) is reached only through a flow whose valve is a check the model owns: a
permissive interlock in control terms, a quality gate in SD terms (the flow splits into passed and sent back, a
coflow of rejects). The worker asks; the check decides; the event that moves the item comes from the check, not the
worker. Then "submitted with tests passing" is not something anyone can say falsely, because no one says it.

Where the test lives is the owner's open choice and the design allows all three: a test file in the work artifact
(the worker's own artifact carries its acceptance test, run by the gate); a sensor in a loop (the gate reads a
measure, a benchmark score above production's); or a test written when the done-when was set, before the work, by
whoever played the Coordinator. A test the worker writes for its own work is not independent, so it is a proposal:
new tests and new sensors are changes to the model, and go through the modeling subsystem and its judge. This is
where "agents identify goals mid-work" lands: an AI block proposes the test or the goal it discovered; it is not
adopted on its say-so.

- **Ladder:** program (the gate) and rule (the split); the AI block only asks.
- **Drawn:** SD, a valve on the transition flow with an information link from the check, and a reject outflow;
  control, an interlock block between the worker (actuator) and the process.
- **Measured:** the share of a kind's fact-asserting states reached through a gate (coverage); rejects at the gate
  against come-backs after it (if come-backs stay high, the gate tests the wrong thing: input to design C).

### C. Metric validity, as analytical redundancy for goals

A goal's measure is a sensor for what the owner wants; the owner's reopens, corrections, unhappy messages and the
intent judge's held verdicts are a second, independent, noisy sensor of the same thing. When a goal reports holding
while the second sensor says not, that is a residual: the measure is suspect (Goodhart, or a setpoint that drifted).
The residual is a finding about the goal's neighbourhood (the goal, its sensor, the flows it closes through), and the
modeling subsystem's job is to propose the fix: a different sensor, a second goal, a guard. Until it does, the goal's
status is shown **uncertain**, a quality flag, which changes no model and needs no pause.

- **Ladder:** the residual is a rule; the proposal is a narrow AI or AI agent block focused on that neighbourhood.
- **Measured:** suspect goals found and then fixed by an accepted change; time a goal spends holding while the
  owner disagrees.

### D. The report as a display with quality flags

Every number and status shown to the owner carries how it was known: measured by a sensor, set by a block, checked
by ergostat, claimed and unchecked, estimated by an observer. The Coordinator's "summary" is then a selection over
goals, findings and the hidden-rework estimates, with what changed since the owner last looked, rationalised like
alarms. The display's own refinement (which questions it failed to answer) is 2.11's and 2.4's (status questions as
a disturbance category feeding a dashboarding loop), so here only the flags: reporting truthfully means a display
that never shows a claimed value as a measured one.

## 5. Recommendation

Build **A** and **B** as the core, feed **C** to the modeling subsystem, and leave **D**'s display to 2.11 with
one requirement from here: provenance flags on everything shown.

Reasons. A puts the harness's real failure, an accumulation of unchecked "done", into a stock the disciplines
already know how to analyse, and estimates the part of truthfulness no per-item check can reach. B removes the most
damaging false reports by construction, on the lowest rungs, and is already proven in image-squeeze. C is the only
one that addresses whether the metrics measure what is wanted, which for a Coordinator is most of what reporting
truthfully means. None of them needs a new item kind, field or block type: A and C are stocks, flows, auxiliaries,
parameters, a goal and a built-in controller; B is a flow with a valve and an outflow, plus a convention that a
fact-asserting state is moved only by its check.

On the old plan's build and last night's work:

- **Keep** the claim line and the `tests` re-run as an optional sensor for AI blocks with a review step: its brief
  for the reviewer, and the pipe-hid-the-exit-code check. Keep the independence rule (a claim is never checked by
  its own command).
- **Change** the claims' role: a claim kind that recurs is a candidate gate. The modeling subsystem should propose
  turning it into a check on the transition (design B), after which the claim is redundant there. Change the
  measure of parity from contradicted claims per worker to the rework-cycle measures: come-backs after acceptance
  (`ergostat.intent.false-done`, already built), the observer's calibration, gate coverage, and suspect-goal time.
- **Retract** "a contradicted claim lowers its trust" as the mechanism, until trust drives a valve (A's check-harder,
  2.10); retract `developer-honest` as a goal with nothing serving it: either wire it to review depth, or show it as a
  monitored value, not a goal. Retract the regex classification as anything more than a fallback; a gate names its
  check.
- The intent judge (§12i) is part of A: one of its discovery flows. Its false-done measure is the most important
  thing built last night for this gap.

## 6. Open questions for the owner

- Should a state that asserts a fact be reachable only through a model-owned check, as a rule ergostat enforces, or
  stay a pattern projects choose?
- Where should the acceptance test usually come from: the work artifact, a sensor in a loop, or whoever sets the
  done-when before the work starts?
- Is an estimated (unmeasured) stock like hidden rework acceptable on the owner's displays, drawn as an estimate?
- Should a test or goal an agent discovers mid-work go through the modeling subsystem's judge before it gates
  anything, or apply at once to that agent's own item?
- Should claims stay built in, or move to a library part for projects with AI blocks and review?
- Is a goal that nothing serves (a monitored value) a legitimate thing to keep, or should check always insist on a loop?
