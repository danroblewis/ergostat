# Parity 2.12: coherence with earlier decisions

Status: exploration, 2026-11-17. One of sixteen notes that rework the harness parity plan
([harness-parity-plan.md](../harness-parity-plan.md) §2.12) after the owner's review. The function it recovers is
number 12 of [harness-as-control-system.md](../harness-as-control-system.md) §5. Nothing here is built.

## 1. What the harness actually does, and why it is worth having

The long session checked each action against what had already been settled: no new pages or panels, the
two perspectives kept apart, the commit trailer, the port rules, the rejected designs left rejected. Three
separate things produce that behaviour, and they need separating because ergostat can recover each one
differently.

- **The context window holds the settlement with its reasons.** The owner's sentence, the argument around
  it and the alternatives turned down all sit in the transcript (or in CLAUDE.md and the memory index,
  which load into every turn). The model attends over all of them when it writes the next action, so a
  proposal that goes against them shows up as a contradiction while it is being generated, before any
  check runs.
- **Training for self-consistency.** Models are trained hard not to contradict what they said earlier in
  the conversation. A decision the assistant agreed to becomes something the next turn is reluctant to
  undo. That reluctance has no explicit threshold: reversing course needs a reason that seems to outweigh
  the earlier agreement, and nothing measures it.
- **Interpretation of scope.** Mostly the session did not match words. It judged whether a new case
  fell under a decision: whether a legend on the diagram counts as new UI (no), or whether a side panel
  does (yes). The value is semantic, as the harness note's §7 argues.

The failure case is just as informative. The product-owner agent in Orchestra drifted: it swapped earlier
design decisions for new ones that added little. Its context did not hold the earlier decisions, or held
them weakly, and nothing made a reversal cost anything. Coherence matters because each reversal costs
rework, puts complexity on both sides of the switch, and wears down the owner's trust that a settled
question stays settled.

## 2. Classical parallels, and where they fall short

The owner's point is right as far as it goes. In system dynamics a *decision* is a rate equation:
Forrester called rate equations decision functions, and Sterman's "decision rule" is the policy that sets a
flow. In control engineering the decision is the controller's law. ergostat already uses the word both
ways ([CONCEPTS.md](../../CONCEPTS.md): a controller "is the decision"; vocabulary: "policy (decision
rule)"; `decision` as a rung of the ladder; the `{"decision": ..., "why": ...}` output line of §9.1). Inside
one model those decisions cannot contradict each other quietly. `check` refuses two blocks writing one flow,
reports competing commands, and the improvement loop (§12e) changes them only through judged
`ergostat.model-change` items. **For decisions that live in the model, coherence is a property of the
math, and there is no gap.**

The gap is in the decisions the harness kept that are *not* in the control model: constraints on the
artifact the plant produces (the codebase, squeeze's output formats), and conventions on how actuators act
(trailers, ports). Several classical parallels fit them.

- **Constraints and invariant sets.** Constrained control (MPC above all) separates the objective, a
  setpoint to steer towards, from constraints, a region the state or input must never leave. A positively
  invariant set is a region the system stays in once it enters. In those terms an earlier decision is a
  constraint on the plant's output, and coherence means keeping the trajectory inside the admissible
  set. This is the owner's 2.3 point that invariants can serve as decisions, and it matches CLAUDE.md's
  rules section, which is a list of invariants.
- **Interlocks, permissives and the safety instrumented system.** Process plants enforce such constraints
  in a separate layer: independent sensors, a trip that closes a valve, and a permissive that must hold
  before an action may start. A violated constraint does not steer anything. It blocks.
- **Supervisory control of discrete-event systems** (Ramadge and Wonham). A supervisor watches the event
  stream and disables the controllable events (merge, accept, push) that would take the system's
  behaviour outside a specification. Coherence is defined formally as staying within the specification
  language.
- **Management of change** (process safety practice). Changing an interlock or a safe limit takes a
  recorded reason, a review and an authorisation, and bypassing one is logged. This is the "supersede with
  a reason" the old plan built.
- **Hysteresis, dwell time and the drifting-goals archetype.** A switching controller with no
  hysteresis chatters. In SD, the drifting-goals (eroding-goals) archetype describes a goal that is
  quietly adjusted towards what is being achieved. The product-owner agent showed both. The classical
  remedies are a switching cost or minimum dwell time, and anchoring the goal to an external standard.

Where they fall short of the harness:

1. **Representation.** All of these assume the constraint is written as a measurable inequality. The
   owner's decisions arrive as sentences. Turning a sentence into a sensor is work the harness never did
   explicitly. It kept the sentence and interpreted it each time.
2. **Interpretation.** A classical constraint monitor compares numbers. Deciding whether a diff "adds UI"
   takes judgement, so the sensor is either a narrow AI with measurable false alarms and misses, or a
   cruder rule that is wrong in known ways.
3. **Feedforward.** An interlock only catches. The harness also *avoided* producing incoherent work,
   because the constraint shaped generation. Classical feedforward acts on a measured disturbance, not on
   a constraint given to the actuator in advance. The closest analogue is handing constraints to an
   optimiser so its plan respects them, which is what giving a worker the invariants in its context does.

So the gap, stated precisely: **earlier decisions about the artifact are constraints that are not in the
model.** Until they are, the math cannot keep them coherent. All that remains is context (feedforward with
no feedback) or a single judge that holds every decision inside one block.

## 3. What ergostat already has

- **Coherence of the model itself.** One model (§1a). `check` reports errors and findings (§12): competing
  commands, two blocks writing one flow. Every model change is a judged item with reasons and evidence
  (§12e), checked again after it lands (§12f, the prediction check). This is management of change for
  the control model, and it works.
- **A goal can already express an invariant.** A goal holds a flow's rate (`hold: "== 0"` on
  violations), `critical: true` watches it for decay, and a goal on a part with no sensor is reported as an
  **unjudgeable goal** (§12). That last finding is exactly the honest status of a decision that exists
  only as words.
- **Low-select override and onoff gates.** `select: {pick: min}` (§9.2) is override control: a zero from an
  interlock beats the controller's command. `mode: advise` puts a person in the loop on a valve.
- **The intent judge** (§12i) holds finished work to the confirmed decisions in its scope, before it counts
  as done, with evidence. It measures what escaped (`ergostat.intent.false-done`) and the tests-alone
  counterfactual. It is a constraint monitor and an interlock rolled into one block (image-squeeze's
  rollback drops a held candidate, and its rollout keeps none before it has a verdict).
- **Project checks for claims** (§12g, `claims:`) run a declared command as a sensor. This is the rule-rung
  form of a constraint check.
- **Context recipes** (§12j) carry the decisions in as feedforward. The parity benchmark measured them as
  strong on decisions (0.83) and rejected alternatives (0.88).
- **Built last night:** the `ergostat.decision` kind (proposed, confirmed, superseded, dismissed; words,
  reasons, alternatives, scope), the extractor (stand-in and AI; 45 decisions proposed from this session
  at a sampled precision of 0.75), and `ergostat context decisions`.

**A judgement on the decision kind.** The owner is right that it is the wrong shape, and there is one more
reason: the name breaks ergostat's own first principle, rule 7, that no word means two things. "Decision"
already names a controller, a policy, a rung and an output line. More important, the kind keeps the
decisions *beside* the model, as records the judge and the recipes read, rather than *in* it. As a result:

- no SD or control view can see them (no stock, no loop, no goal per decision);
- the intent judge holds every decision inside one block, which is the complexity-inside-a-block smell;
- confirming or superseding a decision changes what the system enforces without going through the
  modelling subsystem, which is meant to be the only thing that changes the control model.

The extractor is a different matter. It is a good instrument: an observer that estimates the owner's
standing intent from what they say. It should stay, pointed somewhere else.

## 4. Candidate designs

### A. Invariants as goals: a constraint monitor and an interlock per invariant (a library part)

Each confirmed decision about the artifact becomes, in the model, a small piece of structure.

- **A flow `violations-of-X`**, whose sensor is the invariant's check. The check runs on the work as it
  reaches the merge (or accept) valve, and only when the work touches the invariant's scope, so the sensor
  is sampled on events.
- **A goal on that flow**, `hold: "== 0"`, with `critical: true` for the invariants that guard against
  drift. The owner's sentence, its reasons and the rejected alternatives go into the goal's description
  and into the reasons and evidence of the model-change item that added it.
- **An interlock**: a `compare` block on the check's latest verdict, low-selected (`select: min`) into the
  command of the merge valve. A violation stops the merge. It does not steer anything.
- **The check's rung follows the ladder.** It starts as a narrow AI (the intent judge's model mode, given
  only this invariant and the diff) or as the person rung (the owner looks). The modelling subsystem moves
  it down when the record allows: a lint rule, a test, a grep. The commit trailer is a `rule` from the
  first day. "No new UI" probably stays a narrow AI.

Because dozens of invariants share the same shape, this should be a **parametric library part**,
instantiated per invariant with its name, scope, words and check. Grouping by scope (one part per
neighbourhood, such as "diagrams" or "formats") keeps the model readable. Its measures are per invariant
(`@NAME`), the way trust is per block.

Drawn in **SD**: a violations flow into a stock of work held, drained by fixes and by owner overrules
(released). The R/B structure is visible: more held work means more rework, which balances the merge rate.
Drawn in **control**: a constraint monitor (sensor) on the work's output, an override into the merge
actuator, and a separate, slower supervisory layer the way a SIS sits beside the basic control loops.

**The modelling subsystem's role.** It alone adds, refines and removes invariants. The extractor becomes
one of its improvers: it reads the owner's turns and *proposes a model change* (structure: a new
instance of the part, or a refinement to an existing one) with the owner's words as evidence. Structure is
accepted by the owner under the default policy (§12e), so confirmation is the existing Accept, and
superseding is a model change that edits or removes an instance with a reason (management of change,
unchanged in spirit). It needs a neighbourhood as context: the invariants that share the scope (to catch
duplicates and conflicts: two invariants whose admissible sets do not intersect make the problem
infeasible, which it must say), the goals and blocks of the systems in that scope, and the owner's recent
words about them. It also tunes each check from its record: owner overrules are false alarms, and owner
corrections after a merge are misses. That is sensor calibration, the measurement-quality work 2.16 asks
for.

**Rate of change.** Adding an invariant does not pause running work. A running worker is a trusted valve,
and the interlock judges its result when it reaches the merge. When the new invariant's scope touches work
in flight, the message router (§12h) can deliver a note to the running session. That is the simulated
coordinator's update and a feedforward correction, not a change to the worker's goal. Removing or relaxing
an invariant releases the work it held, which is then judged again.

```yaml
# a library part, instantiated once per invariant (or per scope group); shown expanded
flows:
  violations-no-new-ui:
    to: work-held
    description: work that would add a page, panel or wizard (owner, settled; reasons and rejected options on
      model-change/3f2a)
    sensor:
      run: ergostat check-invariant no-new-ui --scope ui --diff "$ITEM"   # narrow AI now; a rule later
      on: entering review                                                  # sampled on the event, in scope only
goals:
  no-new-ui:
    flow: violations-no-new-ui
    hold: "== 0"
    critical: true
blocks:
  no-new-ui-permit:
    type: compare
    in: flow.violations-no-new-ui
    below: 1                       # 1 while nothing is violated: the permissive
    out: block.merge-permit
  merge-permit:
    type: select
    pick: min                      # override: any interlock at 0 closes the merge
    in: [block.merge-queue, block.no-new-ui-permit, block.two-views-permit]
    out: block.merger
```

### B. Feedforward with one judge (what exists now, renamed)

Keep the decision records as context (§12j) plus the intent judge as the single feedback check, and
rename the kind (`ergostat.invariant`) so it no longer collides with "decision". This is cheap, and the
benchmark shows the feedforward half works. But the constraints stay outside the model. The judge stays
one block with every invariant hidden inside it, its misses cannot be put down to a particular invariant,
and confirmation still changes enforcement without the modelling subsystem. This is a halfway step, not a
destination.

### C. A supervisor on the event stream (Ramadge–Wonham)

A built-in supervisor that refuses controllable events (`*.merged`, `*.accepted`) for items whose checks
show a violation, with the specification taken from the model's invariants. It is design A's interlock
placed at the event layer instead of on a valve. It is tighter, because nothing gets around it, but it is
less visible: the refusal does not appear as a loop in either diagram. It would be worth having as an
enforcement backstop under A if valves turn out to be bypassed (a block that merges without asking).

### D. An anti-drift loop on the invariants themselves

The drifting-goals archetype's remedy, made explicit. A stock of settled invariants. A flow of
supersessions. A switching cost: a proposal that supersedes an invariant must predict a gain on an outcome
(the value judge of 2.15) that exceeds the cost of the reversal, so the supersede valve has hysteresis.
A dwell time: an invariant superseded within N days of being settled is a finding. This is not a separate
mechanism. It is a goal and a measure on design A's structure, and it addresses exactly the
product-owner failure.

### How parity is measured

- **Escaped violations**: merged work the owner later corrects for going against something settled ("we
  had decided this"), per merged item, compared with the same rate in the long session's transcript
  (F3's ground truth). Parity means equal or lower.
- **Held without cause**: owner overrules per invariant check (false alarms). Each check should earn its
  place, or be refined down the ladder or removed.
- **Settled-question churn**: invariants superseded within a dwell time, and supersessions with no
  predicted gain (design D).
- **Feedforward share**: of the violations caught, the share that would have been avoided had the worker's
  context carried the invariant. Measured by the existing benchmark cases on decisions and rejected
  alternatives, rendered from the model instead of from items.
- **Unjudgeable invariants**: the existing finding, counted. It shows how much of what was settled is
  still only words.

## 5. Recommendation

**Design A, with D's measures on it, and B's feedforward kept as the context part.** Reasons:

- It answers the owner's objection literally. The decisions go *into* the model, as goals, sensors and
  override blocks, so the math keeps them coherent. Nothing new is needed beyond a library part and a
  check command, both built from existing pieces (a goal on a flow, `compare`, `select: min`, a `run`
  sensor, model-change items).
- It ends the smell of one judge holding every decision. Each invariant gets its own sensor, measures and
  place on the ladder, so the improvement loop can tell which checks work.
- It sends every change to what is enforced through the modelling subsystem, with management of change
  supplied by the existing proposal, judge and Accept path.
- It keeps both halves of what the harness did: feedforward (the recipe renders the invariants in scope,
  with the owner's words) and feedback (the interlock).

On the old plan's Build for 2.12 and what was built last night:

- **Keep** the extractor, repointed: it becomes an improver in the modelling subsystem, whose output is a
  structural `propose` (an invariant instance) carrying the owner's quoted words as evidence. It needs one
  new evidence form, an owner's turn by session and line. Keep its quote checking. Its 0.75 precision is
  acceptable, because the owner accepts structure anyway.
- **Keep** what the decision items carry (the sentence, the owner's words with where they were said,
  reasons, rejected alternatives, scope). Their home moves: the model-change item that adds an invariant
  and the goal's description.
- **Keep** supersede-with-reason. It is the model-change flow on the invariant's instance.
- **Change** `ergostat context decisions` to render the invariants in scope from the model (and their
  model-change history) instead of from decision items. The benchmark variant should be re-run to confirm
  nothing is lost.
- **Change** the intent judge from holding every decision into the generic checker the library part calls
  per invariant, while still judging done-when and messages (2.2's concern).
- **Retract** `ergostat.decision` as a kind, its separate proposed/confirmed lifecycle, and the name.
  Migrate the 45 proposals as grouped model-change proposals, one per scope neighbourhood, so the owner
  reviews a handful rather than 45.
- **Retract** the old plan's stocks "decisions confirmed" and "proposed awaiting the owner" as the model of
  this function. The function's stocks are work held and invariants unjudgeable. Decisions waiting are
  just open model changes.
- **Leave to 2.13** the corrections about *conduct* ("act, don't ask"). Those are not constraints on the
  artifact. They are about how a block should behave, so they belong to its own harness's context or to
  human-in-the-loop valves.

Not every settled matter becomes a checkable invariant. Some stay vague, and these show honestly as
unjudgeable goals carried by feedforward alone, which says exactly how much coherence ergostat has yet to
recover.

## 6. Open questions for the owner

- Should every settled decision about the product become a model invariant, or only those you would want
  a merge stopped for, with the rest left as context?
- Is a merge interlock the right point of enforcement, or should some invariants stop work earlier, at the
  moment it is proposed?
- Do you accept "invariant" (in the invariant-set sense) as the word, given that "decision" already names
  a controller in ergostat?
- Should the 45 extracted proposals be migrated as grouped invariant proposals, or should extraction run
  afresh under the new shape?
- Should superseding an invariant need a predicted gain on an outcome (the switching cost), or is your
  reason enough?
- Does a library part for this belong in ergostat's core, or in a starter set like the merge queue
  (2.14)?
