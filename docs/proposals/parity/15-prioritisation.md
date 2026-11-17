# 2.15 Filtering by value: prioritisation as control structure

Status: exploration, 2026-11-17. One of sixteen parity explorations; it replaces the "value judge" answer of
[harness-parity-plan.md](../harness-parity-plan.md) §2.15 with a control-structure answer. Read with
[harness-as-control-system.md](../harness-as-control-system.md) §3 (the product-owner agent that drifted) and §5
(function 15).

## 1. What the harness actually does

A long Coordinator session does four distinct things that all get called "filtering by value":

1. **Admission.** Before a piece of work exists, it decides whether it should. It declines scope creep ("that is
   a new feature; not now"), treats the owner's thinking aloud as discussion rather than a request, and refuses to
   spend effort on small polish when the standing instruction is to keep the automated run moving.
2. **Ordering.** Of the work that is admitted, it picks what to do next, and re-picks whenever something arrives:
   a message, a failing test, a finished subagent. It does this ad hoc, every turn, with no fixed rule.
3. **Substitution.** It proposes a cheaper path to the same outcome (reuse an existing page instead of a new one,
   a measurement before a design). This is not ordering: it reshapes the work so it costs less for the same effect.
4. **Deferral.** It queues instead of building: writes the idea down (a note, an open question) and leaves it,
   so it is not lost and not done.

Where the value estimate comes from, concretely:

- **The context window.** The owner's own words in this session and the standing notes loaded at the start
  (memory files, CLAUDE.md): which outcomes matter, what was rejected and why, which kinds of work the owner
  considers waste. The parity bench (plan §4) found the owner's messages alone carry most of what matters (0.94),
  and that docs and memory carry outcomes but not rejections; rejections are exactly what admission needs.
- **Thinking.** Before acting, the model compares the proposed step with the goal it was given and with the
  last few corrections. That comparison is the value estimate; it is done per step, freshly, with whatever the
  context holds now.
- **Training.** Priors that are not in any file: YAGNI, "smaller diffs are better", a sense of what users of a
  product care about, a cost of complexity. These priors are why the harness often filters well with no
  instruction at all, and also why it sometimes filters badly: training also pushes towards being helpful by
  producing more, which is the product-owner agent's drift.

Why it is valuable: every unit of work admitted costs twice, once to build and again forever as complexity
(maintenance, reading, coherence with later decisions). A Coordinator that admits less, and orders what it admits
by what moves the owner's outcomes, buys more outcome per unit of effort and keeps the stock of complexity from
growing faster than value. Its failure mode (from the harness note §3) is the same mechanism with the value
estimate unmeasured: the stock of features grows, the outcome does not, and nothing pushes back.

## 2. The classical parallels

This is one of the best-studied problems there is; the disciplines have names for each of the four pieces.

**Ordering: queue disciplines and the c-mu rule.** Operations research and queueing theory treat "what next"
as a *service discipline* on a queue: FIFO, static priority classes, preemptive or not, weighted fair queueing.
For a single server with linear delay costs the optimal discipline is known: serve in decreasing order of
*c times mu* (cost of delay per hour, times service rate; Smith's rule, the c-mu rule). Product development's
**WSJF** (weighted shortest job first: cost of delay over duration, Reinertsen) is the same rule with guessed
numbers. When value is uncertain and learned by doing, the optimal index is the **Gittins index** (a bandit
problem): it is why a harness sometimes does a cheap probe first. **Priority ageing** (a waiting item's priority
rises with time) is the standard cure for starvation of low classes.

**Classes of service.** Kanban's expedite, fixed-date, standard and intangible lanes (each with its own
cost-of-delay profile and WIP limit) are classes in the queueing sense; Kubernetes' PriorityClass and
criticality-based load shedding ([research/sre-control-systems.md](../../research/sre-control-systems.md)) are the
same idea in infrastructure.

**Admission: admission control and load shedding.** Telecoms' call admission control and a server's load
shedding decide at the door, by class and by current load, what enters. The threshold is not fixed: it rises
as the system fills. That is a balancing loop, and it is exactly the loop the product-owner agent lacked.

**Allocation in system dynamics.** SD models a scarce resource shared by competing demands with allocation
structures: Vensim's `ALLOCATE BY PRIORITY` and `ALLOCATE AVAILABLE`, or Sterman's attractiveness-weighted
allocation (Business Dynamics). The backlog is split into stocks by class, and capacity flows to each by a
priority-weighted share. It is analysable: the replay can say what a different priority would have done.

**Among goals: override control and the cost function.** In control engineering, priority between goals is
either a **selector** (override control: high or low select, safety before throughput; ergostat's `select`
block) or the **weights of an objective** (MPC's Q and R: how much each goal's error costs against how much
effort costs). Lexicographic or hierarchical MPC gives strict levels. Substitution, finding a cheaper action for
the same effect, is what the effort penalty R does in an optimising controller. Changing which weights apply
by operating regime is **gain scheduling**.

**Batch and re-emit.** The owner's suggestion of a stream that waits to collect a batch and re-emits it in
priority order is a *priority scheduler with a sequencing window*: routers do it per link, batch schedulers do it
with release times, and a rolling-horizon scheduler is receding-horizon (MPC) scheduling. The window trades
latency (every item waits up to the window) for ordering quality (more to choose from). It is only needed
where work is *pushed* to its consumer; where the consumer *pulls* from a stock, the stock is the batch, and the
ordering is applied at the moment of the pull.

**Estimating the hidden value: an observer.** The owner's values are a hidden state, measured noisily (an
override, a dismissal, a correction, a verdict that work was not as meant). Estimating a hidden state from noisy
measurements is a **state observer** (a Kalman filter, in the linear case); updating the weights a scheduler uses
from realised outcomes is **adaptive control** (model-reference or self-tuning).

**Where they fall short of the harness.** Each classical discipline assumes the value (the class, the cost of
delay, the weight) is *known at arrival* and expressed in a few numbers. The harness reads it out of prose: a
proposal's text against the owner's rejections, at the moment it matters. The classical tools also assume work
arrives from outside; the harness's hardest case is work it generates itself, where the inflow's source and the
filter are the same mind. And substitution, reshaping an item, has no queueing analogue at all; it is design, and
belongs to the AI that does the work, not to the Coordinator. So the parity question is narrower than it looks:
ergostat needs the classical structure for admission and ordering, an estimator at the door that turns prose into
the few numbers the structure needs, and an outer loop that corrects that estimator from what the owner later did.

## 3. What ergostat already has

- **Stocks of items are queues.** A stock counted from items (SPEC §5a, §6 `items:`, `state:`) is a queue, and a
  sensor's `where:` can split it by a field, so a backlog by class is already plain YAML. `measure: oldest` is
  the age of its head.
- **Ordering lives inside blocks, unseen.** image-squeeze's developer takes the oldest proposed hypothesis
  (`examples/image-squeeze/bin/lab.py`, `claim`, sorted by first event); the software factory's developer sorts
  bugs before features, then by a `priority` field, then by age (`examples/software-factory/bin/factory.py`,
  `claim`); the-job's programs are oldest-first (`bin/job.py`). Each is a dispatcher hidden in a worker: the
  smell the owner names. Nothing in the model knows the discipline, so nothing can analyse or tune it.
- **Priority among goals, partly.** `critical: true` on a goal, the `select` block (`pick: min | max | first`,
  override control, §9.2), and the open question of arbitration between controllers (§15, question 3, with
  `priority` named and not decided). The triage example (§13) hides prioritisation among three goals in an AI
  controller's prompt: the same smell, one level up.
- **A command can name an item** (`{"out": "block.writer", "command": {"amount": 3, "item": ...}}`, §9.1), so a
  dispatcher outside the worker can already hand it the item to work on.
- **Admission with evidence, for one kind.** Changes to the model (§12e) are admitted only with evidence, refused
  with why, judged on record held out, and accepted by policy: the template of an admission gate whose threshold
  is a measured quantity. Nothing does the same for the project's own work.
- **The value context, built last night.** Confirmed decisions with their rejected alternatives, corrections
  (§5a), the owner's messages routed to items (§12h), and recipes that render them for a scope (§12j) are the
  material the harness's value estimate reads. The intent judge (§12i) already holds finished work to them: it
  is the same estimator, used at the exit instead of the door.
- **Selection by a measure.** A block's `review:` rules (§12j) choose a depth by a measure, first matching rule
  wins: that is gain scheduling in miniature, and the same shape a regime-dependent ordering needs.

What is missing: an admission valve on work's inflow whose threshold is fed back from load and complexity; the
dispatch discipline as a part of the model (so the replay, what-if and the modeling subsystem can see and change
it); a value estimate written onto an item at admission (feedforward); and the outcome measure that closes the
loop on that estimate.

## 4. Candidate designs

### A. The dispatcher: a discipline on a stock, outside the worker

Each stock a pool of workers draws from gets a dispatcher between it and them. The stock is split into class
stocks by `where:` sensors; the dispatcher is a rule-rung block that, each time a worker is free, commands it with
the item that heads the discipline (class precedence, then a score such as WSJF with ageing). The discipline's
weights are parameters with ranges. Several orderings over one stock are simply several dispatchers, one per
consumer (developers by WSJF, reviewers by age, to bound staleness). Regime-dependent ordering is a schedule of
weight sets chosen by a measure, as `review:` chooses a depth (an incident open: incidents first).

- *Ladder:* rule. The dispatcher computes; it never judges prose.
- *SD view:* the backlog as class stocks, outflows `started` per class, capacity allocated by priority (an
  allocation equation the replay can run).
- *Control view:* a block between the queue and the worker pool, its weights as parameters, the schedule as
  gain scheduling.
- *Modeling's role:* tunes weights, WIP limits and the ageing rate as parameter changes; proposes a new class
  when overrides cluster (the owner keeps expediting one kind of item).
- *Measure:* weighted waiting time of each class against its cost-of-delay profile; how often the owner reorders
  by hand.

Alone it leaves admission untouched: it orders the drift instead of stopping it.

### B. The admission gate: a balancing loop on inflow

Proposed work enters a *proposed* stock. An admission valve moves it to the backlog or to a *declined* stock
(kept, with the reason, never deleted: a dead-letter queue the owner and the modeling subsystem can review and
resurrect from). The valve compares the item's estimated value with a threshold auxiliary, and the threshold is
set by a controller from two stocks: the backlog's length (load shedding) and *complexity*, the accumulated cost
of what was built (lines, parts, open findings, whatever the project can measure; drained by removal work). As
complexity rises the bar rises, and admissions fall: the missing balancing loop of the harness note §3, made
explicit. Self-generated work (a researcher's ideas, a product agent's features) passes the same gate as the
owner's, and its source also sees back-pressure: a proposer does not run while the proposed stock is over its
goal.

- *Ladder:* the gate and its threshold controller are rules; the *estimate* it compares is written by an
  estimator (below).
- *SD view:* proposed → admitted / declined; complexity as a stock filled by `built`; the threshold driven by
  `+stock.complexity` and `+stock.backlog`; a loop B labelled "the bar rises with what we carry".
- *Control view:* an interlock-like valve with an adaptive threshold, the outer controller setting it.
- *Modeling's role:* the threshold controller's gains; whether complexity is measured well.
- *Measure:* items the owner later calls pointless (corrections, `held` verdicts, dismissals); declined items the
  owner resurrects (false negatives); outcome moved per item built.

### C. The estimator: value as feedforward at the door, corrected by an observer

The harness's real contribution is turning prose into a value estimate. Make that one simple, reliable block, run
once per item at admission (and again when an event changes the item, such as a message routed to it), never
per pull: a narrow AI (or a program, where fields suffice) given the item and the decisions-and-corrections
context for its scope (§12j recipe), answering a handful of numbers onto the item: the outcome goal it names, the
expected effect on it, the size, the cost-of-delay class, and a confidence. That is feedforward: the disturbance
(incoming work) is measured before it reaches the plant, so the gate and the dispatcher act on it without waiting
for its effect. The loop closes after the work ends: realised value (did the named goal's error move, was it
called pointless, was it reopened, did its intent verdict hold) is compared with the estimate, and the
estimation error is a measure. Its correction is the modeling subsystem's: the estimator's recipe version and its
calibration (a bias per class, a scale per proposer), changed by proposals and judged against the record, the way
§12j's recipe outcomes are compared. This is an observer of the owner's values.

- *Ladder:* narrow AI for the estimate (one bounded call, max-cost), rules for everything that uses it, the
  modeling subsystem above.
- *Measure:* estimation error by class and by proposer; its trend after a recipe change.

### D. The priority buffer: batch and re-emit, for pushed work

For consumers triggered by events rather than pulling from a stock, a buffer holds arrivals for a sequencing
window and re-emits them in discipline order (in SD, a stock with a delayed, ordered outflow; the window a
parameter trading latency for ordering). It is A for push; most of ergostat's consumers pull, so it matters only
at the edges.

## 5. Recommendation

Build B, A and C as one parametric library part, a **prioritised queue**: a gate, class stocks, a dispatcher and
an estimator, instanced wherever a stock of items feeds a pool of workers. Many loops use this same structure (the
lab's hypotheses, the factory's tickets, the-job's documents), which is the owner's test for a library part, and
it draws out every piece that is now hidden in workers' `claim` functions. D is an option of the part for pushed
work. The reasons:

- It uses the disciplines' own tools, so the analysis, replay and what-if already apply.
- It keeps the AI where only an AI helps (reading prose into a few numbers, once per item) and puts every
  decision that uses those numbers on the rule rung, where it is simple, cheap and reliable.
- It closes the loop that failed: value is measured after the fact, so a bad estimator is visible as a measure,
  not as a slowly cluttered codebase.
- Dynamic ad-hoc prioritisation is a **manual override** (hand/auto station): an owner's message "this first"
  routed to an item (§12h) is a changeset putting it in the expedite class, WIP-limited to one, never a hidden
  reordering. Overrides are counted, and a cluster of them is a signal to the modeling subsystem that the
  discipline is wrong.

**Rate of change.** Weights, classes and thresholds are the model, so only the modeling subsystem changes them,
as parameter or structure proposals judged on record held out (the dispatcher's allocation is in the SD replay,
so a weight change can be replayed; where it cannot, a step test approved by the owner, §12d). A change takes
effect at the next pull: work in flight is never preempted by a re-weighting, as a Coordinator does not change a
running subagent's goal; only the expedite class preempts, and only by the owner's override. Changes are batched
(daily, or when the override count crosses a bound), so the discipline is stable enough for its effect to be
measured.

**What the modeling subsystem needs.** The neighbourhood of the part: the class stocks and their flows, the
consumers, the goals the items name, the override and decline record, the estimation-error measure, and the
confirmed decisions in the part's scope. Not the whole model, except when proposing a new outcome goal an
estimate keeps naming.

```yaml
# a sketch: the part expanded, for the lab's hypotheses (keys beyond today's are marked "new")
stocks:
  proposed:   {sensor: {items: hypothesis, state: proposed}}
  declined:   {sensor: {items: hypothesis, state: declined}, cumulative: true}   # the dead-letter stock
  urgent:     {sensor: {items: hypothesis, state: admitted, where: {class: expedite}}}
  standard:   {sensor: {items: hypothesis, state: admitted, where: {class: standard}}}
  complexity: {sensor: {run: bin/measure-complexity, every: 10m}}

auxiliaries:
  admit-bar:
    driven-by: [+stock.complexity, +stock.standard]
    equation: base-bar + complexity-gain * stock.complexity + load-gain * stock.standard

parameters:
  base-bar:        {value: 0.3, range: [0, 1]}
  complexity-gain: {value: 0.002, range: [0, 0.01]}
  load-gain:       {value: 0.05, range: [0, 0.2]}
  age-weight:      {value: 0.1, range: [0, 1]}        # priority ageing: no starvation

blocks:
  estimate:                      # feedforward: once per item, at the door
    type: ai
    model: haiku
    context: value               # decisions, corrections and the owner's words for the item's scope (§12j)
    in: stock.proposed
    max-cost: 0.02
  gate:                          # rule rung: estimate against the bar
    type: admit                  # new: admitted / declined, with the reason
    in: {value: item.value, bar: auxiliary.admit-bar}
    out: {admitted: flow.admitted, declined: flow.declined}
  dispatch:                      # rule rung: the discipline, outside the worker
    type: select                 # extended over items (new): class precedence, then score
    over: [stock.urgent, stock.standard]
    score: "cost_of_delay / size + age-weight * age"
    wip: {urgent: 1}
    out: block.developer         # commands it with the item to take
```

**Of the old plan's Build for 2.15.**

- *Keep:* work carries the outcome it should move and its expected cost; complexity as a stock; declining with a
  reason and the owner able to overrule; the measures "called pointless later" and "outcome moved per item".
- *Change:* the outcome becomes an information link from the item to a goal in the model, not prose; the "value
  judge" is split into an estimator (narrow AI, feedforward, once per item) and a gate and threshold controller
  (rules), so the judgement that matters is a loop the model can analyse, not a block; and ordering is added,
  which the old plan left inside the workers.
- *Retract:* "dropped" as an end. Declined work is a stock kept and reviewed, like a dead-letter queue, and the
  rate at which the owner resurrects from it is one of the gate's two error signals. Retract also any new item
  kind for value: the estimate and the class are fields of the work's own kind, folded like any others.
- *What was built last night:* decisions, corrections and recipes (§5a, §12j) become the estimator's context
  unchanged; the intent judge (§12i) supplies one of the realised-value signals (a `held` verdict is negative
  value) and its brief is the estimator's brief at the other end of the item's life; message routing (§12h) is the
  channel for manual overrides; `review:` rules are the model for regime-dependent weight sets. Claims (§12g) and
  storage are not touched.

**How we would know parity is reached.** On the parity bench, cases from the session where the harness declined,
deferred or reordered: given the proposal and the recipe, does the gate decline what the session declined, and
does the dispatcher put first what the session did first. In running examples: the share of admitted items the
owner later calls pointless falls, owner overrides per week fall, outcome moved per item built rises, and
complexity grows no faster than the outcome goal's measure.

## 6. Open questions for the owner

1. Is complexity something each project measures its own way (a sensor), or should ergostat offer one built-in
   measure of it?
2. Should work the owner proposes pass the admission gate too, or only work the system proposes itself?
3. Is a library part (a prioritised queue, expanded into plain stocks, flows and blocks) the right vehicle, or
   should these be starter YAML a project copies?
4. Should the expedite class preempt work in flight, or only jump the queue?
5. May the modeling subsystem re-weight the discipline automatically when the judge passes it, or does a change
   of priority always wait for the owner?
6. Is realised value "the named goal's error moved", or do you want to state value per item yourself sometimes?
