# 2.13 Learning from correction

Status: exploration, 2026-11-17. One of sixteen parity notes (see
[harness-as-control-system.md](../harness-as-control-system.md) §5 item 13 and
[harness-parity-plan.md](../harness-parity-plan.md) §2.13 and §4). Nothing here is built.

## 1. What the harness actually does

When the owner corrects the long session in one sentence (stop asking and get on with it; justify a design or
drop it; a pronoun rule for prose), three things happen, at three speeds.

- **At once, in the context window.** The sentence becomes part of what every later token is conditioned on.
  The very next action differs. Nothing was stored or retrieved; the correction is simply present, read
  together with everything else the session holds.
- **By generalisation, from training.** Instruction-following and preference training let the model take one
  example and apply it to situations it has never seen: a correction about one pull request changes how it
  writes every later one, and a correction about one question changes how often it asks anything. Its prior
  supplies the *scope* (how far the correction reaches) and the *direction* (what "less of that" means for a
  different action). This is the semantic gain the harness note names: a numerical learner would need many
  data points to move as far.
- **Across sessions, by memory.** The harness writes a memory file (a feedback memory, with the reason), and the
  index of memories is loaded into every later session. The correction then survives compaction and a new
  session.

What makes it valuable is less the storage than three judgements the model makes with it:

1. **Which part of its own control system was wrong.** A correction about an ugly layout means it had no sensor
   on layout quality (the owner was that sensor); one about asking too much means a gate was set too tight;
   one about pushing with failing tests means a check step was skipped; one about building fitting machinery
   when the owner wanted model improvement means the goal itself was misread. The session repairs whichever it
   was, usually without saying which.
2. **How widely to apply it.** Too narrow and the owner says it again; too wide and the owner has to undo it
   ("you took that too far"). Both happen.
3. **How to reconcile it with earlier corrections and decisions**, so the policy stays coherent.

It also fails in a characteristic way: the scope guess and the repair are invisible and untested. Nothing
checks that a correction was learned until the owner notices the mistake again. The first parity run saw
exactly that: fresh sessions repeated mistakes the owner had already corrected.

## 2. The classical parallels, and the line between error correction and learning

The owner's distinction is the right one, and both disciplines already draw it.

- **Error correction is what every loop already does.** A controller reads e = r − y and acts on it, cycle by
  cycle, with a fixed law and a fixed structure. Reopening an item, delivering the owner's note to the session
  working on it (§12h), the intent judge sending work back (§12i): these are error correction on *this* piece
  of work. Nothing about the controller changes, and the next piece of work starts from the same law.
- **Learning changes the controller, the sensors, the setpoints or the structure,** so that the next
  repetition starts better. System dynamics calls this *double-loop learning* (Argyris; Sterman, *Business
  Dynamics*, ch. 1): single-loop learning corrects action against fixed goals and decision rules; double-loop
  learning revises the mental model and the rules themselves. In ergostat the mental model is the model, and
  the only thing allowed to change it is the modelling subsystem (§12e). So learning from correction *is*
  modelling, with the owner's correction as its evidence.

Control engineering has several named forms of the second loop:

- **Iterative learning control (ILC).** For a task repeated in trials, the feedforward input of trial k+1 is the
  input of trial k plus a learning gain times trial k's error: u(k+1) = u(k) + L·e(k). Its whole aim is that
  the same error does not recur, and its convergence is measured trial over trial. "The same correction given
  twice" is precisely ILC failing to converge. A kind of work in ergostat (code changes, reports, intake) is
  the repeated task; each run is a trial.
- **Run-to-run (R2R) control**, from semiconductor batch processes: between batches, an EWMA controller updates
  the recipe from the last batches' measured error, with a discount so one noisy batch does not swing it.
  It names the rate-of-change question: learn between runs, not inside one, and at a chosen gain.
- **Self-tuning regulators** (Åström and Wittenmark, *Adaptive Control*): identify the process, redesign the
  controller from the estimate; ergostat already does this for numeric loops, owner-gated (§12d).
- **Gain scheduling and supervisory mode switching**: when the operating condition changes, a supervisor
  switches the controller's parameters or its mode (auto, manual, cascade). An operator taking a loop to manual
  is the plant's version of a correction whose only reason is the person.
- **Human supervisory control** (Sheridan): an intervention corrects this moment and also says the
  automation's design is wrong.

Where they fall short of the harness: ILC and R2R learn a numeric correction for a known input channel; they
cannot decide *which* part of the system the error came from, and they need many trials. The harness gets
large, correctly-directed changes from one sentence, because the sentence carries the diagnosis and the scope
in words. The structure below keeps that semantic step (on the AI rung, where it belongs) but makes its output
a model change that can be judged, drawn and analysed, rather than a hidden adjustment inside an agent.

## 3. What ergostat already has

Honestly, quite a lot of the plumbing, and some of the right loops.

- **The readings.** `ergostat.correction` (SPEC §5a, built last night): the owner's words verbatim with where
  they were said, `corrects`, `kind_of_work`, `scope`, proposed → confirmed → retired, dismissed.
  `ergostat corrections scan` (`ergostat/decisions/fromrecord.py`) proposes corrections from what the record
  already holds: dismissals with a reason, items moved back with a reason, messages classed as corrections. The
  transcript extractor proposes them from the session (30 from this session, sampled precision 0.95).
- **The ILC error signal, roughly.** A correction that repeats an earlier one is linked (`repeats`,
  `correction.repeated`) and raised as `correction-repeated`. The matching is by shared content words, and its
  sampled precision was 0.5.
- **Feedforward into the next trial.** `ergostat context corrections --kind K`, and the `corrections` part of a
  recipe (§12j), put confirmed corrections into the starting context of an `ai` block. In the parity benchmark,
  adding corrections to decisions moved the score from 0.49 to 0.53.
- **Corrections as sensor criteria.** The intent judge holds finished work to the confirmed corrections in its
  scope (§12i, `ergostat/intent/brief.py`). That is a correction turned into a check, which is the right
  direction, but only for an AI judge's reading.
- **The modelling loop** (§12e, §12f): proposals with checked evidence, the judge on held-out record, accept
  policy per kind, the prediction check after acceptance (`verified` / `regressed`), and the loop's own
  measures. It is the place learning belongs, but today it only sees the fit to measured series; it knows
  nothing about corrections.
- **Human-in-the-loop valves**: a machine block's `mode: advise` (its commands wait for a person), `person`
  blocks, and `review:` rules that set review depth from a measure such as trust (§12j). All static or
  measure-driven; none is moved by corrections.

What is missing, stated plainly:

1. A confirmed correction changes later behaviour **without passing through the modelling subsystem**. Pushing
   it into every session's context is an unjudged change to the inputs of every AI block of that kind: a model
   change with no item, no evidence check, no judge and no prediction check.
2. Every correction is treated as **policy for an AI block**, whatever it actually corrected. A correction that
   reveals a missing sensor, a wrong setpoint or a gate set wrongly stays as words inside agents. That is
   complexity hidden inside blocks.
3. The corrections stock has **no outflow but the owner's retire**, so it grows (the harness note's open
   question). Nothing compiles a correction into structure and lets it leave the context.
4. Nothing measures whether a correction was **learned**, other than the owner repeating it.
5. Nothing gives the **fast, safe response** a plant operator has: when the owner corrects a kind of work, more
   of it goes past the owner until the learning is done.

## 4. Candidate designs

### A. Corrections as an ILC feedforward table (what was built, kept as is)

The confirmed corrections, indexed by kind of work, are the feedforward input of each trial; repeats are the
convergence error. Drawn in SD as a stock *corrections active* feeding the AI blocks by an information link;
in the control view as a feedforward block in front of each AI actuator. On the AI rung throughout. The
modelling subsystem has no role.

Cheap, and it helps a little (+0.04), but the learning happens inside the agents, the list only grows, and
nothing tests it: the memory file transplanted, without the session that integrated it.

### B. The absorption loop: a correction is evidence for the modelling subsystem (recommended core)

A confirmed correction is a *reading from the human sensor*: an error that no sensor in the model saw. It
enters a stock, **corrections unabsorbed**, and the modelling subsystem's job is to drain it by proposing a
model change that answers it. Each answer says which part of the control system it repairs, using the
disciplines' own parts:

| What was wrong | The model change that absorbs it | Rung it ends on |
|---|---|---|
| A missing or weak sensor (the owner noticed what nothing measured) | a sensor, a claim check (§12g), a test the project declares, a criterion for the intent judge | program or rule |
| A setpoint or goal misread | a goal's `hold`, a new goal, a done-when on the kind (2.2) | rule |
| A gate set wrongly (asked too much, or not enough) | the valve's mode, a `review:` rule, a standing allowance (2.5) | rule |
| A controller's policy (how an AI block should act) | an addition to that block's prompt or recipe | AI, until compiled |
| The structure (a missing review step, a missing queue) | stocks, flows, blocks | any |
| An invariant (something that must never happen) | an interlock or a check, related to the goals it protects (2.3, 2.12) | rule |

Absorption is a `ergostat.model-change` like any other, with the correction as its evidence (a new evidence
form, `correction:ID`). The judge cannot judge these by fit alone, so each correction carries a **trial**: the
situation it arose in (the item, the brief, the state as of then), the owner's words, and what should have
happened. Judging an absorption means re-running that trial against the changed model, as F3's task cases do
and as ILC re-runs a trial. A change that stops the mistake in its own trial without breaking the earlier
trials of the same kind passes. After acceptance, the prediction check (§12f point 4) becomes: has the
correction recurred? A repeat is `regressed` for the absorbing change, and the correction goes back into the
unabsorbed stock.

The key SD move is a **second drain**: corrections absorbed only as context (words in a recipe) sit in a stock
**corrections in context**, and the modelling subsystem is held to keep that stock small, which pushes it to
*compile* them down the ladder into a sensor, a gate or a test. Once compiled and verified, a correction leaves
the context (or stays as a one-line pointer), because the structure now enforces it. This bounds the context,
answers the harness note's open question, and is the ladder working as the owner wants: a behaviour starts as
an AI's instruction, is refined, and is replaced by a program.

Drawn in SD: a chain *unabsorbed → in context → compiled*, with an inflow *corrected* (from the owner) and a
leak back *repeated*; a balancing loop through the absorber (unabsorbed up, absorption up, unabsorbed down) and
a second balancing loop on the context stock (in context up, compilation up). In the control view: the owner
as a sensor on the plant's output that no instrument measures, the absorber as the outer (adaptation) loop
around the inner controllers, its output going to their parameters, sensors and setpoints, as an adaptive
controller's outer loop is drawn.

Measured by:

- **repeats**: corrections given twice, per kind of work. The baseline is the long session's own rate (the
  extractor linked 5 of 30 as repeats); parity is at or under it, the goal near zero.
- **owner-as-sensor share**: of the errors found in a week, the share first found by the owner rather than by a
  sensor, a claim check or a judge. It should fall as corrections are compiled into sensors. The harness never
  measured this; it is where ergostat can show parity rather than assert it.
- **overreach**: corrections that undo or narrow an earlier absorption within a fortnight (the scope set too
  wide).
- **F3 task cases** built from corrections: a fresh session, started from the model after absorption, avoids the
  corrected mistake.
- **context size** of the corrections part, which should stay bounded.

### C. Supervisory mode switching: the fast, safe response (recommended beside B)

Absorption takes hours (a proposal, a trial, a verdict). Meanwhile the kind of work that was corrected keeps
running. The plant answer is not to wait: the supervisor takes that loop toward manual. Here, a correction
rate per kind of work, read as an auxiliary, drives a compare block with hysteresis whose output is the mode of
the corrected kind's valve: above a threshold the valve goes to `advise` (its work waits for the owner, or its
`review:` depth goes up); once the absorption is verified and the rate falls under the release point, back to
`auto`, transferred without a bump (the held commands released one at a time).

This is the owner's point about corrections whose only ground is that the owner asked: a correction that cannot be generalised, or has not been
yet, means more human-in-the-loop valves, set by measurement, not by hand. It is also the answer to the
rate-of-change question:

- a correction about the item in flight is error correction: the message reaches the running session (§12h)
  or the item is reopened; nothing in the model changes;
- a correction about a kind of work does **not** rewrite a running session's goals mid-run (a Coordinator would
  not); the valve is switched to advise for that kind's *next* runs at once, which is safe and reversible;
- the model change follows between runs (R2R), and is judged before it reaches anyone.

Drawn in SD as a balancing loop with a cost: corrections up, owner approvals up, errors reaching outcomes down,
corrections down, but owner attention (a stock with a limited drain) is consumed, so the loop is bounded by a
second one. In the control view: an override selector over the block, the correction rate as the scheduling
variable. On the rule rung. The modelling subsystem tunes its thresholds like any loop (§12d), and owns
whether a kind of work may switch at all.

### D. Learning from overrides: the self-tuning part for numbers (smaller, a library part)

Many corrections are numeric in effect: the owner overrules the intent judge's verdicts, dismisses a kind of
proposal, puts a setting back. Each override is a reading of the gate's error. An EWMA run-to-run controller per
gate (the intent judge's strictness, a review threshold, a proposal's confidence floor) moves the threshold a
little per override, with a discount, and proposes the change to the modelling subsystem like §12d's tunings.
It needs no AI, it is a parametric part many gates would share, and it is measured by overrides per decision
falling. It covers the part of 2.13 the harness does by vague impression ("the owner keeps waving these
through"), and does it better.

### A sketch of B with C

As a part of the `modelling` system, written so a project can take it whole (a library part; whether that is
`use:`, a starter set or a copy is open, and nothing like `use:` exists yet). Keys that do not exist today are
marked.

```yaml
defaults: {system: modelling}

stocks:
  corrections-unabsorbed:            # confirmed, no accepted change answers it yet
    sensor: {items: ergostat.correction, state: confirmed, where: {absorbed: false}}      # absorbed: new field
  corrections-in-context:            # answered only by words in a recipe: the top of the ladder
    sensor: {items: ergostat.correction, state: confirmed, where: {absorbed_as: context}}
  corrections-compiled:              # answered by a sensor, a gate, a setpoint, a test or structure
    sensor: {items: ergostat.correction, state: confirmed, where: {absorbed_as: structure}}

flows:
  corrected:  {to: corrections-unabsorbed, sensor: {items: ergostat.correction, entering: confirmed}}
  absorbed:   {from: corrections-unabsorbed, to: corrections-in-context, driven-by: +stock.corrections-unabsorbed}
  compiled:   {from: corrections-in-context, to: corrections-compiled, driven-by: +stock.corrections-in-context}
  repeated:   {to: corrections-unabsorbed,       # the absorption did not hold: back in
               sensor: {items: ergostat.correction, entering: proposed, where: {repeat: true}}}

auxiliaries:
  corrections-rate-code:             # corrections per run of this kind of work, last week
    sensor: {builtin: ergostat.corrections.rate@code}                                      # new measure
  owner-found-share:                 # errors found first by the owner, of all found
    sensor: {builtin: ergostat.corrections.owner-found}                                    # new measure

goals:
  learned:        {flow: repeated, hold: "<= 0"}
  absorbed-soon:  {stock: corrections-unabsorbed, hold: "<= 3"}
  context-small:  {stock: corrections-in-context, hold: "<= 15"}    # pushes compilation down the ladder
  owner-not-sensor: {auxiliary: owner-found-share, hold: "<= 0.3"}

blocks:
  absorber:                          # the improver, given corrections as evidence
    type: ai
    goal: absorbed-soon
    prompt: prompts/absorber.md      # say which part was wrong; propose the lowest-rung change that answers it
    out: flow.absorbed               # propose lines with evidence correction:ID
  compiler:
    type: ai
    goal: context-small
    prompt: prompts/compiler.md      # turn a correction held as words into a sensor, test, gate or setpoint
    out: flow.compiled
  trial-judge:
    type: judge
    judge: correction                # new mode: re-run each correction's trial on the changed model
    accept: {context: auto, gate: auto, structure: owner}    # context and more-human gates are reversible
  supervise-code:                    # C: the fast path
    type: compare
    in: auxiliary.corrections-rate-code
    above: 0.2
    back-below: 0.05
    out: block.developer.mode        # new target: 1 is advise, 0 is auto
```

## 5. Recommendation

Build **B as the core, C beside it, D later as a library part**; keep A only as B's first, lowest-cost
absorption.

Reasons:

- It puts the learning where the owner's rule says it must be: only the modelling subsystem changes the model,
  and a correction becomes evidence for it, not a side door into every agent.
- It separates the two things cleanly. Error correction stays what loops and messages already do, on the item
  in flight. Learning is a judged model change between runs, at a rate the model chooses, with the mode switch
  as the immediate and reversible safety.
- It turns hidden complexity into structure: corrections end as sensors, gates, setpoints and tests that SD and
  control can see and analyse, and leave the context once they do.
- It is measurable in ways the harness never was: repeats, owner-as-sensor share, overreach, and the trial
  re-run for each correction.

Against the old plan's Build for 2.13 and last night's work:

- **Keep**: corrections as events and items (the owner's words, scope, kind of work); `corrections scan` from
  dismissals, reopenings and messages; the transcript extractor; the owner's confirm and dismiss on the
  reading; repeat detection, now as the loop's error signal; the intent judge reading corrections as criteria
  (that is one form of compilation into a sensor).
- **Change**: a confirmed correction is a reading, not an applied change. Its effect on later sessions comes
  only through an accepted, judged model change answering it (context included). The item gains how it was
  absorbed and by which change; `retired` becomes mostly automatic, when a compiled absorption is verified,
  with the owner's retire kept for a correction that no longer applies. Repeat matching needs better precision
  (0.5 is too noisy to drive a mode switch); a narrow AI classifier, later a rule, is the ladder path.
- **Retract**: the stock *corrections active* as the measure of success (a growing list is not learning), and
  "included in every later session of that kind" as the mechanism. Also retract the idea that the item kind is
  the answer: the kind is the sensor's record; the answer is the loop.

Connections: 2.4 (messages classed as corrections are the main inflow, and live delivery is the error-correction
half), 2.5 and 2.10 (the mode switch and review depth are the same human-in-the-loop valves), 2.3 and 2.12
(corrections that are invariants end as interlocks beside the decisions), 2.16 (compiling a correction into a
test is the same move as turning a claim into a test), 2.6 (deciding which part was wrong is diagnosis; corrections
the absorber cannot place should wait in a queue it reviews), 2.1 (no mid-run rewrites of a worker's goal), F3
(the trials).

## 6. Open questions for the owner

- Should a confirmed correction reach any session before the modelling subsystem has absorbed it, or only after
  its absorption is judged?
- Do you want to confirm the correction (the reading), the absorption (the model change), or both?
- May a correction switch a kind of work to advise mode on its own, with only the return to auto needing you?
- Is the parity target the long session's own repeat rate (about one in six), or zero?
- Should a correction compiled into a sensor or gate leave the context entirely, or stay as a one-line pointer?
- Should this loop be a maintained library part every project gets, or wiring a project chooses?
- Is "the share of errors you found first" the measure you would trust that ergostat has learned?
