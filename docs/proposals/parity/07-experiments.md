# Parity 2.7: running experiments before acting

Status: exploration, 2026-11-17. One of sixteen gap notes under the harness parity plan
([harness-parity-plan.md](../harness-parity-plan.md) §2.7; function 7 of
[harness-as-control-system.md](../harness-as-control-system.md)). Nothing here is built.

## 1. What the harness actually does

Before a consequential action the long session ran small, cheap probes whose answers changed what it
did next: it grepped for a function before adding one (does it exist already? who calls it?), re-ran the
one failing test alone (flaky or real?), measured a selection's size before designing the split view,
tried a command in a scratch folder, read a file before editing it, ran `--dry-run`, checked a hung merge
instead of re-running it. Two different values come out of these:

- **Risk estimation.** The probe moves an estimate of what the action will cost if it is wrong (how
  many callers break, whether the failure is the code or the machine). Sometimes the answer is *do not
  act*: the feature exists, the failure is flaky, the change touches more than it is worth. The probe's
  value is realised only when it can change the decision.
- **Prework.** The probe's output becomes context for the action itself: the callers found are the
  edit list, the measured size is the design's constraint. The research and the action share one
  context window, so nothing is lost in a handoff.

What produces it:

- **Training**: read-before-write and test-before-claim are habits learned from coding transcripts.
- **The harness's cost asymmetry**: reads and greps are ungated, instant and free; writes are gated.
  Probing is cheap *by construction*, so the agent probes often.
- **The context window**: the probe's result is still in hand when the action is chosen, with the
  question that motivated it.
- **Thinking**: the agent names what it does not know and picks the probe that answers that, not a
  generic checklist. The design of the experiment is chosen per question, and so is the stopping rule
  ("enough to decide").

It fails both ways: "assumed without checking" (pushing with failing tests behind a pipe), and probing
that never ends. Neither is bounded by anything but the agent's judgement.

A distinction worth keeping: many of these probes are **state checks** (2.8: `git status`, `pgrep`).
An experiment proper is a probe that tests a *hypothesis on which a decision waits*, sometimes by
intervening (re-running, trying, stepping), and whose design is chosen for that hypothesis.

## 2. The classical parallels

- **Dual control** (Feldbaum, 1960s). When the controller is uncertain about the plant, every action
  has two effects: it steers, and it reveals. The optimal dual controller balances **caution** (act
  less where the plant is uncertain), **probing** (act partly to learn) and certainty-equivalent action
  (act as if the estimate were true). This is the exact shape of the harness's behaviour: probe when
  learning would change the decision, hold back while uncertain, act when sure. Its shortfall: it is
  intractable except for small parameterised plants, and the uncertainty it reasons about is a
  covariance over parameters, not "does this function already exist?".
- **System identification with designed experiments** (Ljung ch. 13; persistent excitation, PRBS,
  step tests). Perturb the plant on purpose to learn its dynamics, within bounds, with neighbours held
  still. Shortfall: one fixed question (K, τ, θ), one loop.
- **Value of information** (Howard 1966) and **sequential testing** (Wald's SPRT): run the experiment
  only when its expected effect on the decision is worth its cost, and stop it as soon as the decision
  is clear. Shortfall: needs a prior and a loss function someone wrote down.
- **Start permissives** in process control: conditions that must hold before a unit may start (purge
  done, pressure proven). A permissive is a pre-action check wired into the sequence, not left to the
  operator. Shortfall: fixed in advance, no research value.
- **Model predictive control**: simulate the candidate move on the internal model before making it.
  In system dynamics the same is **policy testing on the model** (Sterman's management flight
  simulators): try it on the model before the world. Shortfall: only as good as the model in that
  neighbourhood, and nothing says when the model is too uncertain to trust there.
- **Progressive delivery** (canary, shadow traffic, A/B): the action itself run at reduced scope, its
  effect measured before it is widened.

Together they cover the harness's two values well: dual control and permissives cover risk, VOI covers
whether to experiment, identification and MPC cover how. What none does is *invent the question*. In
ergostat that part need not be invented either: the questions are already raised by structure that
exists (section 3), and only open-ended ones need an AI on a higher rung.

## 3. What ergostat already has

More than the old plan admitted:

- **Step tests** (SPEC §12d): a complete designed-experiment protocol for one question. A permissive
  (steady operation), a size bounded by limits and history, neighbours held still, an abort bound,
  the setting put back, owner approval, every move recorded (`steptest.*`). It is the template for
  intervening experiments, but hard-wired to one question type.
- **Experiments on the model** (§12c): what-if, sensitivity fans over parameter uncertainty, extreme
  conditions, loop dominance. A what-if is MPC's trial move; a sensitivity fan is a quantified
  uncertainty. None of them is consulted before a block acts.
- **Dry run of a model change**: `ergostat improve --try` and MCP `try_change` check a proposal on a
  scratch copy, recording nothing.
- **The judge** (§12e): an A/B test of a model change on record it has not seen, with windows as
  evidence.
- **image-squeeze's lab and rollout** (`examples/image-squeeze/lab.yaml`, `rollout.yaml`): a full
  experiment pipeline in plain YAML. Hypotheses are items counted into stocks (ideas → building →
  experiments → improvements / dropped), the candidate runs on paired traffic, the rollout widens it a
  stage at a time while it earns it (sequential testing), the rollback drops it on guards
  (`candidate-sound` is critical). This is the strongest existing answer: it is already a stock with
  flows, valves and loops, and it is domain wiring, not a resource.
- **Claims** (§12g), built last night: checks run *after* an action, by ergostat, never the claimant.
  Their checks (`tests`, `state`, `changed`, declared commands) are exactly the probes the harness runs
  *before* acting. The library of checks already exists; it is only pointed the other way.
- **Contexts** (§12j), built last night: recipes that carry what is known into a session. There is no
  part for "what was found out about the parts this work touches".
- `mode: advise` (a person approves commands) and `critical: true` goals.

What is actually missing: nothing holds **open questions about the system** as a stock; no valve on
the operations side reads **uncertainty or risk**; experiment results do not flow into contexts or into
the modeling subsystem as evidence; and the step test's protocol cannot be reused for any other
question.

## 4. Candidate designs

### A. Permissives in front of valves

A cheap probe (a program-rung block: re-run the one test, check the branch merges cleanly, check the
target does not exist) runs before an actuator's command passes, and its result feeds a `select` (pick
min) with the controller's command: zero when the permissive fails. Control view: an interlock in
series before the actuator. SD view: an information link from the probe's auxiliary to the valve.
Built from existing blocks; reusable as a library part ("permissive").

Weakness: every probe is fixed per valve, there is no learning about which probes matter, and the
results are not research for anyone. It recovers the "may decide not to act" half only.

### B. The experiments side-loop (recommended)

A small subsystem most models carry, the owner's suggestion made concrete.

- **Stocks**: `open-questions` (hypotheses on which some action or proposal waits), `running`
  (experiments in flight, WIP-limited like the one candidate in image-squeeze), `answers` (cumulative:
  results that stay on the record), `experiment-spend`.
- **Flows**: `raised` (in), `started` (open → running), `answered`, `inconclusive` (back to open, or
  out), `expired` (a question whose action went ahead or was dropped: a lease that was not renewed).
- **Who raises questions** (existing structure, mostly low on the ladder): a sensitivity fan wider
  than a goal's tolerance over the projection horizon; `ergostat.model.unidentified-loops`; the judge's
  "too few windows"; a claim left unchecked; a residual; a block that names its doubt in an `event`
  about the item it works on; the owner. An AI rung is needed only for open-ended questions.
- **Who answers** (the ladder, lowest first): ergostat's own model (a what-if of the pending action,
  free and touching nothing), the check library from §12g run beforehand (the tests on the branch, a
  merge check, a state read), a step test, a reduced-scope trial (design D), a narrow AI, an AI agent
  given a probe brief, and last a person (asking is an experiment about intent: 2.3).
- **The valve on `started`** is a prioritising controller: orders open questions by value of
  information, approximated as *actions held on the question × cost of being wrong ÷ cost of the
  experiment*, under a spend goal. That is a prioritisation projection (2.15) with a budget (2.9), and
  can be a reusable parametric part.
- **What the answers feed**, by information links:
  1. **Operations**: a `risk` auxiliary per guarded flow (the projection's chance of putting a
     critical goal off, widened by open questions on the parts the flow touches). The flow's
     controller reads it through a `lookup` (risk → allowed rate) and a `select` (min): **gain
     scheduling for caution**, dual control's caution term, from built-in blocks. At high risk with
     a cheap experiment available, the action is held and a question raised (probing); at high risk
     with none available, the block's `mode` goes to `advise` (a person decides); at low risk the
     action goes ahead (certainty-equivalent).
  2. **Contexts** (prework): a recipe part listing the answers about the item's parts, so the AI that
     acts starts with the research done, as the harness's context window did.
  3. **The modeling subsystem**: an answer is evidence a proposal can cite, and a step test or trial
     is its main way to identify a neighbourhood the record does not.
- **Loops**: B1 *uncertainty reduction* (open questions → experiments → answers → fewer open);
  B2 *caution* (open questions → risk → operations throttled → fewer new actions raising questions);
  B3 *budget* (spend → spend goal off → fewer started); R1 *research* (answers raise new questions:
  the bounded reinforcing loop that makes probing end only through B3 and the VOI valve).

Drawn: in SD, an aging chain of questions with the risk auxiliary linking out to the operations
valves; in the control view, a supervisory layer (the VOI controller) over an observer (the answers
and the model's fan as a state estimate with its uncertainty) that schedules the operations
controllers' gains. Both are standard drawings.

### C. The model as the first experiment (part of B, also usable alone)

Before a guarded action, ergostat projects it as a what-if over a horizon with the sensitivity fan
(§12c). The share of samples that put a critical goal off is the risk auxiliary. This is MPC's trial
move and dual control's caution, priced at zero world risk. Where the fan is wide, the model is the
uncertain thing, and that becomes a question for the modeling subsystem: identify here. It works only
where the action's effect is in the model; for code changes (most of the Coordinator's work) it says
nothing until the model covers the codebase's own dynamics.

### D. A trial library part (generalised rollout)

image-squeeze's rollout lifted into a parametric part: a candidate and the current way, paired, scope
stages (one item, one file, 5% of traffic, a branch), a sequential stopping rule, guards, rollback.
Parameters: the measure, the stages, the guards, the budget. It is design B's intervening rung for any
reversible action with a measurable effect. Worth building once a second model wants it.

### A sketch of B with C

```yaml
systems:
  experiments: {description: what the system does not yet know, and finding it out}

stocks:
  open-questions: {system: experiments, unit: questions,
                   sensor: {items: question, state: open, every: 10s}}
  running:        {system: experiments, unit: questions,
                   sensor: {items: question, state: running, every: 10s}}
  answers:        {system: experiments, unit: questions, cumulative: true,
                   sensor: {items: question, state: answered, every: 10s}}

flows:
  raised:   {to: open-questions}
  started:  {from: open-questions, to: running, driven-by: +stock.open-questions}
  answered: {from: running, to: answers}
  expired:  {from: open-questions}       # the action it waited for went ahead or was dropped

auxiliaries:
  merge-risk:
    unit: share
    description: chance a merge now puts a critical goal off, from the projection's fan,
      widened by the open questions on the parts the branch touches
    driven-by: [+stock.open-questions]

goals:
  experiment-budget: {flow: experiment-spending, hold: "<= 2/h"}
  questions-young:   {stock: open-questions, hold: "<= 5"}

blocks:
  choose-experiment:                     # supervisory: value of information under a budget
    type: program
    goal: questions-young
    in: [+stock.open-questions, goal.experiment-budget.error]
    out: flow.started
  caution:                               # gain scheduling: allowed merges an hour by risk
    type: lookup
    in: auxiliary.merge-risk
    table: [[0, 6], [0.1, 2], [0.3, 0]]
  merge-gate:
    type: select
    pick: min
    in: [block.merger-controller, block.caution]
    out: block.merger
```

`question` here is an ordinary project item kind counted by the stocks; a question is done when its
kind's projection says so (answered, or expired when the action it waited on moved), never by a
`done` written on it.

### How parity would be measured

- **Assumed without checking**: actions taken on a part while a question about it was open (the share,
  over time); should fall.
- **Realised value of information**: the share of experiments whose answer changed the decision
  (held, redirected, sent to a person). Near zero means the side-loop is ritual; near one means it is
  starved.
- **Wrong actions after an experiment vs without**: reopens, contradicted claims, regressions
  (`ergostat.model-change.regressed`), rollbacks.
- **Risk calibration**: the risk auxiliary's predicted chance against what happened (a Brier score).
- **Cost and latency**: spend per decision changed; age of open questions.
- On the parity benchmark (F3): the session's tasks where it probed first, redone by workers with and
  without the side-loop's answers in their context.

## 5. Recommendation

Build **B, with C as its first rung and A's permissive as how operations read it** (the caution
lookup and the gate are A, fed by B's risk instead of one fixed probe). Keep D as a library part to
lift from image-squeeze when a second model needs it.

Reasons: it puts the complexity in the control system, not in a block (each probe stays a simple
program; the deciding is a visible VOI valve and a gain schedule that SD and control can both analyse);
it serves both of the harness's values through separate links (risk to the operations valves, prework
to the contexts); it is dual control in its approximate, practical form (caution plus explicit
probing), not an invention; and most of it is built from what exists: the check library, step tests,
what-if and sensitivity, the item sensors, built-in `lookup` and `select`.

**The modeling subsystem's role.** It consumes answers as evidence (an experiment's item is evidence
a proposal can cite, a small extension to the evidence kinds of §12e) and raises the questions the
model itself cannot answer (wide fans, unidentified loops). Its focus is the neighbourhood of the
parts the question is about. It is the only thing that changes the side-loop's own structure: the
budget's setpoint, the VOI law, which flows are guarded. Experiments never change the model, only
the record it is judged on.

**The rate-of-change question.** A read-only probe or a model trial pauses nothing. An intervening
experiment pauses what it would confound, exactly as the step test already holds the loop's blocks:
the side-loop's `started` valve is interlocked with the loops whose parts it perturbs. A running AI
session is not paused for an experiment about its own work; its answer reaches it as a message (2.4,
built), or waits for its next run's context.

**The old plan's Build:**

- *Worker instructions* (measure before designing, re-run the one test): keep, but as the AI block's
  own harness, not the parity answer.
- *An `experiment` event line*: retract. An experiment is an item counted by the side-loop's stocks,
  raised and answered through ordinary events; no new output line.
- *Reviewers flag "assumed without checking"*: change to a measure of the loop (actions on parts with
  open questions), computed, not a reviewer's finding.
- *Stock "claims without evidence"*: retract here; it belongs to 2.16. This gap's stock is open
  questions.
- *Last night's work*: the claim checks (§12g) are reused as the before-acting probe library (the same
  checks run before the run, as a permissive or an answer); contexts (§12j) gain an "answers about
  these parts" part; messages (§12h) carry an answer to a running session; step tests become the
  first named intervening rung.

## 6. Open questions for the owner

- Should the experiments side-loop ship as a built-in subsystem every model has (like modeling), or as
  a library part a model adds?
- Is "question" the right word for the held hypotheses, or would you rather the side-loop count
  "unknowns" or "hypotheses" as image-squeeze does?
- May a low-risk experiment that touches the world (a re-run, a 5% trial) start without approval, as
  a passed parameter change may, or does every intervention wait for you as step tests do?
- Is a risk read from the model's fan acceptable while the model does not yet cover code changes, or
  should code work rely on the check library alone until it does?
- Should the VOI valve's notion of cost of being wrong come from the critical goals alone, or from a
  stated loss you write per flow?
