# Parity 2.1: revising goals and control structure

Status: exploration, 2026-11-17. One of sixteen notes on how ergostat recovers what a long agent session
did as a Coordinator ([harness-as-control-system.md](../harness-as-control-system.md) §5, function 1;
[harness-parity-plan.md](../harness-parity-plan.md) §2.1). It replaces that plan's answer for this gap.

## 1. What the harness actually does

The old plan read this function as "the agent revises a setpoint". That is too narrow. When a session
writes a plan, a decision or a line of thinking into its context, every later token is generated
conditioned on it. The written text does not just move one reference value; it re-wires the session's
control system:

- **New sensors.** "Run the browser audit after every diagram change" becomes a check the session now
  takes after each edit. Nothing outside the context added it.
- **New stocks.** A todo list is a stock of open sub-goals with an inflow (decomposition) and an outflow
  (ticked off). A list of "flaky tests seen" is a stock it now watches.
- **New or wrapping controllers.** "Before merging, check `git status`" wraps the merge actuator in an
  interlock; "if a subagent's report overreaches, read the diff" wraps delegation in a verification loop.
- **New equations and setpoints.** "Good enough is the render test passing on every view" redefines the
  done-condition and the measure it reads.

Three things make this valuable. It is **immediate**: the revision is in effect at the next token, with
no handoff, so re-planning after every observation (receding horizon) costs nothing. It is **contextual**:
the revision is made by the reasoner holding everything it has seen, so it is coherent with the owner's
words and earlier decisions in that window. And it is **tentative**: a plan revised now can be revised
again in a minute without anyone approving it. Training produces the habit (long-horizon tasks reward
decomposing, checking, and re-planning), and Claude Code's design reinforces it: a todo tool that makes
the plan an explicit stock, and reminders injected when that stock goes stale (a sensor on the plan, with
a nudge).

The cost is equally real: the structure is invisible to the owner, lost at compaction, unmeasured, and
free to drift. The product-owner agent's decline is this function failing: it revised its own goals
toward what was easy to produce.

**The Coordinator's part is different from the agent's.** Inside a subagent, re-planning is the
subagent's harness, and not ergostat's question. What the Coordinator did was: read each report in light
of everything, decide whether the plan (the control structure across all the work) should change, and
then choose *when* the change reached the work. In practice it almost never changed a running subagent's
goal. It let the run finish, then rewrote the next brief; it interrupted only when the run was clearly
wasting effort; and occasionally it sent a running worker a note. That timing choice, made per case, is
most of the value, and it is what this note is about.

## 2. Classical parallels, and where they fall short

- **Receding-horizon (model predictive) control.** Re-plans the reference trajectory every step. Its
  model and constraints are fixed; only the trajectory changes. The agent changes the model too.
- **Adaptive control** (self-tuning regulators, model-reference adaptive control). Parameters adapt;
  structure is designed in advance.
- **Gain scheduling and switched (supervisory) control.** A supervisor switches among pre-designed
  controllers by a scheduling variable or by which candidate model explains the data best (Morse,
  Hespanha). Its key result is the one this gap needs: switching among controllers that are each stable
  can make the whole unstable if it switches too often, so a **dwell time** (or an average dwell time)
  bounds the rate of switching. That is the classical answer to "how fast may the structure change".
- **Bumpless transfer.** When a loop moves to a new controller or mode, the new one is initialised from
  the old one's state so the actuator does not jump. Changing a running worker's goal by a message, rather
  than by killing and restarting it, is bumpless transfer.
- **Time-scale separation in hierarchical control.** An outer loop is made several times slower than the
  inner one, so the inner settles between outer moves. A Coordinator that does not retarget a subagent
  mid-run is honouring this rule.
- **Reference governors and setpoint rate limits.** A setpoint change is filtered so constraints hold
  during the transition.
- **Management of change** (process industries). A change to a running plant's control configuration is
  classified, reviewed, and either made online (with bumpless transfer) or held for the next turnaround.
  This is the pause-or-continue choice, institutionalised.
- **System dynamics: drifting (eroding) goals.** Sterman's archetype: a goal formed by anchoring on
  performance drifts down when performance lags. Self-revised goals are this structure; its antidote is
  an anchor the actor cannot move (the owner's intent). **Double-loop learning** (Argyris) names what the
  agent does: not just correcting action toward a goal, but revising the governing goal and rules.

Where they fall short: every classical case assumes the candidate structures were designed beforehand
and are few, or that engineers change structure offline. The agent invents new structure, from semantic
content, in seconds, and much of it is provisional. None of these say how to decide well what the new
structure should be; they say how to switch safely and how often. That division is useful: ergostat's
modelling subsystem supplies the deciding, and the classical results supply the switching.

## 3. What ergostat already has

Honestly, a good deal of the mechanism, and none of the timing.

- **Setpoints moved within a fixed structure are operating, not modelling.** A block's `out` may be
  `goal.X`: an outer loop sets an inner goal's setpoint (SPEC §9, §13 "Cascade"). A `limit` block with
  `rate` is a setpoint rate limit (§9.2). So "revise a number" is already covered without touching the
  model, and should stay so.
- **Any block may propose a change to the model** (`propose`, §12e), recorded as an
  `ergostat.model-change` item, checked, judged on held-out record, and accepted by the owner or the
  judge's `accept` policy. The modelling subsystem is plain YAML in each example
  (`examples/image-squeeze/model.yaml`): `model-error`, pending, testing, passed and accepted changes, an
  improver, a judge.
- **The agent's thinking and plan are already in the record.** A session's transcript is folded as
  `claude.message`, `claude.tool-use` (todo writes included) and `claude.thinking` events, each with an id
  and its `causedby` chain (§5a, "Claude Code transcripts as events"). A revision can therefore cite the
  exact lines that led to it.
- **The brief, and a message channel into a running session.** Context recipes (§12j) render a session's
  starting context, with a `model` part (the item's parts and their goals). Messages (§12h) are delivered
  live into a running `claude -p` session at its next step, or queued for its next turn.
- **Anchors.** Confirmed `ergostat.decision` items (§5a) and the intent judge (§12i) hold finished work
  to what the owner decided.
- **A block's `decision` line** records what it decided and why.

What is missing:

1. **The rate of change is implicit and harsh.** When the model's files change, the running engine
   reloads by restarting in place, and `Runner.close` calls `kill_all()` (`ergostat/runner.py`,
   `ergostat/cli/running.py`): every run in flight, including a long AI session, is killed. Today each
   accepted change to the model is an unplanned interruption of all work, regardless of what it touched.
2. **No boundary, no dwell.** A change cannot say "after the runs it affects finish", and nothing limits
   how often one loop's structure changes.
3. **A request from running work has no focus.** A `propose` line is judged by the fit on later record;
   a structural need discovered mid-work (a new check, a new pile to watch, a wrapping loop) has no record
   yet, and the improver reviews the whole model on its own clock rather than the neighbourhood the
   request concerns. Its evidence types (findings, fit statistics, residuals, document lines, rules) do
   not include the record's own events, so it cannot cite the thinking that motivated it.
4. **Nothing measures the cost of timing**: work redone because the goal moved under it, or time held
   waiting on a decision.

## 4. Candidate designs

All four share one decomposition. A revision is a flow of **structure requests** from running work into
the modelling subsystem's queue (a stock), carrying references to its context; the modelling subsystem
decides (the only thing that changes the model); and a **valve** sets when an accepted change reaches the
work it touches. The candidates differ in that valve.

### A. Hold: an interlock on the affected neighbourhood

A structure request trips an interlock: the blocks in the request's neighbourhood (the parts it names
and the loops through them) are held, at their next step, until modelling decides. For a running
session, the hold is a message asking it to stop at a safe point and report state; for a block not yet
started, its valve stays shut.

- *Ladder:* the interlock is a rule; the decision an AI agent or the owner.
- *Drawn:* SD, a valve on the work flows with an information link from the requests stock; Control, an
  interlock block gating the actuators, fed by the request.
- *Good for:* revisions that would invalidate the work in flight (the goal itself is wrong).
- *Cost:* throughput lost while held; with a slow modeller, it is the multi-agent latency the owner
  already found slow.

### B. Continue: the agent as a trusted valve, reconciled after

The running block keeps its own revision (inside its harness) and finishes. The request waits in the
queue; modelling reconciles after the run: adopts the structure into the model, or not, and the next
briefs (contexts) carry the result. This is time-scale separation: the modelling loop is slower than the
runs it revises, and changes land at run boundaries (sample-and-hold).

- *Ladder:* modelling on the AI rung for structure, a program for applying at the boundary.
- *Drawn:* the request flow and the reconciliation as ordinary model-change flows; the provisional
  structure the agent described shown as tentative (ghost) parts in both diagrams until accepted.
- *Good for:* most revisions, and the Coordinator's habit.
- *Cost:* if the agent's revision was wrong, the run's work is wasted; measured as redone work.

### C. Notify: bumpless transfer by message

Modelling decides while the run continues; an accepted change that touches a running session is sent to
it as a message (§12h live delivery), stated as a Coordinator would state it: what changed, why, which
earlier instruction it replaces. The session keeps its state and takes the new reference at its next
step. This is the simulated Coordinator update, and it replaces `kill_all` for changes that touch a
running AI block.

- *Ladder:* a program composes the notice from the model-change item (diff, reasons); an AI only when
  the change needs translating.
- *Drawn:* an information link from accepted changes to the running block; in the Control view, a
  setpoint step into the inner loop from the supervisory one.
- *Good for:* long runs where waiting for the boundary wastes more than it saves.

### D. Scheduled: the timing chosen per change by a supervisory valve (recommended)

The timing is itself a valve, chosen per change by what is measured, not by a fixed rule: hold (A),
continue to the boundary (B) or notify (C). It starts on the rule rung with a simple table and earns a
better law from the record. It is a library part, the same for every model, because every model with
running machine blocks needs it.

- *Inputs to the valve:* which goals the change touches (an owner-anchored or `critical` goal, or a
  confirmed decision, holds); how long the affected run has gone and is expected to go (old runs are
  notified, young ones finish); the dwell since the last change to that loop (inside the dwell, wait);
  and the measured redone-work rate for that neighbourhood (if continuing has been wasting work there,
  move toward hold).
- *The modelling side, focused:* each request starts a modelling pass scoped to its neighbourhood: the
  parts it names, the loops through them, and their goals, rendered by a context recipe that also carries
  the cited transcript events, the decisions in scope and the owner's words on the topic. The whole-model
  review keeps its own slow clock. Structure with no record yet is judged as declared, as an assumption
  until the record can test it (as an unfitted equation is), rather than refused for having no fit.
- *Anchors against drift:* a request that lowers a goal the owner holds, or contradicts a confirmed
  decision, goes to the owner whatever the valve says; the count of goal revisions toward performance
  (the drifting-goals tell) is a measured flow.

```yaml
# a sketch: the timing valve as structure in the modelling subsystem
defaults: {system: modelling}
stocks:
  structure-requests:            # changes asked for by running work, not yet decided
    sensor: {items: ergostat.model-change, state: checked, where: {asked_by: run}, every: 10s}
  changes-waiting-boundary:      # accepted, waiting for the runs they touch to end
    sensor: {items: ergostat.model-change, state: accepted, where: {applied: false}, every: 10s}
flows:
  work-redone:                   # runs reopened or missed because a change landed under them
    sensor: {items: ergostat.message, entering: missed, over: 1h}
  goals-lowered:                 # the drifting-goals tell
    sensor: {items: ergostat.model-change, entering: accepted, where: {lowers_goal: true}, over: 1d}
goals:
  requests-answered: {stock: structure-requests, hold: "<= 2"}
  little-redone:     {flow: work-redone, hold: "<= 0.5"}
  goals-anchored:    {flow: goals-lowered, hold: "== 0", critical: true}
blocks:
  reviser:                       # the Coordinator's judgement, focused on one neighbourhood
    type: ai
    goal: requests-answered
    context: revision            # neighbourhood + cited thinking + decisions + owner's words
    out: flow.changes-made
  when-to-apply:                 # the rate-of-change valve (rule rung to start)
    type: lookup
    in: {age: run.age, dwell: loop.since-last-change, redone: goal.little-redone.error}
    table: hold-if-anchored, notify-after-10m, else-at-boundary, dwell-15m
    out: block.apply
```

The YAML is a sketch; the keys show the shape (a queue, a valve, its inputs, the goals on its cost),
not a final syntax. What the valve commands, ergostat does: hold, notify through §12h, or wait for the
boundary, and in every case never kill a run to apply a change.

### How parity would be measured

From the parity benchmark's tasks (F3), the moments where the long session re-planned: the observation,
the revision, and when it reached the work. ergostat reaches parity when, on replays of those moments:

- **revision latency** (the observation event to the change in effect for the affected work) is no
  longer than the session's next handoff;
- **redone work** after revisions is no higher than the session's (its interrupted or discarded
  subagent runs);
- **churn** (accepted structure later reverted) and **goals lowered without the owner** stay at or below
  the session's;
- the owner's corrections about plans changed behind their back, or not changed when they should have
  been, do not rise.

## 5. Recommendation

Build D, starting with the simplest valve: **continue to the run boundary by default, notify a run older
than a set age, hold only for changes that touch owner-anchored goals or confirmed decisions, with a
dwell time per loop.** Reasons: it matches what the Coordinator actually did (finish, then rebrief; rarely
interrupt), it rests on named classical results (time-scale separation, dwell time, bumpless transfer,
management of change), it keeps the modelling subsystem the only writer of the model, and it makes the
timing a measured valve the modelling loop can itself improve, instead of a fixed rule hidden in the
engine. The first concrete step is not new structure at all: stop killing every run when the model
changes, and apply changes at the boundaries of the runs they touch.

On the old plan's Build for 2.1:

- **Retract** the `revise` output line. Structure goes through `propose` (with the run as its maker and
  transcript events allowed as evidence); setpoint values within the structure go through cascade
  (`out: goal.X`). A third path would split the one writer of the model.
- **Retract** "a work item's goal is a field, revised by the worker under its item's policy". Items are
  not tasks; a work item's description is not the control system's setpoint, and no block applies changes
  to the model itself.
- **Keep** that every field has history (F1, landed): a model-change's reasons and the goal's history
  are readable as of any time, and the intent judge must judge finished work against the goal as it stood
  during the run.
- **Change** the modelled stocks from "items with open goal revisions" to the structure-requests queue,
  the waiting-for-boundary stock, and the redone-work and goals-lowered flows above.
- **Change** the measure from "revised items accepted more often" to the latency, redone work, churn and
  drift measures above.

What landed last night touches this gap and is kept: §12h's live delivery is the notify path (and the
"messages from ergostat itself" that 2.14 plans should include accepted model changes); §12j recipes need
a `model` part that can render a neighbourhood and a part for cited transcript events; confirmed decisions
are the anchors the valve reads; the intent judge needs goal history as of the run.

## 6. Open questions for the owner

- Should a running AI session ever be held mid-run for a model change, or only ever at its boundaries or
  by a notice?
- Is "continue to the boundary, notify long runs" the right default for the timing valve?
- Which goals count as yours, so that no revision may lower them without you?
- May structure an agent asks for be drawn as tentative in both diagrams before the modelling subsystem
  decides?
- Should structure with no record yet be accepted as a declared assumption, tested later, rather than
  waiting for the judge?
- What dwell time between changes to one loop feels right to start: minutes, or one run of its slowest
  block?
- Should repeated requests for the same structure from inside one agent block be read as a sign to split
  that block into explicit stocks, flows and loops?
