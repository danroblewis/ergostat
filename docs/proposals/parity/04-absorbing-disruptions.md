# Parity 2.4: absorbing disruptions

Status: exploration, 2026-11-17. One of sixteen ([harness-as-control-system.md](../harness-as-control-system.md) §5
function 4; the first plan's answer is [harness-parity-plan.md](../harness-parity-plan.md) §2.4, built as SPEC §12h).
The question is rephrased as the owner asked: not "how does a worker hear a message" but **how does a control system
absorb disruptions**, when they come in many kinds and each kind wants its own short-term response.

## 1. What the harness actually does, and why it is valuable

A long Claude Code session is interrupted all the time. Claude Code writes a message typed while the agent works
into the turn at its next step ("the user sent a new message while you were working"), and background agents,
hooks, failing commands and finished subagents arrive the same way. What the session does with each is not one
behaviour but a quick sort followed by one of a handful of moves:

- **A status question** ("is the storage branch merged?", "what is running?"): answer from what it holds, and
  carry on. Nothing in flight changes.
- **A redirect of work in flight** ("check the flag ramp first", "not WebP"): change the current step, or tell
  the subagent doing it, and carry on from there.
- **New work** ("also, the Fit page is thin"): note it, queue it, maybe start it in the background. The current
  step is not disturbed.
- **A change of priority** ("that review can wait"): reorder; sometimes drop what is under way.
- **A constraint or invariant** ("never commit the transcript"): applies to everything in flight and everything
  later, so it is checked against current work and then remembered.
- **A stop** ("stop", "don't push that"): halt at once, before the next outward act, then report state.
- **Thinking aloud** (the owner musing about a new user's walkthrough): take it in; build nothing.
- **A disruption from the machine, not the person**: a test went red, main moved, a subagent stalled, a command
  hung. Diagnose or re-plan; these are the same sort with a different sender.

Why it is valuable: nothing is redone because a message missed the work; the owner gets fast answers without the
work stopping; and, most of all, the *response fits the kind*. A status question never derails a worker; a stop is
never queued behind a merge; a constraint is never applied only to the one task it was said near.

What produces it:

- **The context window** holds everything in flight in one place, so "which work does this concern" is a lookup
  against what the session is already thinking about, not a search. Routing is nearly free.
- **Training** gives the sort: instruction-tuned models are strongly shaped to treat the latest user turn as the
  thing to answer, and to tell a question from an instruction from an aside. The handful of moves above are common
  conversational acts the model has seen countless times.
- **Thinking** picks the move and its timing: finish the atomic step (the tool call under way) and then switch,
  or answer first and resume.

What the harness does *not* do well, and a Coordinator would: it rarely notices that the same kind of
interruption keeps coming. Asked "what is running?" ten times, it answers ten times; at best it writes a memory or
a script when told to. That recurrence is the most interesting part of the gap, because a control system can do
it better than the session did.

## 2. Classical parallels, and where they fall short

- **Disturbance rejection by feedback.** Any flow on a goal's stock that the loop's valve does not set is a
  disturbance (SPEC §7, derived); integral action rejects a step of it. This covers disruptions whose effect is on a
  measured stock and whose right response is "push back the same way every time". It treats every instance as one
  signal on one channel, which is the owner's objection.
- **Feedforward.** A *measured* disturbance is compensated before it reaches the output. Answering a status
  question before it is asked (a view that shows it) is feedforward on a recurring disturbance.
- **The internal model principle** (Francis and Wonham). To reject a class of disturbance asymptotically, the
  controller must contain a model of what generates it: an integrator for steps, an oscillator for a sinusoid.
  This is the formal statement of "categorise them": absorbing many kinds of disruption needs a model of each kind
  inside the system. It falls short only in that the classes here are semantic, not spectral.
- **Ashby's law of requisite variety.** A regulator can absorb only as much variety in its disturbances as it has
  responses. The harness's value is variety; one routing rule for every message has a variety of one.
- **Supervisory (switching) control and gain scheduling.** A supervisor detects the regime and switches among
  controllers, each tuned for one (Morse's multi-model switching; hybrid automata). The handful of moves in §1 are
  the controllers; the sort is the switching law.
- **Fault detection and isolation, then reconfiguration.** Residuals are generated, the fault is isolated to a
  class, and fault-tolerant control reconfigures. Covers the disruptions that come from the machine.
- **Interrupt handling in real-time systems.** Priority levels, masking during critical sections, and a short
  handler at interrupt time with the slow work deferred (top half, bottom half). Covers *when* a running block may
  be disturbed.
- **Service management's triage** (incident, request, change, problem). A service desk classifies every contact on
  arrival and runs each class through its own process; **problem management** looks for contacts that recur and
  removes the cause, so they stop coming. This is the closest whole parallel, and it is the dashboarding idea: a
  status question that keeps coming is a problem, and its fix is a better instrument.
- **System dynamics: buffers.** A stock absorbs variability between an inflow and an outflow; its adjustment time
  says how fast. A queue of disruptions per class is a buffer the class's handler drains at its own rate.

Where they fall short of the harness: each classical tool assumes the class is known in advance and the response
is numeric. The harness classifies on the fly from meaning, and its response is often structural (tell a worker
something, reorder a queue, add a rule). The classical toolbox gives the *shape* (classify, switch, buffer, learn
the generator); the classifier and some handlers have to sit on higher rungs of the ladder.

## 3. What ergostat already has

Honestly, a good part of the plumbing (SPEC §12h, built last night on branch `messages`):

- The owner's words as `ergostat.message` items, sent from the CLI, the pages, MCP or a sensor relay; states
  received, routed, delivered, unrouted, answered; `missed` when the work finished first.
- Routing in order: explicit `about`, mentions, then a classifier block (an `ai` block on a cheap model, with route
  lines) or a free stand-in that scores items by shared words.
- Delivery live into a running Claude Code session (stream-json, mid-turn), by resume after the turn, into a
  block's next input, or as a follow-up or reopen of finished work.
- Measures (`ergostat.messages.unrouted`, `awaiting`, `missed`, `reached`), and the-job models the owner's notes as a
  disturbance flow (`notes-said`) with a goal holding unrouted at zero.
- Disturbances are derived structure (SPEC §7, §12), loops reject them through goals, and a command that arrives
  while a block runs is held, not queued (anti-windup, §9.1).
- A system's `show:` (§4a) is already a control panel: the measures a box shows when drawn closed. The-job's morning
  brief is a program that ranks what is off. These are the existing dashboards.

What is missing:

1. **Every message is one kind.** Routing answers only "which work", never "what kind of disruption". The response
   is therefore always the same: put the words in front of the work and let it cope. The strategy choice is hidden
   inside the receiving AI block, the smell the owner named. A status question sent this way costs a worker's turn.
2. **No recurrence loop.** Nothing counts what keeps being asked or said, so nothing ever removes the cause. The
   unrouted stock has only one outflow: the owner routing by hand.
3. **Disruptions from the machine are elsewhere.** Findings, failed runs, main moving and stalled sessions are not in
   the same structure as the owner's words, so they are not triaged alike.
4. **No preemption policy.** A stop or a redirect cannot hold or abort a block's run except by talking to its
   session.

## 4. Candidate designs, as control structure

### A. Triage as a switching supervisor over class queues

One inflow, `disruptions-arriving`, fed by the owner's messages and by machine disruptions (a finding raised, a run
failed or timed out, main moved). A **classifier valve** splits it into one flow per class, each into a stock (a
queue) drained by that class's handler. The classifier is the supervisor's switching law; each handler is the
controller for one regime.

- Ladder: rules first (a `?` with no imperative, `stop` and `don't`, an explicit `about`), the existing stand-in
  next, a narrow AI (haiku) for the residue. Handlers as low as they can go: status answered by a **program** that
  reads the record (items, goals, runs, the system's `show:`), with an AI only to phrase a summary; redirect by the
  existing delivery; reorder by the prioritiser (2.15) moving a queue, no worker needed; new work by intake (2.11);
  constraint by proposing a decision or correction (2.12/2.13); stop by an interlock (below); aside recorded only.
- SD view: a split of one inflow into class stocks, each with its outflow; misclassified work as a flow back to the
  unclassified stock when the owner re-routes. Control view: a supervisor block switching among handler blocks, the
  class queues as buffers between.
- Measured: per class, time from arrival to response; work redone because a message missed it (already measured);
  re-routes by the owner (misclassification); worker turns spent on status questions (should fall to zero).

### B. Problem management: a recurrence loop per class, to the modeling subsystem

The slow loop beside A, two time scales as in adaptive control. For each class, an item sensor counts arrivals by
topic over a window (topic: the parts and items the message was routed to, or the classifier's label). A goal holds
recurrence low; while it is off, a **class improver** (an `ai` block, on the narrow-AI or agent rung) proposes the
change that would have made the disruption unnecessary, as an ordinary `propose` line that the modeling subsystem
checks and judges:

- status on topic T keeps coming: a measure added to a system's `show:`, a sensor on what was asked, a section of
  the morning brief (feedforward: the answer is shown before it is asked);
- redirects of the same kind keep coming: a correction proposed (2.13), and the worker's context recipe given it;
- the same constraint keeps being said: an invariant proposed (2.3), checked on all work;
- new work of one shape keeps arriving by hand: an intake rule or item kind proposed;
- a class that keeps going unrouted: a new class proposed, or a handler.

This is the internal model principle made into a loop: the system learns a model of what generates each class and
builds its compensation into the structure. Measured: arrival rate per class and topic falling after an accepted
change, held out by the judge as any model change is (the fit's equivalent here is the recurrence rate itself).

### C. Preemption as interlocks and masking on valves

For the stop, reorder and redirect classes: a block declares how it may be disturbed, in the vocabulary of
interrupts. `preempt: at-step` (taken at its next step: today's live delivery), `at-run` (masked until the run ends:
resume), `hold` (the valve is closed by an interlock; the run finishes its atomic step and waits), `abort`. The
stop class's handler is an interlock on the block's valve, like any interlock 2.5 designs, so a stop never queues
behind work. This shares the rate-of-change question with 2.1: a redirect is a setpoint change for a running
controller, and the default for a trusted block may be "let it finish, revise after".

Measured: cost spent after a stop; work redone after a redirect taken late.

### D. A disturbance observer for unannounced disruptions

Not every disruption is said. A stock's unexplained change (`ergostat.model.unexplained`, the residual) is a
disturbance estimate. When it is large on a stock a goal holds, the observer raises it into the same triage inflow
as a machine disruption, with the stock as its topic. It is cheap and reuses what the fit already computes, but
belongs to A's sources rather than standing alone; its recurrence is already modeling's own error signal.

### A sketch of the strongest (A with B), expanded into parts

Written out, so both views can analyse it. Repeated per class, it is a natural **library part** parameterised by the
class name, its handler and its recurrence setpoint; the-job and image-squeeze would use the same part.

```yaml
stocks:
  disruptions-unsorted:   {unit: messages, sensor: {items: ergostat.message, state: received}}
  status-questions:       {unit: messages, sensor: {items: ergostat.message, state: routed, where: {class: status}}}
  status-recurrence:      # status questions per topic, the worst topic, over a week
    unit: messages
    sensor: {items: ergostat.message, entering: answered, where: {class: status}, per: topic, pick: max, over: 7d}
flows:
  disruptions-arriving:   {to: disruptions-unsorted}          # the disturbance, measured
  sorted-status:          {from: disruptions-unsorted, to: status-questions}
  sorted-redirect:        {from: disruptions-unsorted}        # into the existing delivery
  status-answered:        {from: status-questions}
goals:
  status-answered-fast:   {stock: status-questions, hold: "<= 0", tolerance: 1}
  status-rarely-asked:    {stock: status-recurrence, hold: "<= 3"}
blocks:
  triage:                 # the switching law: rules, then the stand-in, then haiku for the rest
    type: program
    run: $ERGOSTAT_CMD triage
    out: {status: flow.sorted-status, redirect: flow.sorted-redirect}
  status-answerer:        # program rung: answers from the record, never interrupts a worker
    type: program
    goal: status-answered-fast
    run: $ERGOSTAT_CMD status --answer
    out: flow.status-answered
  dashboard-improver:     # the slow loop: proposes the view that would have answered it
    type: ai
    goal: status-rarely-asked
    context: modeller
    out: flow.view-changes-proposed
```

(The `where:` and `per:` keys on an item sensor are illustrative; the point is the stocks, flows and two loops, not
the keys.)

### The modeling subsystem's role

- **It owns the slow loop's output.** Every structural response to recurrence (a measure on a system's `show:`, a
  sensor, a brief section, a new class, a correction or invariant) is a `propose` line, checked and judged like any
  model change. The class improver never edits the model.
- **Its focus is the neighbourhood of the recurring topic**: the parts and items the recurring messages were routed
  to, their systems' `show:`, the goals that hold them, and the messages' words verbatim. The whole model only when a
  new class is proposed, since that changes the switch.
- **Rate of change.** The fast loop (triage and handlers) never changes the model; it responds. The slow loop changes
  it at the judge's pace, after a hold-out, so a burst of questions on one afternoon does not rebuild the dashboards.
  Running work is not paused for a change to classes or views: none of them touches a running block's valve. A
  change to a handler's preemption policy waits until that block is idle.
- **Misclassification is its evidence.** Owner re-routes and answers judged wrong are the residual of the switching
  law, the signal for refining the classes.

### How we would know parity was reached

- From the parity benchmark (F3): replay the owner's mid-work messages from the session's transcript through triage;
  score the class and the move against what the session actually did next.
- Worker turns spent on status questions near zero; status answered within seconds by a program.
- Recurrence by topic falls after accepted view changes (the harness's own baseline is flat: it never learned).
- Missed and redone work no worse than today's (the-job: reached 0.82); stops honoured before the next outward act.

## 5. Recommendation

Build **A with B**, triage as a switching supervisor over class queues, with a recurrence loop per class feeding the
modeling subsystem; take **C** from 2.1 and 2.5 rather than inventing a policy here (the stop handler is their
interlock, a redirect is their rate-of-change question); fold **D** in as a source of A.

Reasons: it is the classical shape (supervisor, buffers, internal model, problem management), so both views can draw
and analyse it; it moves the strategy choice out of the receiving AI block and into structure, and pushes most
handlers down the ladder; and B is where ergostat can exceed the harness's baseline, since the session never learned
from repeated interruptions.

On the old plan's Build and last night's work:

- **Keep**: the message item, sending from every surface, routing to work in flight, live and resume delivery,
  follow-up and reopen, the missed sweep and the measures. They become the **redirect** handler and its measures.
- **Change**: routing gains a first step, the class, before "which work"; status questions stop being delivered to
  workers; the unrouted stock gains outflows other than the owner (an aside class, a short clarifying reply); machine
  disruptions enter the same inflow. The class is recorded on the message by the route line, but the design is the
  split and the loops, not that field.
- **Retract**: the assumption that every message is one kind and that its response is always delivery, and
  "redone because missed" as the gap's only measure.

## 6. Open questions for the owner

- Is the class list in §1 the right starting set, or should classes be discovered from the record first?
- May the slow loop's view-only changes (a measure on a system's `show:`, a brief section) be accepted automatically,
  since they change no control?
- Should disruptions from the machine (findings, failed runs, main moved) share the owner's triage, or keep their
  own path?
- When a status question cannot be answered from the record, should it go to the work in flight or to the owner's
  morning brief as a gap?
- Should the triage part ship as a maintained library part, or stay in each example until a library mechanism exists?
