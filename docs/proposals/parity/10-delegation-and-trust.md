# Parity 2.10: delegating, and trusting what comes back

Part of the harness parity exploration ([harness-as-control-system.md](../harness-as-control-system.md) §5
function 10; [harness-parity-plan.md](../harness-parity-plan.md) §2.10). Draft for the owner, 2026-11-17.

**The short answer.** Most of this gap is not a gap. ergostat already delegates (a controller commands a machine
block, SPEC §9.4), already treats what comes back as a sensor reading to be checked (claims, §12g; the intent judge,
§12i), and last night it gained a rule that sets review depth from a measure (`review:`, §12j). A trust *stock* per
worker should be dropped: a harness does not keep one, and a share of contradicted claims is a measure, not an
accumulation. What is left is smaller and more structural: the review loop is open (rules on a proxy, written as a
key on a block instead of drawn), there is no rework structure for the work that comes back wrong, and nothing
improves briefs. Each of these has a well-known classical form. None needs a new kind or block type.

## 1. What the harness actually does

When a Coordinator session hands work to a subagent, several separate things happen, and it helps to pull them
apart because they come from different places.

- **It chooses what to hand off.** It keeps work that needs what it alone holds (the owner's recent words, a decision
  still forming) and hands off work that can be stated in a brief and checked afterwards. A large part of the reason
  is its own context budget: a subagent's reading and trial and error never enters the Coordinator's window. That
  reason has no counterpart in ergostat, which has no single window to protect.
- **It writes the brief.** This is context transfer (§7 of the harness doc): what the owner said, what was decided,
  what not to touch. It is where most delegation failures came from in this project, and it is already the subject
  of the projection recipes (§12j).
- **It reads the report skeptically.** This comes mostly from training, not from a track record. A model is taught
  to distrust "all tests pass" without output, to notice a report that claims more than the brief asked, and to
  check a diff before believing its summary. The check is triggered by the *content* of one report against what the
  Coordinator expected, held in its context: a report naming files it should not have touched, or finishing
  implausibly fast, gets looked at. This is the valuable part, and it is per report.
- **It sometimes lightens review for a reliable agent.** The harness doc credits it with "verification effort set
  by track record". On reflection that is mostly a story told afterwards. There is no score; within one session the
  Coordinator remembers that an earlier report from the same kind of agent held up, and checks a little less. Across
  sessions nothing is kept. The owner's doubt is right: harnesses do not really evaluate subagent trust.
- **It does something with a bad return.** It sends the work back with what was wrong, redoes it itself, re-briefs a
  fresh agent, or escalates to the owner. This is the rework path, and in the session it was where time went.

So the value is in four places: the brief, per-report plausibility, a rework path, and (weakly) a review effort that
falls as returns keep holding up.

## 2. Classical parallels

- **Hierarchical and supervisory control.** A supervisor sets references and modes for local controllers and does
  not move actuators itself. Delegation is exactly this, and ergostat already has it: a block whose output commands
  another block is a controller (§9.4), and an outer goal may set an inner one's setpoint (cascade, §13).
- **Acceptance sampling with switching rules** (statistical quality control: ISO 2859-1, ANSI Z1.4, skip-lot
  sampling). Incoming lots from a supplier are inspected at *normal*, *tightened* or *reduced* levels, and the level
  switches by fixed rules on recent results (for instance tightened after two of five lots rejected, reduced after a
  run of accepted lots, back to normal on any rejection). This is "review effort set by track record" in its
  engineered form: a small state machine with hysteresis, not a trust score. It is the right name for what
  `review:` does.
- **The rework cycle** (system dynamics, project dynamics: Cooper's rework cycle, Ford and Sterman, Lyneis and Ford).
  Work done flows either to *work really done* or, by one minus the quality fraction, to *undiscovered rework*;
  inspection and testing discover rework at a rate set by review effort and return it to *work to do*. The stock of
  undiscovered rework is the latent cost: it is what the owner finds later. This structure says why reviewing has
  value and what its setpoint should be.
- **Sensor validation and innovation gating** (state estimation, fault detection and isolation). An observer
  predicts the next measurement; the innovation (measurement minus prediction) is tested, and a reading whose
  innovation is improbably large is rejected or flagged before it updates the state. In adaptive filters the
  measurement noise of each sensor is itself estimated online, so a noisy sensor is weighted less. "This report
  overreaches" is a large innovation; "this agent's reports are usually right" is a small estimated noise.
- **Analytical redundancy.** A reading is cross-checked against other, independent readings rather than repeated.
  Claims checked by re-running the tests rather than reading the exit code are this (§12g).
- **Override and selector control, escalation.** When the normal controller cannot hold a variable, a selector hands
  control to another that can (split range, override). Moving work up the ladder (program, narrow AI, agent, person)
  after it fails at one rung has this shape.

Where they fall short of the harness: every classical form works on numbers, against a prediction the designer
wrote down. The harness's per-report skepticism uses a prediction it never writes down, formed from the whole
context, about the meaning of the work. Classical forms supply the loop and the bookkeeping; the prediction itself
has to come from a brief that states what is expected.

## 3. What ergostat already has

- **Delegation**: controllers commanding machine blocks (§9.1, §9.4), agents with `at-once` (§10), a machine block
  naming its goal (§9.3). A Coordinator handing an item to a worker is a command with an `item`.
- **The return as a sensor**: claim lines, checked by ergostat and never taken on the block's word (§12g), with
  `ergostat.trust.contradicted@WHO` per block, rung and model. image-squeeze's `developer-honest` goal watches it and
  correctly says nothing acts on it. This is analytical redundancy, built.
- **Semantic checking of the return**: the intent judge (§12i) holds finished work against the confirmed decisions,
  corrections and the owner's messages, and `ergostat.intent.false-done` with its tests-alone twin measures what got
  past it. This is the closest thing to the harness's skeptical reading, on the program or narrow-AI rung.
- **Briefs**: `contexts:` recipes, the use recorded on the session with its hash, and outcome measures per recipe
  (`ergostat.context.RECIPE.outcome`, §12j); measured offline in the parity benchmark (0.625 for the recommended
  worker recipe).
- **Review depth by measure**: `review:` on a machine block (`ergostat/recipes/review.py`, `spec/engine.py`
  `review()`), recording `review.required` and `review.skipped` with the value read.
- **Rework, partly**: the intent judge's `held: reopen` sends work back with the verdict as its reason, and the
  item's `intent` field carries it into the next brief through `item-history`. MODELLING.md §1 already teaches the
  stock-between-two-rates pattern with unreviewed ramps, which is the same shape as undiscovered rework.

What is actually missing:

1. **The review loop is open and hidden.** `review:` reads a proxy (the contradicted share) through a threshold, and
   its rules sit inside a block's keys, so neither diagram shows a controller, a sensor or a loop, and `ergostat check`
   cannot say whether it closes. Its true objective, escaped rework at least review cost, is measured
   (`intent.false-done`) but not read by it.
2. **No rework structure.** Held and reopened work is counted, but there is no stock of work that came back wrong and
   no stock of work accepted but not yet proved, so the model cannot say what review is worth.
3. **No per-return expectation.** Nothing in a command says what the return should look like, so nothing can gate a
   single surprising return.
4. **Nothing improves briefs.** Recipe outcomes are measured and no loop acts on them.

## 4. Candidate designs

### A. The rework cycle as a library part, with review as its discovery valve

Model delegated work the SD way. Stocks: *to do*, *returned, unchecked*, *accepted, unproved* (undiscovered rework
lives here), *proved*, *sent back*. Flows: *returned* (the worker's valve), *accepted* and *sent back* (the review's
valve), *proved* (time, or a later check), *found late* (from *accepted, unproved* back to *to do*: reopens, owner
corrections, follow-ups). The quality fraction of a worker is a parameter, identified from the record per block, rung
and kind; review depth sets the discovery rate. All the counts come from existing item states and events (§12i's
reopened, §12g's verdicts), so it is wiring plus one maintained part.

- Ladder: no new rung; the worker is whatever rung it is, the review is a reviewer block on any rung, the bookkeeping
  is item sensors.
- SD view: an aging chain with a rework loop back to *to do*; a balancing loop through review (more review, less
  undiscovered rework) and a reinforcing one through found-late rework adding load.
- Control view: the worker is the plant, the reviewer an inspection actuator, found-late rework a disturbance to the
  owner-facing quality.
- Modeling subsystem: identifies the quality fraction and the delay in *accepted, unproved*; flags a kind whose
  found-late rate exceeds its review-time rate (reviews in the wrong place).
- Measured: found-late per accepted (it is `intent.false-done`) and review cost per item.

### B. Review depth as a drawn controller: acceptance sampling with switching

Retire the hidden `review:` rules in favour of a controller that the diagrams show: built-in `counter` and `onoff`
blocks (§9.2), or one maintained library part made of them, holding a review level (reduced, normal, tightened) with
hysteresis, reading the accept and send-back flows of design A, and commanding the reviewer with a depth. It is an
ISO 2859-style switching rule, on the rule rung, with a goal that closes it: escaped rework at or under a setpoint.

- SD view: a balancing loop from found-late rework to review level to discovery rate.
- Control view: a supervisory, gain-scheduled controller; the schedule variable is the recent accept history.
- Modeling subsystem: proposes the switching thresholds (run lengths) as parameters; a tuning reaches the controller
  at its next pass, never in the middle of one review.
- Measured: at equal escaped rework, review spend falls; at equal spend, escaped rework falls. Compared with a fixed
  "always review" and "never review" over the same record by replay (§12b).

### C. Per-return innovation gating

A command that delegates states its expectation in plain fields: the item, the files or parts it may touch, the goals
it should move, a size. The return is compared on the program rung (files touched outside scope, a goal moved the
wrong way, a diff far over size, a claim of more than was asked) and the residual raises review depth for that one
return, on top of design B's level. This is the harness's per-report skepticism made explicit, and it uses the
brief, not a trust score. It overlaps 2.8 (state before, effect after) and 2.16 (claims).

- Measured: whether high-residual returns are the ones found late (precision and recall of the gate against
  found-late rework).
- Risk: the expectation has to be written by whoever delegates; when it is an AI controller, this is one more thing
  it can get wrong. Narrow AI could write it from the recipe.

### D. Escalation along the ladder, and brief improvement through modeling

A return sent back twice moves up a rung (selector control): to a stronger model, an agent with the fuller recipe, or
a person, through the existing message and reopen paths (§12h, §12i). The pattern of escalations is then evidence for
the modeling subsystem: a kind that always escalates should start higher, be split, or get a different recipe.
Recipes are part of the model, so a recipe change is a model change, proposed and judged like any other (§12e), with
the parity benchmark or recipe outcomes as the judge's evidence, and applied at the next session start, never to a
running one.

### Sketch of the strongest (A with B)

```yaml
# from a maintained library part, parameters filled per worker
stocks:
  dev-returned:      {sensor: {items: hypothesis, state: testing}}
  dev-unproved:      {sensor: {items: hypothesis, state: kept, since: 7d}}   # accepted, not yet proved
flows:
  dev-accepted:      {from: dev-returned, to: dev-unproved}
  dev-sent-back:     {from: dev-returned, sensor: {items: hypothesis, entering: building, from-state: testing}}
  dev-found-late:    {from: dev-unproved, sensor: {events: hypothesis.reopened}}
auxiliaries:
  dev-escaped:       {sensor: {builtin: ergostat.intent.false-done@hypothesis}}
goals:
  dev-escapes-low:   {auxiliary: dev-escaped, hold: "<= 0.05"}
blocks:
  dev-review-level:                # reduced 0, normal 1, tightened 2; drawn and checked like any controller
    type: lookup                   # (or the library part's counter + onoff with hysteresis)
    in: flow.dev-sent-back
    table: {0: 0, 1: 1, 2: 2}
    out: block.reviewer
  reviewer:
    type: ai
    context: reviewer
    out: {accepted: flow.dev-accepted, sent-back: flow.dev-sent-back}
```

The exact sensor keys need checking against §6; the point is the shape: two stocks around the review, the escaped
share as the goal, and the review level as a visible controller.

## 5. Recommendation

Say plainly that trust is not a gap: it is a sensor (claims, the intent judge) and, at most, a gain schedule. Build
**A and B together**, as one maintained library part (the delegated-work rework cycle with a switching review
controller), wired first in image-squeeze for the developer and in the-job for the preparers. Reasons: it closes the
loop that `review:` leaves open, it reads the measure that matters (escaped rework) instead of a proxy, it moves the
logic out of a block key into stocks, flows and a drawn controller that both views and `check` can analyse, and it is
the same structure every delegating loop uses, which is what a library part is for. Then **D**'s recipe half, as a
job for the modeling subsystem once recipe outcomes have enough record. Hold **C** until 2.8's state-before work
says what an expectation should carry; it is the only design that recovers the harness's per-report skepticism, so
it should not be dropped, only sequenced.

On the old plan's Build for 2.10:

- **Keep** projection recipes, their recorded use and outcome measures (they are the brief, and they are measured).
- **Keep** claims and `ergostat.trust.*` as measures; they are design A's sensors.
- **Retract** the trust stock per worker type and model, and the flows *briefs* and *reworked* as drawn; replace them
  with design A's stocks and flows, which are counted from items that already exist.
- **Change** `review:`: keep it working for now, but treat it as a gain-scheduled controller and move it into a drawn
  block (design B); have `check` report a `review:` whose measure no goal holds; make its default rule read escaped
  rework rather than the contradicted share.
- **Retract** "verification effort set by track record" as the headline of function 10 in the harness doc's table; the
  harness's real strengths are the brief and the per-report check.

Modeling subsystem's role here: it alone changes the review thresholds, the quality-fraction parameters and the
recipes. It needs the neighbourhood of the graph around one delegation (the worker, the reviewer, the item kind's
chain, the recipe and its outcomes, the found-late events with their reasons) rather than the whole model. Changes
take effect at the next delegation; a running worker is never re-briefed by a model change (a Coordinator would send
a message instead, which is §12h's path, not the model's).

How we would know parity: on this project's history, the Coordinator's accepted subagent returns that the owner later
corrected, against review time spent, compared with ergostat's found-late rate and review spend on the same kinds of
work; and the F3 tasks redone with the recipe and the review loop in place.

## 6. Open questions for the owner

- Is it acceptable to state in the harness doc that function 10's "trust by track record" was overstated, and to
  reframe the function as brief plus per-report check?
- Should review level be a project's own wiring of built-in blocks, or a maintained library part ergostat ships?
- Is escaped rework (`intent.false-done`) the setpoint you want review to hold, or is there a cost of review you want
  traded against it explicitly?
- Should a return that fails twice escalate up the ladder by default, or only where a project says so?
- Do you want delegations to carry an expectation (design C), knowing it adds a field every delegating controller
  must fill?
