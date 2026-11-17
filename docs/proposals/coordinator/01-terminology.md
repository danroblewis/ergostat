# 01. Words

Status: reference, 2026-11-17. The second Coordinator note, after [00-oracle.md](00-oracle.md). It
takes every term ergostat uses (SPEC, CONCEPTS, the vocabulary) or the parity notes propose
([../parity/](../parity/)), and for each gives its standard meaning in system dynamics and in control
engineering (or none), whether ergostat's use **matches**, **collides** (the word has a standard
meaning and ergostat uses it for something else) or is **invented** (no standard meaning in either
field), and the word recommended, with the reason.

The rule it applies is SPEC §1's seventh principle, "no word means two things", widened to the owner's
standard: no word means something other than what a practitioner of either discipline would take it
to mean. Where the disciplines already have a word, use theirs. Where they do not, use plain English
and define it once. A collision is worse than an invention: a reader stops at a new word, and reads
straight past a familiar one.

The recommendations are for the docs and the parity work first. Renaming a YAML key or an event type
is a separate change, through the usual deprecation (`deprecated-name`, SPEC §12), and is noted where
it would follow.

## The five most important renames

1. **"Valve" for a controllable flow, an actuator, or any gating point → "actuator" in the control
   view, "rate equation" in the SD view; "valve" only for the glyph.** In SD every flow has a valve
   (the symbol where its rate equation lives), so "a flow with no valve is a disturbance" (CONCEPTS,
   vocabulary) contradicts the first thing an SD practitioner knows. In control a valve is one kind of
   final control element. The parity notes go further and call any decision point a valve ("the timing
   is itself a valve", "a VOI valve", "the agent as a trusted valve"), which neither field would
   recognise.
2. **"Decision" (four meanings) → "decision rule" only for SD's policy, which is the controller's law.**
   ergostat uses it for the owner's settled design choices (`ergostat.decision`), a rung of the ladder
   (`decision`), a block's log line (`{"decision": ...}`) and the controller ("the controller is the
   decision"). In SD a decision is the rate equation's policy (Forrester's decision functions,
   Sterman ch. 13). Rename: the owner's checkable rules → **constraints** (as parity 2.12 proposes), the
   rest → **design decision record**; the rung → **decision table**; the output line → **rationale**.
3. **"Invariant" for the owner's rules → "constraint" (hard or soft).** In control and in MPC the word
   is constraint; "invariant" has the precise meaning of an invariant set (a region the state never
   leaves once in it), which is a property to prove, not a rule to enforce. IEC 61511 and MPC give the
   vocabulary for enforcing one: soft constraint, hard constraint, permissive, interlock, trip.
4. **"Judge" (two built-in blocks) → "validation" for model changes, "acceptance inspection" for
   finished work.** Neither field has a judge. The model judge does what Ljung and Sterman call
   validation on data not used for fitting; the intent judge does what quality practice calls
   inspection against acceptance criteria. Two different jobs under one word, both renamed into the
   word their discipline uses.
5. **"Ladder" and "rung" → "tier".** A control engineer reads "ladder" and "rung" as ladder logic
   (IEC 61131-3's LD language, whose unit is the rung), the first thing a PLC programmer learns. The
   ergostat ladder is something else: the kinds of machine, ordered by cost and predictability. "Tier"
   says that and collides with nothing in either field. (Sheridan's "levels of automation" is not the
   replacement: it measures who has authority, human or machine, not which kind of machine does the
   work.)

Next in importance, below: **trust** (retire as a name; it is a human attitude in the literature),
**gate** (→ permissive, guard or hold point), **hold/held** (reserve for ISA-88's held state),
**projection** in "projection recipe" (collides with SD's projection, a forecast), and **tolerance**
(→ deadband).

## How the entries read

Each entry: **SD**: the standard meaning in system dynamics. **CE**: in control engineering (including
process-control practice and its standards). **ergostat**: how ergostat or the parity notes use it.
**Verdict**: match, collision, extension (the standard meaning, used more widely in a way a
practitioner would accept), or invented. **Use**: the word recommended, and why.

## 1. Keep

The word matches its standard meaning, or is plain English with no standard meaning to collide with.

| Term | SD | CE | ergostat | Verdict | Use |
|---|---|---|---|---|---|
| **stock** | A level: what accumulates, the integral of its flows (Sterman ch. 6) | A state variable; the plant's integrator | The same; "memory decides the kind" (SPEC §7a) | Match | Keep. SPEC's test (memory) is Sterman's |
| **flow** | A rate: inflow, outflow; a biflow runs both ways | A plant input or output rate | The same; `two-way` is the biflow | Match | Keep |
| **auxiliary** | A converter: computed from others at each moment, no memory | (an algebraic signal) | The same | Match | Keep. Retire `variable` as already planned |
| **connector**, **`driven-by`**, **polarity** | Information link with a sign (+/−); acts at once | Signal; the sign of a gain | `driven-by` is a signed causal link; "a connector acts at once" (SPEC §7) | Match | Keep. In prose say **causal link** for `driven-by` |
| **coflow** | Sterman ch. 12 | none | The same | Match | Keep |
| **exogenous**, **endogenous** | Outside / inside the feedback structure; the boundary chart's columns | Exogenous input | The same | Match | Keep, and use the boundary chart's third word, **excluded**, too |
| **delay** (material, information) | Sterman ch. 11 | Transport delay (dead time); lag | The same | Match | Keep. Say **dead time** in the control view, **delay** in the SD view |
| **controller** | (the policy's equation) | The designed block that turns error into command | Derived role of a block (SPEC §9.4) | Match | Keep |
| **actuator** | none | Final control element | Derived role: a block whose output is a flow | Match | Keep, and use it in place of "valve" (rename 1) |
| **setpoint**, **reference** | none ("goal" is SD's word) | r, SP | `goal.x` as a reference is "the goal's setpoint (r)" | Match | Keep, for the value; see **goal** |
| **error** | Discrepancy, gap | e = r − y | `goal.x.error` | Match | Keep. Say **gap** in the SD view |
| **disturbance** | Exogenous input | An input that moves the output and is not manipulated | Any flow on the goal's stock not set by the loop's controller (SPEC §7) | Match | Keep; see the note under "define carefully" for flows set by other loops |
| **feedback loop**, **reinforcing**, **balancing** | Any closed causal cycle, R or B | Positive or negative feedback | §12a's loops | Match | Keep, always as **feedback loop** when the SD sense is meant (see **loop**) |
| **cascade** | (nested structure) | Primary sets the secondary's setpoint | `out: goal.X` | Match | Keep |
| **feedback**, **open loop** | Same | Same | Same | Match | Keep |
| **saturation**, **anti-windup** | none | Actuator at its limit; stopping integration there | Commanded against moved; a held command (SPEC §9.1) | Match | Keep. Note that "a command held, not queued" is anti-windup only in the loose sense; see **define carefully** |
| **identification**, **step test**, **SIMC**, **margins**, **Harris index** | (calibration) | Ljung; Skogestad; Desborough and Harris | §12d | Match | Keep |
| **observer**, **innovation**, **residual** | (residual: data minus model) | Luenberger, Kalman; FDI | Parity 2.8, 2.10, 2.16 | Match | Keep, and use only in these senses |
| **permissive**, **interlock**, **trip**, **bypass** | none | IEC 61511 and PLC practice (00-oracle §3.7) | Parity 2.3, 2.5, 2.8, 2.12, 2.14 | Match | Keep, exactly as IEC 61511 uses them. Do not let them drift into synonyms of each other |
| **rework**, **undiscovered rework**, **rework cycle** | Cooper; Ford and Sterman: work done splits by a quality fraction into really done and undiscovered rework, found after a discovery delay | none | Parity 2.2, 2.6, 2.10, 2.16 | Match | Keep, with the full structure (quality fraction, discovery rate) whenever it is drawn |
| **gain scheduling**, **override (selector)**, **feedforward** (on a measured disturbance) | none | Standard | `select` block; parity notes | Match | Keep. See **feedforward** under "define carefully" for the stretched use |
| **reference mode**, **dynamic hypothesis**, **boundary chart** | Sterman ch. 3 | (data for identification) | 00-modeling-review | Match | Keep, and produce them (00-oracle §2) |
| **sensor** | none (an information link implies a measurement) | Transmitter: measures one variable | An instrument inside one stock or flow; never acts (SPEC §6) | Match (CE), extension (SD) | Keep. In the SD view, a perceived value with a lag is a stock, not a sensor setting (MODELLING.md §4) |
| **finding** | none | none | What `check` reports | Invented, plain | Keep |
| **measure** | none | none | A built-in quantity a sensor can read | Plain | Keep |
| **item** | none (SD aggregates items into stocks) | none (DES: an entity) | Every event about one id, folded (SPEC §5a) | Plain; matches Kanban's work item | Keep |
| **message** | none | (an operator input) | The owner's words, routed to work in flight (SPEC §12h) | Plain | Keep; its classes are named in control terms under "define carefully" |
| **claim** | none | none (closest: an actuator's readback, proof of operation) | What a block says it did, checked independently (SPEC §12g) | Plain | Keep for the assertion. Never use it for taking work (see **lease**) |
| **verdict** | none | none | The intent check's result: met, unmet, contradicted, unjudged | Plain | Keep, as the result of an acceptance inspection (rename 4) |
| **lease** | none | (watchdog timer) | Work held with a time to live, renewed by heartbeats (parity 2.6, 2.14) | Software standard (Gray and Cheriton, 1989) | Keep, and use it in place of "claim" for taking work |
| **dead-letter** | (a stock) | none | Work parked after repeated failure, for diagnosis | Messaging standard | Keep. In the SD view it is a stock; quality practice would say **quarantine** |
| **circuit breaker** | none | (a trip with automatic reset after a cool-off) | Parity 2.6 | Software standard (Nygard) | Keep, defined as a trip with a timed half-open probe |
| **WIP limit**, **Little's law**, **class of service**, **cμ rule**, **WSJF** | none | none | Parity 2.9, 2.14, 2.15 | Queueing and lean standard | Keep |
| **outcome**, **budget**, **owner** | | | | Plain | Keep; see **owner** under "define carefully" |
| **follow-up**, **reopen**, **missed**, **route**, **classifier** | none | none | SPEC §12h | Plain | Keep. In the SD view, reopen is the discovery flow of the rework cycle |
| **parameter**, **equation**, **structure** (kinds of change) | Parameter change, formulation change, structural change | Retuning against redesign | `ergostat.model-change` kinds | Match | Keep; add parity 00's **control**, **measurement**, **boundary** |
| **calibration**, **fit**, **Theil statistics** | Sterman 1984; Oliva 2003 | (estimation) | §12b | Match | Keep |

## 2. Rename

The word collides with a standard meaning, or a standard word exists and ergostat does not use it.

| Term | SD | CE | ergostat | Verdict | Use, and why |
|---|---|---|---|---|---|
| **valve** | The glyph on every flow, where its rate equation lives | A control valve: one kind of actuator | A flow's actuator; "a flow with no valve is a disturbance"; in the parity notes, any decision point | Collision in both | **Actuator** (control view), **rate equation** or **flow** (SD view), **valve** only for the glyph. A "trusted valve", "the VOI valve", "the timing valve" become **the decision rule for X**, a **permissive**, or the named controller. The event `valve.opened` would follow as `actuator.moved` |
| **decision** (item kind) | Decision rule: the policy setting a flow | The controller's law | `ergostat.decision`: an owner's settled design choice | Collision | Checkable ones → **constraint** (parity 2.12 already proposes retiring the kind into model changes); the record of choices and reasons → **design decision record** (the software practice's ADR) |
| **decision** (tier) | | | The rung between narrow AI and program | Collision | **Decision table**: a fixed mapping from cases to actions, which is what the rung is |
| **decision** (output line) | | | `{"decision": ..., "why": ...}` | Collision | **Rationale** (`{"rationale": ..., "why": ...}`): what the block did and why, for the log |
| **invariant** | none | An invariant set (a region the state stays in once entered) | The owner's rules about the artifact (parity 2.3, 2.12) | Collision | **Constraint**, marked **hard** or **soft** (MPC), enforced by a **permissive**, **interlock** or **trip** (IEC 61511). "Unguarded invariant" → **unenforced constraint** |
| **judge** (`judge: model`) | Validation: building confidence by tests | Validation on fresh data (Ljung ch. 16) | Replays a change on record held out, passes or fails it | Invented, where a standard word exists | **Validation** (the block: the **validator**). Its passes and failures are **validation results** |
| **judge** (`judge: intent`) | none | none; quality: inspection against acceptance criteria | Checks finished work against the owner's words, decisions and corrections | Invented | **Acceptance inspection** (the block: the **inspector**). Its verdict is kept. Parity 2.2 already narrows it to a residual reader behind a guard |
| **ladder**, **rung** | none | Ladder logic (IEC 61131-3 LD); a rung is one line of it | The kinds of machine by cost and predictability: person, AI, narrow AI, decision table, program, rule, nothing | Collision (CE) | **Tier** (`@tier:ai`). "Moving down the ladder" → **moving to a lower tier** |
| **gate** | none | none in loops; a logic gate in block vocabulary; Stage-Gate in product development (Cooper) | A risk check that holds acts (parity 2.5), a done-criterion on a transition (2.2), the merge gate | Collision, and three meanings | Before an act: **permissive**. On a state transition: **guard** (the term of state machines and Ramadge–Wonham supervisors). Waiting for the owner: **hold point** (inspection practice). Retire "gate" as a part's name |
| **hold** (`hold:` on a goal), **held** (work), **hold** (2.1's interlock) | none | ISA-88's **held** state: a procedure paused, resumable | Three meanings: the setpoint key; work an inspection stopped; an interlock on a neighbourhood | Collision | Reserve **hold** and **held** for ISA-88's sense (paused, resumable). Say **setpoint** or **limit** for the goal's value in prose; the key can follow later as `setpoint:`. Inspected-and-stopped work is **rejected** (quality) |
| **projection** (recipe) | Projection: a forecast from the model | none | §12j's "projection recipes" (event-sourcing's projection) | Collision | **Context recipe**, or just **recipe** (see "define carefully"). Keep "projection" for the forecast the model makes (§12b, "replay and projection") |
| **tolerance** (goal) | none | A specification's tolerance band; for alarms, the **deadband** | Hysteresis on the goal's status | Collision (mild) | **Deadband**, as ISA-18.2 and DCS alarm practice call the hysteresis on a limit |
| **done-when** | none | none; quality and agile: **acceptance criteria** | The owner's words for when a piece of work is done (§12i) | Invented, where a standard word exists | **Acceptance criteria** |
| **standing consent**, **consent** | none | none; ITIL: a **standard change** is pre-approved by class | An owner's general approval for a class of act | Invented (parity 2.5 already retracts it) | **Pre-approved change class** (standard change) |
| **agent** (`agents:` in YAML) | none; agent-based modelling's agent is a simulated individual | none | A machine shared by blocks | Collision with ABM, and with "AI agent" | **Machine** for the declaration and the concept (the docs already say machine); **AI agent** only for the AI kind. `agents:` → `machines:` would follow |
| **kind** (of item) | none | none; DES: entity type; Kanban: work item type | `items:` entries; also an agent's `kind` (person, ai, ...) | Internal collision | **Item type** for items; keep **kind** for a machine's kind, which is its tier |
| **regime** | none | ISA-18.2: **operating state** (state-based alarming) | The owner's situation (at work, away) that schedules a check (parity 2.5) | Invented, where a standard word exists | **Operating state**; and the schedule on it is **gain scheduling** or **state-based** limits |
| **library part** | Generic structure (Lane and Smart; Hines's "molecules"); a module | A library block (Simulink), a function block type (IEC 61131-3) | A parametric piece of model instantiated many times (parity 2.6, 2.9, 2.15) | Invented, where standard words exist | **Generic structure** in the SD view, **library block** in the control view; one name in the YAML, **template**, so "part" keeps its meaning (a model element) |
| **back in**, **time off**, **crossings** | none | Recovery (settling) time; time outside limits; limit excursions | Loop performance words (vocabulary) | Invented, where standard words exist | **Settling time** (for ==), **recovery time** (for a limit), **time outside limit**, **excursions** |
| **modeling** / **modelling** | The activity of building the model | none | Both spellings, in the same notes | Spelling | **Modelling** (the docs' British spelling), everywhere; `modeling` only where it names code |

## 3. Define carefully

The word is right, but ergostat uses it in a way one of the fields would read differently. Define it
once, in these words, in CONCEPTS or the vocabulary.

- **goal.** SD: the desired state in a balancing loop, compared with the actual (or perceived) state to
  make a gap; a variable of the model, which can itself drift (the eroding-goals archetype needs the
  goal to be a stock or auxiliary with its own inflow). Control: the setpoint, r. ergostat: an object
  with a one-sided or two-sided target (`"<= 20"`, `"== 50"`), an owner and a criticality, fixed in the
  model. *Define*: a goal is SD's goal and control's reference; with `==` it is a **setpoint**, with
  `<=` or `>=` a **high or low limit** held by **zone (range) control**, and the control view should say
  which. A goal that should be able to drift is not a goal key but a stock or auxiliary, so the drift is
  modelled (parity 2.1's "goals lowered" flow).
- **loop.** SD: any feedback loop, with or without anything designed in it. Control: a control loop,
  sensor to controller to actuator to plant. ergostat uses both: §12a's derived feedback loops and
  CONCEPTS's "a loop is derived: a goal, its sensors, its controllers, their valves", and the Loops
  page lists control loops. *Define*: always qualify, **feedback loop** (SD) or **control loop**
  (control). A control loop is one kind of balancing feedback loop.
- **block.** Control: a function from inputs to outputs in a block diagram; IEC 61131-3 function block.
  ergostat: the same, but a block may be a program, an AI agent, a person or an external system.
  *Define*: a block is the control view's function block; what runs it is its tier. A `person` block is
  as legitimate as Simulink's human-operator model, and should be described that way, not as a novelty.
- **valve (glyph).** After rename 1, the word survives only for the symbol on a flow's pipe in the
  stock-and-flow diagram, where SD puts it, on every flow.
- **disturbance.** Control: an input not manipulated by the loop. ergostat counts as a disturbance any
  flow on the goal's stock not set through this loop, including flows another loop sets. *Define*: a
  flow set by another loop is, in control terms, an **interaction** (a coupling between loops, the
  subject of pairing and the RGA), and is a disturbance only to a loop designed as if decoupled. Say
  which.
- **setting.** A stock a controller steps through a two-way flow (SPEC §7a). Control: the manipulated
  variable of a controller in velocity form (its output with memory). SD: a stock adjusted by
  anchoring and adjustment. *Define* as both, and say "manipulated variable" in the control view.
- **process** (`process:` on a goal). Control: the plant, or a model of it (here FOPDT, K e^(−θs)/(τs+1)).
  *Define*: the identified or declared process model of the goal's loop, from u to y. Note it is
  written on the goal because the goal names the loop's CV; the pairing (which u) is derived.
- **critical.** Control and safety: safety-critical, with a required integrity. ergostat: a goal that
  guards against a cascade, watched for decay. *Define*: "critical" means watched for loop degradation,
  not safety-instrumented; if it is meant to be a protection layer, it needs the independence and
  specification of 00-oracle §3.7.
- **limit** (on a stock). Control: a physical constraint. ergostat: the physical capacity, used for time
  to failure. *Define* as the stock's **capacity**, a hard physical constraint, distinct from a goal's
  limit (a requirement).
- **owner.** Control: the operator; process safety: the person who authorises change; product practice:
  the product owner. ergostat: all three, plus a sensor ("the owner is also one of its sensors").
  *Define* the owner's roles separately: **operator** (watches, acknowledges, overrides), **change
  authority** (approves model changes), **source of requirements** (goals, constraints), and **sensor**
  (corrections, observations). The interface and alarm rules (00-oracle §3.8) apply to the operator
  role.
- **mode** (`mode: advise`). ISA-88: automatic, manual, and an intermediate mode in which the operator
  confirms each transition; historically, advisory (operator-guide) control, where the computer
  proposes and the operator acts. *Define* `advise` as that intermediate, operator-confirmed mode. Keep
  **mode** for who drives the transitions; never for the operating state (see **regime**).
- **recipe** and **context.** ISA-88: a recipe is the procedure, formula and equipment requirements for
  a batch; a **master recipe** is the template, a **control recipe** the copy made for one batch. LLM
  practice: the context is what the model sees. ergostat: a versioned template (`contexts:`) rendered
  for one run. *Define*: the `contexts:` entry is a **master recipe**, its rendering for one run a
  **control recipe**, which is the **brief**. This is ISA-88's sense, deliberately, and it keeps
  ISA-88's separation: the recipe says what the work needs, the machine is chosen apart from it.
- **brief.** The rendered context a worker starts from. *Define* as the control recipe plus the work
  order (ISA-95's term for an instruction to produce): what to do, with what, held to which acceptance
  criteria.
- **model-change.** Process safety: management of change. ergostat: every change to the model, an item
  with states made, checked, testing, passed, accepted, superseded. *Define*: an `ergostat.model-change`
  is a **change request** in the MOC sense; its review is the hazard and technical review, Accept is
  the **authorisation**, the check after writing is the pre-start-up review. Keep the name; use MOC's
  vocabulary for its lifecycle in prose.
- **modelling subsystem.** SD: modelling is the whole process of 00-oracle §2. Control: the outer loop
  that maintains models (identification and redesign) and authorises changes. ergostat: the only thing
  that changes the model, from requests. *Define* it as three functions kept apart: **identification**
  (learning numbers and structure from the record), **modelling** (SD's formulation and testing), and
  **management of change** (authorising and timing the change). Today they are one block and one
  judge; the words should not hide that they are three.
- **improver.** Invented. *Define* as the **modeller**: the role that proposes model changes. Prefer
  "modeller" in prose.
- **correction.** Control: error correction is every loop's ordinary action. Quality: a corrective
  action (CAPA) removes the cause of a nonconformity so it does not recur. ergostat: the owner's words
  saying what to do differently. *Define*: a correction item is an **observation** of a nonconformity,
  in the owner's words; the model change it leads to is the **corrective action**. Parity 2.13 already
  draws this line between error correction (single-loop) and learning (double-loop).
- **trust.** Human factors (Lee and See, 2004): the human's attitude towards automation, which should
  match its capability. ergostat: `ergostat.trust.*`, the share of a block's claims contradicted. *Define*
  the measure as the block's **claim contradiction rate**, a sensor-validation statistic (parity 2.10:
  "trust is a sensor"); reserve "trust" for the owner's reliance, as Lee and See use it. See "retire".
- **feedforward.** Control: action on a measured disturbance before it shows in the error. Parity 2.12
  calls giving a worker the constraints in its brief "feedforward with no feedback". *Define*: that is
  **constraint handling in the plan** (constraints given to the optimiser, as MPC does), or simply the
  brief; reserve "feedforward" for measured disturbances.
- **anti-windup.** Control: preventing integrator wind-up at a saturated actuator. ergostat calls "a
  command held, not queued, while a run is going" anti-windup. *Define*: it is a related protection
  (no backlog of commands builds up while the actuator is busy), and should be described as such,
  not as the integrator scheme of Åström and Hägglund.
- **servo.** Control: a feedback system that tracks a reference. ergostat: an AI session as an actuator
  with its own inner loop. *Define*: the inner loop of a cascade, like a valve positioner inside a flow
  loop; the outer loop gives it a reference and judges the result by the stock.
- **system** (label, `systems:`). SD: a sector (Forrester) or module. Control: a subsystem or unit
  (ISA-88's physical model). ergostat: a group of parts, within others. *Define* as **sector** in the
  SD view, **unit** or **subsystem** in the control view. "The system" alone keeps its plain meaning,
  the whole.
- **part.** ergostat: any model element (stock, flow, goal, block). *Define* as that, and keep it out
  of the name of templates (see **library part**).
- **the record.** Process industries: the **historian** (time series) and the event journal. ergostat:
  readings and events, the only store. *Define* as historian plus event log.
- **replay.** SD: historical simulation, driving the model with recorded inputs. Ljung: simulation (an
  output-error model, never one step ahead). *Define* as **historical simulation**; it is not a
  re-execution of the work.
- **reference window**, **hold-out**. SD: the historical fit period. Ljung: estimation data and
  **validation data**. *Define* in Ljung's words.
- **scaled error.** The normalised mean squared error. *Define* it so, and pair it with Theil's
  breakdown wherever it is shown.
- **discovery** (`discover loops`, `discover prometheus`). Control: **structure identification**; SD:
  formulation from data. *Define* as structure identification; it proposes, and the result is a
  hypothesis (SD-5), not a finding of fact.
- **observation.** Control: a measurement. ergostat: an event a sensor records about an item, never a
  command. Matches; *define* so that it is not confused with the **observer** (an estimator).
- **neighbourhood.** Invented (a graph term): the parts within k links of a request, the loops through
  them and the goals and blocks on them. *Define*; it plays the role of the subsystem a control
  engineer would analyse, and of the sector an SD modeller would test in partial-model tests.
- **Coordinator.** Hierarchical control (Mesarovic, Macko and Takahara, *Theory of Hierarchical,
  Multilevel Systems*, 1970): the upper level that coordinates subsystems by setting their interaction
  variables. Beer's Viable System Model: System 2 (coordination, damping oscillation between units) and
  System 3 (control, resource allocation). ISA-95: level 3 dispatching and scheduling. ergostat: the
  role the long session filled. *Define* it as the supervisory and scheduling layers of 00-oracle §3.3
  together, and say which layer each of its functions is in.
- **Supervisor.** DES: the supervisor of Ramadge and Wonham, which only disables controllable events.
  Process control: the supervisory layer, which sets setpoints. Erlang: a supervisor restarts children.
  Orchestra: the agent that configured the system. *Define* by which is meant every time; prefer
  **supervisory layer** and **DES supervisor**, and retire Orchestra's sense from ergostat's docs.
- **context holder.** Invented (harness doc §8). *Define*: a long-lived session holding the project's
  interpretation, consulted by workers. In control terms it is a shared **process model** (STAMP) and
  an **observer** of the owner's intent; say so.
- **alarm** (block type). ISA-18.2: an indication requiring a timely operator response. ergostat: a
  block that raises a finding while out of bounds. *Define*: an `alarm` block is an alarm only if it is
  rationalised (a defined response, priority and time to respond); otherwise it is an **alert** or a
  finding. CE-27 applies.
- **external.** A block performed by something ergostat does not run. *Define* as an **observed
  controller** (or actuator) whose law is identified, not designed.
- **ledger**, **morning brief** (the-job). *Define* as the **shift log** and the **handover report** of
  control-room practice.
- **experiment**, **probe**. Control: an identification experiment; dual control's probing. *Define*:
  an experiment perturbs; a probe reads. Step tests are experiments.

## 4. Retire

The word should go from ergostat's vocabulary, because what it names is better said by an existing
term, or because it names nothing the model holds.

| Term | Why | Replace with |
|---|---|---|
| **trust** (as the name of a measure) | It names a human attitude in the literature (Lee and See), and parity 2.10 shows the measure is a sensor-validation statistic | **claim contradiction rate**; "trust" only for the owner's reliance on a machine |
| **consent**, **standing consent** | Already retracted in parity 2.5 | **pre-approved change class** |
| **gate** (as a name) | Three meanings, none standard in control | **permissive**, **guard**, **hold point** |
| **the ladder** (as a metaphor) | Collides with ladder logic | **tiers** |
| **"trusted valve"**, **"the timing valve"**, **"VOI valve"** and the like | Valve used for any decision point | The named controller or decision rule, or **permissive** |
| **invariant** (for the owner's rules) | Reserved meaning (invariant set) | **constraint** |
| **projection recipe** | Collides with SD's projection | **context recipe**, or **master recipe** in ISA-88's sense |
| **"decision" as a tier** | Collides with SD's decision rule | **decision table** |
| **"the controller is the decision"** (CONCEPTS) | Ambiguous after the decision kind | "the controller holds the **decision rule**" |
| **done-when** | A standard word exists | **acceptance criteria** |
| **modeling** (American spelling in prose) | Two spellings in one set of notes | **modelling** |

## 5. Where the words still differ between the two views

Some pairs are the same thing under two disciplines' names. ergostat should not choose one; each view
uses its own, and `explain` gives both. The table extends the vocabulary's comparison
([../../vocabulary.md](../../vocabulary.md)) with the words above.

| One thing | SD view | Control view |
|---|---|---|
| What is wanted | goal | setpoint, or high or low limit |
| How far off | gap (discrepancy) | error |
| How a flow is set | rate equation, decision rule (policy) | controller law, actuator |
| The glyph on a pipe | valve | (none; the actuator is a block) |
| A lag in seeing | perception delay, information delay | measurement lag, filter |
| A lag in moving | material delay | dead time |
| A part of the model | sector | unit, subsystem |
| A reusable piece | generic structure | library block |
| A rule that must not be broken | (a constraint on a stock or flow) | hard constraint, enforced by permissive, interlock or trip |
| Checking a model change | validation (Table 21-4's tests) | validation on fresh data (Ljung) |
| Learning numbers from the record | calibration, estimation | identification |
| Learning structure from the record | formulation from data | structure identification |
| A change to the model | policy change, structural change | management of change |
| Work found not done after acceptance | discovered rework | (quality: nonconformity) |
| A piece of work's description given to a worker | (the decision's information) | control recipe and work order (the brief) |
