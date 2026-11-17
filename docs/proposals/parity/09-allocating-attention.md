# 2.9 Allocating attention: parity as control structure

Status: exploration, 2026-11-17. One of sixteen gap studies replacing the first plan's answers
([harness-parity-plan.md](../harness-parity-plan.md) §2.9; function 9 of
[harness-as-control-system.md](../harness-as-control-system.md) §5).

## 1. What the harness actually does

A Coordinator session has one serial thread of control and many things in flight: background
subagents, monitors, merges, test runs, the owner's messages, its own half-finished edits. At every
step it picks one of them to serve: read a subagent's report, check a stalled run, answer the owner,
merge, or do nothing and wait. It also picks what the owner sees, and when. That choice is the whole
of "allocating attention", and it touches three scarce resources at once:

- **The Coordinator's own service capacity.** One tool call at a time, a context window that every
  look fills, and a cost per look.
- **The workers' capacity.** Which item a subagent is given, or which a pool pulls next.
- **The owner's attention.** The scarcest of the three; an interruption costs them more than any
  amount of machine time.

What produces it, concretely:

- **The context window is the queue.** Everything in flight is in it, with its recency and its last
  known state. The model's next token over that context is literally a selection among the
  candidates: which tool call, about which thing. The owner's remark is right: generation is close to
  the definition of a valve, an opening that apportions one flow (service) among competing stocks
  (things waiting).
- **Interrupts, not polling.** The harness delivers completion notices for background work and tells
  the model not to poll; a monitor wakes it on a condition. Attention is event-triggered, with
  heartbeats only where no event will come.
- **Priors from training.** A failing test, an owner's message, a merge conflict or a report that
  looks too good get looked at before routine progress; quiet is the default for good news. These are
  fixed class priorities learned once, and they are mostly right.
- **Per-item reading.** On top of the classes, the model reads the item itself: this report claims
  more than the diff shows, this agent has been silent too long for its task, this question has
  already been answered. Cost of delay is estimated per item, from semantics, not per class.
- **Switching cost.** It finishes a merge before reading the next report, batches two small updates
  for the owner into one, and does not re-load a big diff to glance at it.

Why it is valuable: the session's throughput was bounded by the Coordinator and the owner, not the
workers. Spending those two well (looking at the stuck thing early, staying quiet about the healthy
thing, telling the owner only what changes their picture) is what made many workers worth having.
The first plan's answer (a digest of what changed) covered only the third resource, and only its
output, not the allocation.

## 2. Classical parallels

- **Queueing and scheduling: the service discipline.** FIFO, static priority, weighted fair queueing,
  shortest job first. The **cμ rule** (serve the class with the highest cost of waiting times service
  rate) is optimal for linear holding costs in a multi-class queue; its lean-software cousin is WSJF
  (cost of delay divided by duration). The **Gittins index**, and for things that change while
  unwatched the **Whittle index of restless bandits**, is the textbook answer to "which running
  thing do I look at": each in-flight thing gets an index from its own state, and the highest is
  served.
- **Sensor scheduling and event-triggered control.** When to sample a process: time-triggered
  (heartbeats), event-triggered (sample when the error crosses a threshold), self-triggered (the
  controller predicts when it next needs to look). Leases with renewals and watchdogs are the
  computing form: a missed renewal is the event.
- **Alarm management for the human supervisor** (ISA-18.2, EEMUA 191). Plant operators are the
  owner's case: a budget of alarms per operator per hour, priority classes, shelving, suppression of
  floods and of consequential alarms, rationalisation (every alarm needs a defined response), and
  measures of the alarm system itself (standing alarms, chattering, alarms per hour). The owner's
  attention is the operator's.
- **Gain scheduling.** The weights of the discipline change with the operating point: when the
  backlog of things waiting on the owner grows, owner-facing work gets more weight.
- **System dynamics: attention as a scarce resource.** Sterman's management attention, and
  Repenning's **fire-fighting** dynamics: when urgent work takes the capacity meant for upstream
  work, the upstream work degrades, producing more urgent work, a reinforcing loop with a tipping
  point. Vensim's allocate-by-priority function is SD's standard tool for splitting one capacity
  among demands by priority.

Where they fall short of the harness: the classical disciplines assume costs of delay are known per
class and fixed; the harness estimates them per item, from what the item says, and notices kinds of
urgency no class was defined for. They also price switching rarely, and alarm management assumes a
human did the rationalisation beforehand. The parity question is therefore not "which discipline"
but where the per-item estimate comes from and what tunes the weights.

## 3. What ergostat already has

Honestly, the parts are mostly there; the allocation itself is hidden.

- **Interrupts and heartbeats.** Machine blocks run when commanded or on `every`/`cron` (SPEC §9.1);
  sensors have their own `every`. Owner messages are routed and delivered live into running
  sessions (§12h). That is the event-triggered half of attention.
- **Signals to weight by.** Every goal has an error and a status (§8); `proportional`, `lookup`,
  `schedule`, `select` and `expr` blocks (§9.2) can compute weights from them. Item sensors count by
  state and by field (`where:`, as the-job's `mentions-late`).
- **Shared capacity.** An agent's `at-once` is a semaphore across its blocks
  (`ergostat/spec/engine.py`, the `slots`); when two commanded blocks compete for a slot, nothing in
  the model says which goes first. Arbitration between two controllers is an open question (SPEC §15,
  question 3; a `priority` key is named there but not decided).
- **Things that need attention.** Findings (`contradicted-claim`, unrouted messages,
  `correction-repeated`, `not-answering`) surface in the status (§12, §12g, §12h). They form a flat
  list: no classes, no budget, no measure of how the owner's attention is spent.
- **Disciplines, hidden in blocks.** image-squeeze's developer "takes the oldest idea" and resumes a
  half-built one first, but that ordering lives in `bin/lab.py claim` behind a file lock; the model
  shows only `started driven-by +stock.ideas`. the-job's morning brief ranks the goals that are off by
  the size of their error, inside `bin/rhythm.py`. Both are queue disciplines written as code where
  neither SD nor control can see them: the smell the owner named.
- **The loop to tune it.** The modelling subsystem (§12e) can propose a parameter change, the judge
  replays it, and loop dominance and sensitivity (§12c) say which loop matters now.

What is missing is the allocation as a part of the model: the queue's discipline, the per-item
estimate it reads, the attention capacities as stocks, and the feedback that retunes the weights.

## 4. Candidate designs

Common to all: the thing being allocated is a **flow of service** out of a **queue stock**, through a
**valve** whose opening is shared among classes or items. The designs differ in which resource they
model and how dynamic the shares are.

### A. The ordered queue: a dispatch valve over classes

A queue of items is split into class stocks (one per kind of waiting work: owner-asked, stuck,
failing, routine, upstream), each counted by an item sensor with `where:`. One worker pool's
service is the shared capacity; its outflows from the class stocks are set by an **allocation
valve** that splits the capacity by priority and by an index, allocate-by-priority in SD terms, the
cμ rule in queueing terms. The index is a parametric expression over fields of the item and signals
of the model (its age, the error of the goal its item serves, its class weight). A worker pulls the
head; the ordering is no longer inside `lab.py`.

- Ladder: the sort is the **rule** rung. The per-item part of the index (cost of delay, a class for
  something novel) is written onto the item as a field by a classifier, a **narrow AI** block, so
  judgment enters as a measured, recorded field rather than inside the valve.
- SD view: class stocks, their outflows, the capacity as an auxiliary, the valve's share per class.
  Control view: a dispatcher block between the queue and the pool, its weights as parameters.
- Measure: waiting time per class against its cost of delay; the weighted holding cost
  (Σ weight × items × time); the age of the oldest item per class.

### B. Gain-scheduled weights with a starvation floor

A's weights become signals: a `lookup` on the operating point (the owner-waiting stock, the error of
a critical goal) raises one class's weight as its pressure rises. A supervisory loop sits above: a
goal on weighted lateness per class, and a slow `proportional` block that moves the weights to hold
it. To keep the fire-fighting loop from tipping, upstream work keeps a reserved share (a floor on
its outflow), and the reinforcing loop between "urgent work served" and "upstream work starved" is
drawn, so ergostat's loop analysis names it and loop dominance says when it takes over.

- Ladder: **program** (lookup and proportional are built in).
- Measure: as A, plus the share of capacity spent on urgent classes over time, and whether the floor
  ever binds.

### C. The Coordinator's own looking: event-triggered inspection

Make "look at the running thing" a flow. In-flight work holds a lease with a renewal; a missed
renewal, a claim contradicted, a run finished, or a residual (the model's projection against what
its sensor read, §12b) past its threshold each add an item to a stock of **unexamined surprises**.
An inspector (an **AI agent** block, or a program for the common cases) drains it, through the same
dispatch valve as A with a different index (surprise size times the criticality of the goal
touched). Time-triggered heartbeats remain only where no event can come. This is the restless-bandit
choice made by structure: what changes unwatched sends its own event, and what is quiet is not
looked at.

- Measure: time from an event that needed a look to the look, per class; looks that found nothing
  (wasted samples); surprises that aged past their lease without a look.

### D. The owner as a budgeted server: alarm management

A stock **waiting on the owner**, fed by the classes that need a person (decisions, held verdicts,
unrouted messages, a high-index surprise), drained by the owner's answers. Its inflow is split:
above a threshold, an **interrupt** (notification now); below it, a **delayed stream** that batches
items into the next digest, ordered by index (the digest the first plan proposed, now the batched
outflow of a valve, not a separate idea; it meets 2.15's delayed streams and 2.11's dashboards).
The threshold is a parameter with a budget beside it: interrupts per day, as ISA-18.2 budgets alarms
per hour. Shelving and flood suppression are items the owner can set: a class shelved until a time,
consequential items folded into the one that caused them.

- Ladder: **rule** for the split, **person** for the server.
- Measure: interrupts per day against the budget; the share acted on (an interrupt dismissed is a
  nuisance alarm); things the owner asked about that ergostat already knew (attention under-given);
  age of the oldest item waiting on the owner.

### The modelling subsystem's role, for all four

The discipline's form, classes, weights, floors, thresholds and budgets are parameters and structure
of the model, so only the modelling subsystem changes them (§12e). It needs a neighbourhood, not the
whole model: the queue, its classes, the goals its items serve, and the capacities that drain it,
with the per-class measures above as evidence and the queue's own replay to project a reweighting
before it is accepted. On the rate of change: the valve reads its weights at each pull, so a change
reaches only the next pull, and claimed work keeps its item (bumpless transfer); nothing needs
pausing. Timescales stay separate: the gain schedule moves weights within a declared table at the
sensor's rate, the supervisory loop moves them slowly, and the modelling subsystem changes the
table, the classes or the index at its own cadence. The modelling subsystem also has its own
attention problem (which neighbourhood to work on next), and it is A again: its candidate changes are
a queue, ordered by expected fit gain against cost.

## 5. Recommendation

Build **A as a reusable, parametric part, used three times**: by a worker pool (A itself), by the
Coordinator's inspector (C) and by the owner's queue (D), with B's schedule as the way its weights
become dynamic. One structure, three instances, is the case the owner gave for library parts: many
loops with the same shape, differing only in their classes, index and capacity.

Reasons: it pulls the two hidden disciplines (`lab.py claim`, `rhythm.py brief`) into the model where
both views can draw and analyse them; it puts per-item judgment where it can be measured (a field a
narrow AI writes) instead of inside a valve; it reuses what exists (item sensors, lookup, proportional,
findings, messages, the judge) and needs one new capability, an ordered pull from an item queue,
which is the queue's discipline and not a new item kind; and it answers the old plan's measure (things
the owner asked that were already known) with the structure that should reduce it.

```yaml
# Sketch only: the part, and one of its uses.
parts:
  priority-queue:                    # a library part: one queue, its classes, its valve
    params: [kind, classes, capacity, index]
    stocks:
      waiting[class]:                # one stock per class, counted from items
        sensor: {items: "{kind}", state: waiting, where: {class: "{class}"}}
    flows:
      served[class]:
        from: waiting[class]
        share: allocate(capacity, by: weight[class], floor: floor[class])
    auxiliaries:
      weight[class]: {table: "{classes}.weight"}   # scheduled below
    order: "{index}"                 # how the head of each class is chosen

uses:
  owner-queue:
    part: priority-queue
    kind: needs-owner
    capacity: owner.answers          # the owner's answer rate, measured
    classes:
      decision:   {weight: 3, interrupt: true}
      held-work:  {weight: 2}
      surprise:   {weight: lookup(goal.critical.error)}
      routine:    {weight: 1, floor: 0.1, batch: digest}
    index: "cost_of_delay / est_minutes"   # cost_of_delay written by a classifier
goals:
  owner-not-flooded: {flow: owner-queue.interrupts, hold: "<= 4/day"}
  owner-not-surprised: {flow: owner.asked-already-known, hold: "<= 1/week"}
```

Of the old plan's Build for 2.9:

- **Keep** the digest, but as the batched outflow of D's valve, ordered by the same index, not as a
  standalone block; keep the stock *needs the owner* and its goal on the age of the oldest.
- **Keep** the measure "the owner asked about something already known", and add interrupts against a
  budget, interrupts dismissed, and the per-class waiting times.
- **Change** "notifications only for items marked as needing the owner": the mark becomes a class and
  a threshold on an index, set by the model and tuned by the modelling subsystem, not a flag.
- **Retract** the `digest` kind on the Items page as the answer; a digest is an output of the queue,
  shown through the existing system box and Items views.
- From last night's work: the findings (`contradicted-claim`, unrouted messages) and the intent
  judge's held verdicts become **classes feeding D**, rather than a flat "needs attention" list;
  messages (§12h) already give C its event triggers; recipes' `state` part (§12j) should carry the
  head of each queue, which is what a fresh Coordinator-like session needs to know first.

Parity is reached when, on the transcript's history replayed through F3, the order in which this
structure would have surfaced things matches (or beats, by the owner's later corrections) the order
the session looked at them, with the owner interrupted no more often than the session interrupted
them.

## 6. Open questions for the owner

1. Should library parts with indexed stocks (one stock per class) come before this gap, or should the
   first version write the classes out by hand in image-squeeze and the-job?
2. Is a per-item cost of delay written by a narrow AI acceptable as a measured field, or should the
   index use only fields that programs set?
3. What is your interruption budget per day, and should it be a goal you own or a parameter the
   modelling subsystem may tune?
4. Should the Coordinator's own looking (design C) be modelled at all, or is it enough that workers
   and the owner have ordered queues?
5. Should the fire-fighting floor (a reserved share for upstream work) be a default of the part, or
   only added where loop analysis shows the reinforcing loop?
