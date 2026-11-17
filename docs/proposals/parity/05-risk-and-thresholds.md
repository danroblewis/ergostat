# 2.5 Gating by risk, with thresholds that adapt

Status: exploration, 2026-11-17. One of sixteen parity notes; it replaces the "Build" of section 2.5 in
[harness-parity-plan.md](../harness-parity-plan.md) as a proposal, not yet agreed. Function 5 of
[harness-as-control-system.md](../harness-as-control-system.md).

## 1. What the harness actually does

Two layers produce the long session's behaviour, and only one of them is visible.

**The fixed layer is the harness's.** Claude Code has permission rules (allow, ask, deny per tool and
pattern), modes (ask for edits, accept edits, plan, bypass), a sandbox, and hooks before a tool call.
These are static: a pattern matches or it doesn't. They are the hardware interlocks.

**The layer that does the work is the model's.** Before each act the model, reading its whole context,
forms something like a risk level for that act, and compares it with a standard it brought from
training. The standard is fixed: do not destroy what you did not create, do not act outward without
leave, do not spend or publish on a guess, prefer the reversible step. What adapts is which parts of
that standard apply, and that is set by the context:

- **Where it is.** Memory says the owner is at work, so writes to the team's tracker and chat are
  off-limits entirely (a regime in which a whole category of acts is closed), while pushing to the
  owner's own repository is fine.
- **What the owner said this session.** "Act, don't ask" lowers the ask threshold across the board;
  the owner being blocked live moves "push" from after-the-full-suite to after-lint-and-own-tests.
- **What it knows about the state.** A delete is low risk when it has just listed what it made and
  removes exactly those (the owner's allowlist rule, learned after a broad delete went wrong), and
  high when it has not looked. Risk rises with the model's own uncertainty, which is why it runs
  `git status` before a merge.
- **What the act is.** Reversibility (a local commit against a force-push), blast radius (one file
  against a whole directory), visibility (local against public), and cost (a few cents against an
  open-ended agent run).

The value is the pair of outcomes it gets at once: the owner is asked rarely (the session stopped
asking about kinds of act already allowed), and almost nothing irreversible happened without leave. The
fixed rules alone cannot do this: either they ask about everything outward, or they allow too much.
The model's contribution is classifying an act it has never seen into the standard's categories, and
reading the situation to decide which clauses are in force. Its failures are equally telling: twice it
pushed with failing tests because a pipe hid the exit code, so its risk estimate was wrong because its
state estimate was wrong (2.8), not because its standard was weak.

## 2. Classical parallels

The owner suspected a classical controller here, and there are several; each catches part of it.

- **Gain scheduling** (and its discrete cousin, mode switching in hybrid and supervisory control). A
  family of fixed controllers, designed in advance; a measured *scheduling variable* chooses which is in
  force. This is the closest fit to the shape the owner described: the standard is the fixed family,
  the context is the scheduling variable. What falls short: classically the scheduling variable is a
  measured number (speed, altitude, load); in the harness it is semantic (the owner is at work).
- **Safety instrumented systems** (IEC 61508, 61511). Hazard and risk analysis (HAZOP, layers of
  protection analysis) produces a risk matrix, severity by likelihood, and each hazard gets protection
  sized to it: a *permissive* (conditions that must hold before an act may start), a *trip* (stop when a
  bound is crossed), an *interlock*. Crucially, the safety layer is independent of the basic process
  control layer that does the work. And a *maintenance bypass* deactivates a protective function on
  purpose, for a bounded time, under management of change, with the bypass itself alarmed.
- **State-based alarming and shelving** (ISA-18.2) and **operating modes** (ISA-88: manual, automatic,
  maintenance; idle, running, held). Alarm limits, and which loops run, depend on the plant's state:
  startup, normal, shutdown, maintenance. A shelved alarm comes back by itself when its timer runs out.
- **Run-time assurance, the Simplex architecture** (Sha, 2001). A capable but unverified controller
  (here, the AI) runs beside a simple verified safety controller; a small decision module watches the
  state and hands control to the safe controller when the capable one's next move would leave the safe
  region. The decision module is simple enough to analyse; the capable controller is not.
- **Reference and command governors** (Gilbert, Kolmanovsky) and **safety filters** (control barrier
  functions, Ames). Instead of allow or refuse, the governor *changes the command* to the nearest one
  that keeps constraints satisfied, and the admissible set moves with the state. Opening a draft pull
  request instead of a ready one, or a canary instead of a full rollout, is a governed command.
- **Risk-sensitive control** (Whittle's exponential criterion) and **chance-constrained MPC**. A fixed
  risk-aversion parameter (θ, or the allowed violation probability ε) is applied to a predicted
  distribution of outcomes. The parameter is fixed; the distribution comes from the observer, so the
  same act is riskier when the state is less certain. This is exactly the split the owner drew: fixed
  aversion, adapting estimate.
- **IT change management** (ITIL): *standard* changes pre-approved by category, *normal* changes to a
  change board, *emergency* changes; change freezes and maintenance windows. The old plan's "consent"
  was groping for the standard change.
- **System dynamics: drift to danger.** Rasmussen's migration toward the boundary of acceptable
  performance, Vaughan's normalisation of deviance, and Sterman's *eroding goals* archetype: a threshold
  that relaxes each time nothing bad happens is a reinforcing loop that ends in an accident. Any
  "threshold that adapts with trust" must be analysed for it.

Where they fall short of the harness: every classical scheme enumerates its hazards and categories in
advance, over a known plant, and its scheduling variable is measured. The harness classifies novel acts
(an arbitrary shell command) on the fly and reads a semantic situation. That classification, and the
reading of the situation, are what ergostat has to supply from structure, with the AI rungs used only as
sensors.

## 3. What ergostat already has

More than the old plan credited.

- **A human valve:** `mode: advise` on a machine block (SPEC §9.3; `spec/engine.py`), whose commands
  wait for approval, asked again only on a new command; `person` blocks. Static, per block, binary.
- **A categorical gate inside modelling:** the judge's `accept:` map by change kind (SPEC §12e):
  parameter changes written automatically, structure waiting for the owner. That is a standard-change
  table with three categories, and the modelling subsystem already runs on it.
- **A bounded, approved experiment that deactivates loops:** the step test (SPEC §12d). It needs the
  owner's approval, holds the loop's own blocks still (the loop is put in manual for its span), keeps
  the setting inside `limits:`, stops early when the error passes a bound (a trip), and restores the
  setting. That is a maintenance bypass with permissives and a trip, built once for one purpose.
- **Limiters and override control:** `limit` (clamp and rate), a run's `max`, and `select: min`
  (SPEC §9.2), which is classical override (selector) control: the safer of two commands wins.
- **Staged exposure with trips:** image-squeeze's `rollout` and `rollback` (`rollout.yaml`): traffic
  in stages while evidence accumulates, held back while the service's goals are off (a permissive), and
  `candidate-sound` a critical goal whose breach drops the candidate (a trip).
- **The cost of skipping a gate, modelled:** the-job's `safety.yaml`. Ramps not decided in time go
  ahead unreviewed into a stock of latent hazard, 45% of which break their service after a delay. Risk
  realised as a material delay is already drawable.
- **Track record as a measure:** `ergostat.trust.contradicted@block` (SPEC §12g), and a recipe's
  `review:` set by a measure (SPEC §12j): verification effort already scheduled on a measured variable.
- **Critical goals** (SPEC §8), watched for decay.

What is missing: there is **no risk reading of an act** (gates read nothing but "a command arrived");
**no operating regime** that changes which gates and loops are in force; **no categories of act** for a
gate to look up; and outward acts are not yet a flow ergostat sees before they happen (they happen
inside a block's run). The old plan's consent items were not built (the progress log has nothing for
2.5), so nothing built needs undoing.

## 4. Candidate designs

All four treat an outward or irreversible act as material on its way through a valve, not a question
put to the owner. The boundary matters: what an AI block does inside its own session is its harness's
business (its sandbox and permission profile); what leaves it and touches the world goes through
ergostat. That is the IEC 61511 rule of an independent protection layer, and the Simplex rule that the
decision module is not the capable controller.

### A. The scheduled gate on an outbox (Simplex with gain scheduling)

- **Stock** `acts-pending`: outward acts a block asked for (a push, a merge, a message sent, a spend over
  a figure), each an item folding its features.
- **Flows out:** `released` (to the world, done by a program block that performs it), `held` (into a
  person block's queue), `refused`, and `reshaped` (see D).
- **Sensors on each act (features, not verdicts):** category (outward, destructive, spend, model, local),
  reversibility, scope, visibility, and *staleness of the state it was based on* (how old the readings
  the block acted on are: the observer's uncertainty, 2.8). A rule table classifies known shapes; a
  narrow AI classifier (as the message router is, SPEC §12h) only labels unknown shapes, and its label is
  a reading with a confidence, never a release.
- **Auxiliary** `act-risk`: severity (from the category table) times likelihood (raised by staleness,
  by the block's contradicted-claims share, by the act's novelty). Plain arithmetic, an `expr`.
- **The gate:** a `lookup` against a threshold per regime: below it released, between it and a second
  threshold held, above refused. The thresholds are the fixed standard, a table in the model.
- **Ladder:** rule (table and gate), narrow AI (labelling the unknown), person (the held branch). The AI
  block that asked never rungs itself up.
- **Drawn:** in SD, a queue with three valves whose information links come from `act-risk` and the
  regime; in the control view, a Simplex decision block between the AI controller and its actuator,
  with the scheduling variable as a dashed input to it.
- **Measured:** a confusion matrix against the owner. Needless holds (released by the owner at once,
  unchanged) are false alarms; releases the owner reverted, or that started an incident, are misses;
  time acts wait at the gate is the gate's cost.

### B. Operating regimes: permissives, inhibits and bypasses

- **The regime is a stock** (or an auxiliary) whose value is a mode: `normal`, `at-work`,
  `maintenance`, `freeze`, `incident`, `owner-away`. Its inflows are mode changes, driven by a `schedule`
  block (a maintenance window, working hours), by goals (an incident goal off forces `incident`), and by
  the owner's messages classified as regime changes (2.4's routing, so "I'm at work now" is a sensor
  reading, not a model change).
- **Each mode is a set of permissives:** which loops run (a mode holds named blocks still, as the step
  test does), which alarms are shelved, which act categories are closed, and the gate's thresholds.
  This is where loops are deactivated on purpose: in `maintenance` the autoscaling loop is in manual
  and its alarm shelved; in `freeze` every merge is held.
- **Bypasses are leases.** A mode entered by hand, or a single act category opened by the owner ("you
  can push to this branch tonight"), carries an expiry and is renewed or lapses (2.14's vocabulary). A
  bypass active is itself a measured stock, alarmed when it outlives its window, as IEC 61511 demands.
- **Drawn:** a state stock with its transitions in SD; in the control view, a supervisory mode block
  above the loops, its outputs the hold signals into each loop.
- **Measured:** acts asked about in a mode where the owner had opened them (needless asks), loops left
  inhibited past their window, alarms missed while shelved.

### C. A risk budget: the outcome loop that adapts without eroding

- **Stock** `risk-budget`, refilled at a fixed rate (the owner's risk appetite, a parameter: this is the
  fixed aversion), drained by realised harm: reverts, incidents traced to a released act, contradicted
  claims behind a release. This is the SRE error-budget policy.
- **The gate's threshold is scheduled on the budget:** with budget left, the hold threshold sits at its
  table value; as it drains, held and refused widen; exhausted, everything outward is held.
- **Why this shape:** the threshold adapts to outcomes (a balancing loop), but it can never relax past
  the table's value, because the appetite is a fixed refill and success adds nothing beyond it. It
  answers *eroding goals* by construction: the absence of incidents does not loosen the standard. The
  loop is analysable: its polarity, delay and gain are the model's.
- **Measured:** budget burn per week; whether tightening followed harm within its delay.

### D. A governor that reshapes instead of refusing

- For categories with a safer neighbour, the gate's table names the reshaped act: a draft pull request
  instead of a ready one, a canary stage instead of full traffic, a dry run before a delete, a spend
  capped at the budget left. The act goes ahead in its admissible form at once, and the full form
  becomes a new pending act carrying the evidence of the first (image-squeeze's rollout is this pattern
  already, for traffic).
- **Measured:** acts reshaped against acts held (reshaping should replace most holds), and how often
  the full form followed.

### The strongest, sketched

A as the structure, B as its scheduling variable, C as its outer loop, shipped as one library part (a
system file a project includes, parametrised by its categories and modes). New keys are marked.

```yaml
systems:
  gate: {description: outward acts held, released or refused by risk, per regime}

stocks:
  acts-pending:
    system: gate
    sensor: {items: act, state: pending, every: 10s}     # 'act' is the part's item kind
  regime:                                                 # the scheduling variable
    system: gate
    sensor: {items: regime, field: mode, every: 10s}      # NEW: a categorical reading
  risk-budget:
    system: gate
    unit: points

parameters:
  risk-appetite: {value: 10, unit: points/week}           # the fixed aversion; changed only by modelling

flows:
  released: {from: acts-pending}
  held:     {from: acts-pending}
  refused:  {from: acts-pending}
  refill:   {to: risk-budget, equation: risk-appetite}
  harm:     {from: risk-budget}                           # reverts, incidents, contradicted releases

blocks:
  act-risk:                                               # severity x likelihood, plain arithmetic
    type: expr
    in: {sev: auxiliary.act-severity, stale: auxiliary.act-staleness, trust: auxiliary.asker-contradicted}
    expr: sev * (1 + stale) * (1 + 4 * trust)
  gate:
    type: lookup                                          # NEW: a table keyed by regime and budget
    in: {risk: block.act-risk, mode: stock.regime, budget: stock.risk-budget}
    table: tables/gate.yaml                               # category x mode -> release / reshape / hold / refuse
    out: {release: flow.released, hold: block.owner-gate, refuse: flow.refused}
  owner-gate:
    type: person
    ask: An act is held at the gate; release, reshape or refuse it.
    out: {released: flow.released, refused: flow.refused}
  maintenance-window:
    type: schedule
    table: {"sat 02:00": maintenance, "sat 06:00": normal}
    out: stock.regime
```

## 5. Recommendation

Build A, B and C together as a library part, the **gate**, and add D's reshaping as rows in its table.
Reasons:

1. It keeps the split the owner drew and that risk-sensitive control formalises. The *standard*
   (categories, severities, thresholds per mode, the appetite) is model structure and parameters. The
   *context* is readings: the regime, the act's features, the staleness of the state, the asker's track
   record, the budget left. Context adapts every reading; the standard does not move by itself.
2. The complexity is in stocks, flows, a lookup and a mode, all analysable; the only AI is a sensor
   labelling unfamiliar acts, low on the ladder, with its label checked by the table.
3. It generalises what exists rather than adding beside it: `mode: advise` becomes the special case of
   a gate with one category always held; the judge's `accept:` map becomes the modelling subsystem's own
   gate table; the step test becomes a regime (a bounded maintenance bypass on one loop).

**The modelling subsystem's role.** Only it changes the table, the categories, the modes and the
appetite. Its context for a gate change is a neighbourhood of the graph: the gate's table, the acts
held and released in the window with the owner's answers, the harm events and what released them, and
the decisions and corrections in scope (SPEC §5a). A pattern of the owner releasing the same held
category unchanged becomes a proposed row change (a `parameter` change, reasons citing those acts); a
miss becomes a proposed tightening. The judge can test either by *replaying the gate* over past acts:
how many needless holds and misses the proposed table would have made against the owner's real
answers. That is a fair counterfactual, unlike most, because the owner's answers are in the record.
Gate changes stay `accept: owner` by default: a loosening is itself an outward act of the model.

**Rate of change.** Regime changes take effect at once, because the gate reads the regime when an act
leaves the queue, not when it was asked for: acts already pending are re-gated under the new regime,
and nothing running needs pausing. The block that asked keeps working (a held act is a closed valve, not
a stopped session); if its next step depends on the act, it is told the act is held and moves on, as
2.1's trusted-valve continuation suggests. Table changes take effect between gate passes and never
recall a released act. Bypass leases lapse on their own.

**Parity, measured.** Extend the F3 benchmark with gate cases taken from the session's transcript:
every outward or destructive act it took, asked about or declined, with the owner's reaction. Replay
them through the gate under the regime the session was in. Parity is reached when the gate asks no more
often than the session did and misses no more of the acts the owner later corrected (the failing-test
pushes are the hard cases: they need staleness from 2.8, not a stricter table).

**What to keep, change or retract from the old plan.**

- *Retract* the `ergostat.consent` item kind and the word. A single approval is not a threshold and
  adapts nothing.
- *Change* "a second identical approval is not asked" into a measure (needless holds) that feeds a
  modelling proposal to change the table, so learning goes through the one path allowed to change the
  model.
- *Change* expiry and revocation into bypass leases with renewal, for temporary openings only.
- *Keep* that every gated act names what released it: the table row, the regime, the risk reading and,
  if held, who released it, as fields on the act's events.
- *Keep* the goal on repeat asks, as one side of the confusion matrix, never alone (alone it is a goal
  that rewards releasing everything).
- Nothing built last night needs retracting. Last night's work feeds the gate: trust measures (12g) as
  a likelihood input, messages (12h) as the regime's sensor, decisions and corrections (§5a) as the
  modelling subsystem's context for table changes, and the intent judge (12i) as a source of harm
  events (work released that was against a decision).

## 6. Open questions for the owner

- Should outward acts be withdrawn from AI blocks' sessions entirely (they ask, ergostat performs), or
  is gating at the session's start, by setting its permission profile per regime, enough for now?
- Which regimes matter first: at work against at home, maintenance windows, freezes, or incidents?
- May the gate loosen its own table automatically when replay shows only needless holds, or is every
  loosening yours to accept?
- Is a fixed risk appetite refilled per week the right shape for the fixed standard, or should the
  standard be the table alone with no budget?
- Should the modelling subsystem's own `accept:` map be rewritten as an instance of the same gate part?
