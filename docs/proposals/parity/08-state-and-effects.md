# 2.8 Checking state before acting, and effects after

Status: exploration, 2026-11-17. One of sixteen gap studies for harness parity
([harness-as-control-system.md](../harness-as-control-system.md) function 8;
[harness-parity-plan.md](../harness-parity-plan.md) §2.8). It replaces that section's "Build" with control
structure. Nothing here is built.

## 1. What the harness does, and why it is worth having

The long session did three different things that the plan folded into one line.

1. **It read the state it was about to act on, at the moment of acting.** `git status` and `git log main`
   before a merge, `pgrep` before concluding that a run had died, reading a file before editing it, opening
   the screenshot before believing an agent that said the layout was fixed. The reading happened *just
   before* the action, not when the task was handed over, so it saw what had moved in between: another
   agent's merge, a run that had in fact finished, a file someone had changed.
2. **It formed an expectation of what its action would do.** Every command was issued with a prediction
   in the context window: the merge applies cleanly, the test count goes from 561 to 562, the run's
   process disappears, the page shows two panes. The prediction is rarely written down, but it is there,
   because the next step was planned on it.
3. **It compared what happened with what it expected, and acted on the difference.** A match moved it on
   at once, without ceremony. A mismatch surprised it, and surprise changed what it did next: it stopped
   building on the result, looked harder (a second check, a diagnosis: function 6), and sometimes changed
   its picture of the system (that pipes hide exit codes; that one test is flaky). Then it checked more
   carefully for a while.

The value is not the checking alone, which any script can do; it is the pairing of a **prediction made at
action time** with a **measurement afterwards**, the difference **routed** either to "the action went wrong"
or to "my picture of the system is wrong", and the depth of later checking **raised by surprise**. All of
it comes from the context window (the action, its intended effect and the current picture sit in the same
few thousand tokens) and from training (habits of verifying before claiming, re-reading before editing).
It is also discretionary, which is its weakness: twice the session pushed with failing tests because a
pipe hid the exit code. The prediction was there; the measurement was wrong, and nothing outside the
session checked the measurement.

## 2. The classical parallels, and where they fall short

The owner's reading is right: this is mostly ordinary control, and the terms exist.

- **Sensors and sampled-data control.** Acting on a fresh sample, and reading again after the actuator has
  moved, is what every digital controller does. The age of the reading a controller acts on is part of
  the loop's **dead time**; a long AI run is a controller with a very long sample-and-hold. System
  dynamics says the same thing with the **Baker criterion** and **information delays**: a decision can use
  only what the decision maker could see, and when.
- **Permissives and interlocks** (process control, PLC sequences): a start command is honoured only while
  its permissive conditions read true *now* (the valve is shut, the tank is not full). A sequential
  function chart's transition fires only when its condition holds. This is "check state before acting",
  enforced at the actuator rather than remembered by the operator.
- **Proof of operation, or command discrepancy** (DCS and motor control): a pump commanded on must show
  its run feedback within a proving time, or a "failed to start" alarm is raised and the sequence stops; a
  control valve whose position feedback departs from its demand raises a travel-deviation alarm. This is
  "check effects after" for a single actuator.
- **The observer and its innovation** (Luenberger, Kalman): an estimator predicts the next measurement
  from the model and the input it just applied; the measured minus the predicted is the **innovation**. A
  well-tuned filter's innovations are small and white; a normalised innovation squared persistently above
  its expected value means the model or the plant has changed. The owner's idea of comparing a
  projection's error with the outcome *is* this.
- **Fault detection and isolation** (residual generation, analytical redundancy, parity relations): several
  residuals compared so that a fault can be *isolated*: was it the actuator, the sensor, or the model? This
  is the harness's routing of a surprise into "the action went wrong" or "my picture is wrong".
- **Adaptive sampling and CUSUM change detection**: sample harder, or alarm, once accumulated evidence of a
  shift passes a threshold. That is "check more carefully for a while after a surprise".

Where they fall short of the harness: each classical check is designed per actuator, by an engineer, for
effects known in advance. The harness invents the check from the meaning of the action (a merge has
effects on main, on other branches, on running sessions), so its "sensor set" is open. Its observer's model
is semantic, not a transfer function. And it isolates faults with judgement, often with one sample. The
parity question is therefore not "add sensors" but: who decides which effects an action has, which of them
get measured, what the expectation is, and where the difference goes.

## 3. What ergostat already has

More than the old plan said.

- **Fresh readings.** A commanded machine block runs once per fresh reading and never outruns its sensors;
  when it moves a flow, that flow's stocks are read at once (SPEC §9.3). A fresh start acts only on a recent
  reading (`runner.py`). That is sampled-data control done properly for short runs.
- **Commanded versus moved** is recorded per run (`block.commanded`, the moved line; §9.3), as the evidence
  of saturation. It is the block's own word for what moved, though, not a sensor's.
- **The controller's own delay** (how old its reading is and how long its run takes) is added to the
  loop's dead time in analysis (§12d). The staleness of a long run is already in the numbers, not yet in
  any check.
- **Claims** (§12g): what a block says it did is checked by ergostat after the run, against the record and
  the world (tests rerun on the commit, git, item state, a stock's level), never by the claimant. This is
  "effects after", guaranteed, for the effects a block chooses to claim. The pipe case is the test.
- **The intent judge** (§12i): finished work judged against what the owner meant, after the fact.
- **Proof of operation, in one place**: during a step test, a block that moves anything but what it was
  commanded stops the test and the setting is put back (§12d).
- **A precondition at the record**: a changeset's JSON Patch `test` operation refuses the whole event when
  the state it assumed does not hold (§5a). That is a permissive, at the fold.
- **A prediction check, for one kind of action**: every change written to the model is judged on record it
  has not seen, and after three hold-outs checked again against the model without it (`verified`,
  `regressed`; §12e, §12f.4). That is innovation monitoring, but only for actions on the model.
- **Residuals** (MODELLING.md): a stock's change its flows do not explain, read as evidence of a missing
  flow or a bad sensor.
- **The `state` recipe part** (§12j, `recipes/parts.py`): what moved on main, uncommitted files, what is
  running, open findings, at the start of a session.

What is missing:

1. **No expectation per action.** Projection (§12b) is open loop and leaves out exactly the flows a block
   sets, so no prediction exists of what *this run* should do. Without one, the after-check can only test
   what the block claimed, which is the block's own list of effects. Effects it did not claim, and effects
   it caused but did not intend, are seen only as residuals, later, unattributed.
2. **The before-check sits at the wrong moment.** `state` is read when the session starts; the action (a
   merge, a submit, an item moved) happens minutes or an hour later. The benchmark agrees: adding `state`
   did not help (0.604 against 0.625), and state was the weakest kind of question. The state that matters
   is the one at actuation, and nothing reads it then except the agent, at its discretion.
3. **No isolation.** A contradicted claim is a finding against the block; a residual is a finding against
   the model; nothing relates the two, so a surprise is not routed to diagnosis (2.6) or to modelling
   (§12e) by evidence.
4. **No adaptive depth from surprise.** `review:` rules read trust (§12j), a week-long share; nothing
   raises the depth after one surprising run.

## 4. Candidate designs, as control structure

### A. Permissive at the actuator: move the act out of the AI block

Complexity hidden in a block is the smell here. An AI block that "does the work and merges it" contains a
valve (the merge) and its permissive (main has not moved under it, the result still passes) where nobody
can see them. Split it: the AI block produces a candidate (a branch, a draft, a proposed item move); the
candidates are a **stock**; a **valve on the program rung** moves them out (merge, deploy, submit), and it
opens only while its **permissive** holds on readings taken *now*: the candidate's base is still main's
head, or the tests have been rerun on the merged result; the item is still in the state the work assumed.
A candidate that fails it leaves by another flow (back to rebase, to the AI or to a program), never
silently.

- Stocks: candidates waiting, candidates gone stale. Flows: submitted, actuated, sent back stale.
  Valve: the actuator; information links from the sensors the permissive reads; a balancing loop on the
  stale stock (rebasing drains it).
- Ladder: the permissive is a rule (`compare`), the actuator a program. The AI block's own before-checks
  stay inside its harness, which is not the question.
- Drawn: in SD, a queue between the agent and main with a valve and its information links; in the control
  view, the permissive as a gate block in front of the actuator, the way an interlock is drawn.
- This is the merge queue of 2.14 seen from its other side; the part should be one library part, shared.
- Measured: actions applied on moved state (merge conflicts, duplicate work, an item moved twice) falls
  to the rate the permissive misses; the stale flow says how often the agent would have acted on old state.

### B. Proof of operation per run (command against sensed effect)

For every machine block that moves a flow, ergostat already knows what it was commanded and what it said it
moved; add the third leg, what the flow's own sensor saw move, over a **proving time** taken from the
loop's identified dead time and time constant (§12d), or declared until one is identified. The
discrepancy is a built-in measure, parameterised like trust (`@block`), read by a sensor into an auxiliary;
an `alarm` on it is the "failed to act" alarm, and its findings go into the diagnosis queue (2.6).

- No new kind: three readings, a `timer`, an `alarm`, a goal on the gap.
- Ladder: rule.
- Drawn: in the control view, the actuator's feedback line closing back on its own command (a local
  position loop); in SD, the gap as an auxiliary between the valve and the flow's sensor.
- Measured: runs with a proven effect / runs; detection latency of a run that moved nothing.
- Limit: it sees only effects on flows the model has. Most of an AI block's effects are not flows.

### C. The innovation monitor (an observer over the neighbourhood of each action)

Generalise the prediction check of §12f.4 from actions on the model to every action. When a block's run
begins, ergostat makes the projection it already makes, but closed over this run: the flows the block
sets carry their command, and the horizon is the proving time. When the horizon passes, the innovation of
each stock and flow in the run's **neighbourhood** (the parts its flows reach within one or two links, the
items it named) is the reading minus the projection, scaled by the noise the identification measured. The
innovations are series; a goal holds their normalised size near what noise explains; CUSUM over them
says when a shift is real.

Isolation, by pattern, not by a block's judgement:

- innovation on this run's own flows and a contradicted or missing claim: **the action failed**, to the
  diagnosis queue (2.6), with the evidence;
- the same innovation across many runs and blocks on the same parts: **the model is wrong**, to the
  modelling subsystem's input with that neighbourhood;
- innovation on parts the run was not expected to touch: **a side effect or an unmodelled link**, also to
  modelling, as evidence for a `driven-by` or a missing flow;
- a single jump with no structure: a sensor reading to set aside (MODELLING.md already says so).

Surprise sets depth: the latest innovation of a block is a measure `review:` can read beside trust, so a
surprising run gets the deeper review at once, and depth decays back as innovations shrink (gain
scheduling of verification by a fast signal, trust being the slow one).

- Ladder: the projection and the innovations are program; the isolation rules are rules; only what lands
  in diagnosis or modelling may meet an AI.
- Drawn: in the control view, the observer as the classical block parallel to the plant, its innovation
  line into a fault-isolation block with two outputs (to diagnosis, to modelling); in SD, the innovations
  as auxiliaries on the parts, and two information links out.
- Measured: escaped effects (an effect found later, by the owner, a reopened item, a regressed change,
  that no innovation flagged within its horizon), false alarms, and calibration (normalised innovations
  averaging about one means the model's expectations are honest).

### D. State delivered to running work, on change (send on delta)

Instead of a snapshot in the brief that ages, the neighbourhood of a running block's item is watched, and a
change to it (main moved under its branch, a sibling merged into the same files, the item was moved by
someone else) is sent into the running session as a message from ergostat (§12h delivers live). This is an
event-triggered observer update: the brief's state is the initial estimate, and corrections arrive only
when the estimate is off. It is cheap, it uses what was built last night, and it makes A's permissive fail
less often, because the agent rebased before it submitted. It is the same channel 2.4 and 2.14 use.

### The strongest, sketched

C on top of A, with B as C's degenerate case for flows. In image-squeeze's terms:

```yaml
include: [parts/permissive-actuator.yaml, parts/innovation.yaml]   # library parts, shared by every actuator

stocks:
  candidates:                       # what the developer built, waiting for the merge valve
    unit: branches
    sensor: {items: hypothesis, state: testing}
  stale-candidates:                 # their base is no longer main's head
    unit: branches
    sensor: {items: hypothesis, state: testing, where: {base_current: false}}
flows:
  merging:
    from: candidates
    sensor: {items: hypothesis, entering: kept}
auxiliaries:
  developer-innovation:             # this run's neighbourhood: measured minus projected, over noise
    unit: "1"
    sensor: {builtin: "ergostat.innovation@developer", every: 30s}
goals:
  developer-predictable:
    auxiliary: developer-innovation
    hold: "<= 2"
blocks:
  base-current:                     # the permissive: rule rung, read at the moment of acting
    type: compare
    in: stock.stale-candidates
    below: 1
  merger:                           # the valve, program rung; the AI never merges
    type: program
    run: bin/py lab.py merge-next
    in: block.base-current
    out: flow.merging
  developer:
    type: ai
    context: worker
    review:
      - when: "innovation > 2"      # surprise: deep review now
        by: reviewer
        depth: deep
      - when: "contradicted > 0.3"  # trust: the slow signal
        by: reviewer
      - by: none
```

## 5. The modelling subsystem's part, and the rate of change

The after-checks are sensors, so choosing them is a change to the model, and only modelling makes it. The
innovation monitor gives modelling what it lacks today: evidence localised to a **neighbourhood** (the
parts an action touched and where the surprise landed), already isolated from action failures. Its
proposals are the usual ones (a flow, a `driven-by`, a parameter, a delay) plus the one this gap adds:
**observability**, a sensor or a declared claim check where actions keep having effects nothing measures.
They are judged by the existing judge on held-out record.

Rate of change: innovation evidence accumulates over many runs; a single surprise never changes the model.
Modelling acts between runs, on the neighbourhood, and its changes reach a block at its next run (as tuning
already does). Running work is not paused for modelling. What does pause running work is the permissive and
the "failed to act" alarm, which are interlocks on the actuator, not model changes; how far a trip
propagates (this actuator, its loop, its system) is 2.5's question.

## 6. Recommendation

Build **A** first, as a library part with 2.14 (one merge-queue-shaped part, not two), because it moves
the most important before-check out of agent discretion at no AI cost, and the record shows the failures it
prevents. Then **C**, starting with B's narrow case (flows the model has, where the projection and the
identification already exist), widening to the neighbourhood once A's candidates and items give it more to
measure. Use **D** as the cheap complement that keeps A's stale flow small. Measure parity on this project's
record: how often the long session read state before a merge and what it caught (from the transcript),
against the permissive's stale flow; how often its after-checks caught a fault, against innovations and
claims; and escaped effects for both.

On the old plan's Build for 2.8:

- **Keep:** the after-check run by ergostat, never left to the worker. It exists as claims (§12g) and the
  intent judge (§12i), and C extends it from claimed effects to expected ones.
- **Change:** the current-state projection in every session's start. Keep the `state` part, but stop
  treating it as the before-check; it is the observer's initial estimate, refreshed by D, and the real
  before-check is A's permissive at actuation. Its content should be what is in flight on the item's
  neighbourhood and the owner's latest ask, which the benchmark asked for.
- **Retract:** a new "post-session check as a built-in judge mode" (C uses the projection, the
  identification and the judge's own hold-out logic, not a third judge); and the invented flows "started
  on stale state" and "effects claimed and missing", which become the permissive's stale flow and the
  existing contradicted-claims stock.
- **Last night's work:** claims stay the backbone (the third leg of B, the isolation signal in C); messages
  are D's channel; recipes' `review:` gains the fast signal. Nothing built needs undoing.

## 7. Open questions for the owner

- Should outward actions (merge, deploy, submit) always leave the AI block and pass a program-rung valve, or only where the record shows stale actions?
- Is a proving time declared per actuator acceptable until identification supplies one, or should the after-check wait for identification?
- When an innovation cannot be isolated (action or model), which way should it go by default: diagnosis or modelling?
- Should surprise raise review depth automatically, or only propose it as a model change for modelling to judge?
- Is the neighbourhood of an action (parts within one or two links, plus named items) the right unit for modelling's focus, or should it be the action's whole system?
