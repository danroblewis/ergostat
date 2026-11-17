# 2.14 Coordinating concurrent work

Status: exploration, 2026-11-17. One of sixteen gap studies behind
[harness-parity-plan.md](../harness-parity-plan.md); the function is number 14 in
[harness-as-control-system.md](../harness-as-control-system.md) §5.

## 1. What the harness actually does here

The long session ran several pieces of work at once (last night: changesets, storage, decisions, messages,
recipes, the intent judge, claims, the parity bench). As Coordinator it did six things:

- **Fan-out.** It decided which work could proceed in parallel and how much at once. That judgement came from
  having the whole plan and the repository layout in its context: it knew storage and decisions touch
  different modules, and that recipes and intent both touch the session code.
- **Isolation.** A worktree and a branch per subagent, so workers never saw each other's half-done edits.
- **Keeping workers apart.** It avoided giving two agents the same files. This is a prediction of each
  change's footprint, made from the request plus a reading of the code, with no locks declared anywhere.
- **Serialising the shared resource.** Merges onto main went one at a time, with suites run and exit codes
  checked between them.
- **Telling workers what moved.** After a merge, the agents still working were told to rebase, or told what
  had changed underneath them.
- **Recovering stalls.** The progress log records that the recipes and intent agents stalled twice each,
  mid-step and uncommitted. The Coordinator noticed, took the work over, ran the suites and resolved the
  conflicts by hand.

All of this adds up to throughput from parallel actuators without collisions, duplicated work or a broken
main, plus recovery when an actuator dies quietly. It works because one context window holds every piece of
work in flight, along with its scope and the code. Training contributes knowledge of git workflows and of how
merge conflicts arise. The tools (`git worktree`, subagents with isolation) supply the mechanism. The
judgement part is the footprint prediction and the semantic conflict resolution. Everything else is
bookkeeping, and the harness does that bookkeeping unreliably: it notices a stalled agent only when it next
looks.

## 2. Classical parallels

- **Queueing theory and WIP limits.** Little's law (WIP = throughput × lead time), the M/M/c worker pool,
  and Kanban/CONWIP limits on work in progress. The pool's size is a setting a controller can hold, like a
  replica count (the Production example's HPA).
- **Leases** (Gray and Cheriton, 1989): a grant with a time to live, kept alive by renewals and lost on
  silence. Control engineering's version is the **watchdog timer**. Neither one is a lock: a dead holder
  frees the resource by itself.
- **Dead-letter queues** from messaging: after k failed deliveries, an entity is parked for diagnosis
  instead of being retried forever (gap 2.6).
- **Discrete-event supervisory control** (Ramadge and Wonham) and **Petri nets**. Mutual exclusion is the
  textbook supervisor specification. In Petri-net terms a shared resource is a place holding tokens, which
  is an SD stock of integer units. A supervisor *disables events* to keep the plant legal.
- **Interlocks** from process control: an actuator may not act while another holds the same equipment.
  Main being broken is an interlock on the merge valve.
- **Optimistic versus pessimistic concurrency control.** A merge conflict is an optimistic transaction's
  abort, and a rebase is its retry. Locking parts is the pessimistic choice.
- **Single-server bottlenecks.** The merge queue is the drum in drum-buffer-rope (Theory of Constraints).
  Batching (bors-style) trades latency for throughput.
- **The rework cycle** (Cooper; Lyneis and Ford) in system dynamics, which together with Brooks's law
  explains why concurrency needs controlling. More workers in flight means more conflicts, conflicts make
  rework, and rework adds work in flight: a **reinforcing loop**. The WIP limit is the balancing loop
  against it.
- **Control allocation and decoupling** in MIMO control. Two actuators acting on overlapping parts are
  coupled loops. Partitioning work by footprint decouples them.

**Where the classical tools fall short of the harness.** They all assume the resources and dependencies are
*declared*. A job-shop scheduler is told which machine each job needs, and a lock manager is told which rows
a transaction touches. The harness *infers* the footprint from a sentence and the code, and when that
prediction is wrong it resolves the conflict semantically. In control terms, the footprint is an unmeasured
state that needs an **observer** (an estimator). The conflict resolution is a repair actuator high on the
ladder. The rest (queues, leases, the merge server, notification) is classical and belongs on the rule and
program rungs.

## 3. What ergostat already has

- **Concurrency between blocks.** The engine runs different blocks in parallel threads (`spec/engine.py`
  `start`/`_run`). An agent's `at-once` is a counting semaphore across its blocks (SPEC §10; `self.slots`).
  This gives pipeline parallelism: a researcher, a developer and a judge all working at once.
- **No parallelism within a block.** "A machine block never runs twice at once" (SPEC §9.1), and a command
  that arrives while a block runs is *held, not queued* (anti-windup). For a continuous command that is
  right, because the latest value wins. For discrete work it is wrong, because ten ready items are not one
  command of ten. So no worker pool exists.
- **No event triggers in the YAML engine.** YAML blocks run when commanded, on a schedule, or on fresh
  readings. The older TOML runner (`ergostat/runner.py` `_follow`) had `on:` event patterns with a queue per
  agent, served one at a time. The idea existed and was lost in the move to YAML.
- **Queues as stocks of items.** A stock counts items in a state and a flow counts items entering or leaving
  one (SPEC §5a, §6). image-squeeze's lab is an aging chain built this way (ideas → building →
  experiments → improvements).
- **Coordination hidden inside a script.** image-squeeze's `bin/lab.py` already does most of the harness's
  bookkeeping, but out of sight of the model:
  - a worktree and branch per hypothesis;
  - an `flock` around every state change;
  - a single candidate slot ("one experiment at a time");
  - recovery of a `building` hypothesis left by a stopped session, which is a lease without a TTL that
    expires only when someone next asks for work;
  - a merge under the lock.

  Its `session` kind even has a `lost` state. This is the smell the brief names: a queue, a lease, a
  workspace pool and a merge server inside one block.
- **Telling running work what changed.** SPEC §12h (built last night) delivers a message into a live
  `claude -p` session mid-turn, or into a block's next run. The progress log's "next" for 2.14 was exactly
  this: a message from ergostat itself saying main moved.
- **Free renewals.** A live session's transcript is read every two seconds and recorded as `claude.*`
  events about its item (SPEC §5a). A worker that is alive writes events about its item, so the evidence a
  lease renewal needs is already in the record.
- **Arbitration is open.** SPEC §15 question 3 (two controllers commanding one block) is the same family of
  question, still undecided.

## 4. Candidate designs

### A. Item-driven worker pools with leases kept by a watchdog loop

Work items wait in a queue state, a dispatcher leases each one to a run of a worker block, and a watchdog
loop puts silent leases back.

- **The queue (one per item kind a block works on).** The stock of items in the kind's ready state. This
  answers "every event with agent bindings gets a queue": the queue is not a new object, because the items
  in a state already are one. What the engine must add is *item-driven dispatch*. An item entering the
  ready state is an event that starts a run, one run per item, several runs of the same block at once up to
  a pool size. Signals keep their anti-windup rule (latest wins) and items are queued. That is the
  continuous versus discrete-event distinction, made explicit.
- **The lease.** An item is moved to `leased` by a dispatcher event carrying the holder and the run. Renewal
  is any event about the item from its holder, such as transcript lines, `claim` lines or progress events,
  so renewal is observed and never declared. Expiry is an ordinary loop: a sensor counts leased items with no
  event for longer than the TTL, a goal holds that at zero, and a rule-rung block moves stale items back to
  ready and adds one to their `expiries`. Over k expiries, it moves them to `dead` (the dead-letter stock,
  which gap 2.6's diagnosis reviews). A run that outlives its lease is told so, and its later output about
  that item is refused. That is the classical fencing token: the lease's sequence number travels with the
  run.
- **The pool size.** A setting, held by a goal on in-flight work (a WIP limit). It can be fixed, or set by a
  proportional controller on queue length and wait, which is the HPA loop again.
- **The workspace.** Acquired with the lease and released with it, so a worktree lives exactly as long as
  its lease. Orphaned worktrees are a stock, counted and held at zero by the same watchdog. Git specifics
  are a library part; the core knows only "acquire on lease, release on release or expiry".
- **Ladder.** The dispatcher, watchdog and expiry are rule and program rungs. The workers are whatever they
  are (AI agents, usually).
- **The SD view** shows an aging chain: ready → leased → submitted → done. It has an expiry backflow (a
  balancing loop that recovers stalls) and the dead-letter sink.
- **The control view** shows the queue as the plant, the dispatcher as the valve, the WIP goal as a
  saturation or interlock on it, and the watchdog as an inner supervisory loop.

### B. Concurrent paths in the model, with the scheduler made visible

This keeps today's pipeline parallelism and draws it. Each agent's `at-once` becomes a stock of slots (a
Petri-net place: capacity, in use), visible in both diagrams, so a bottleneck shows as a full stock rather
than as a semaphore in a thread. Independent loops are concurrent paths, and the engine is the scheduler.
The design is cheap and honest, but it never gives data parallelism (many items of one kind at once), which
is what fan-out needs. Alone it does not reach parity.

### C. Footprint as an estimated co-flow: optimistic first, interlock on evidence

Every leased item carries a co-flow attribute, its predicted footprint (paths or modules). A narrow-AI or AI
block, the observer, predicts it from the item's words and the code. That block is the one place the
harness's judgement is needed.

There are two policies, and they are one parametric library part:

- **Optimistic.** Lease freely, measure conflicts at merge, and let a controller lower the pool size as the
  conflict rate rises. This is gain scheduling on a measured disturbance.
- **Pessimistic.** The dispatcher's valve is interlocked: it skips an item whose footprint overlaps one in
  flight and takes the next.

A sensor compares the predicted footprint to the actual diff, and that error is the observer's quality, fed
to the modeling subsystem. After each merge, the merged change's actual footprint is sent to in-flight items
whose predicted footprint overlaps it, as an ergostat message (§12h). This is feedforward: workers learn what
moved before they collide, and only the workers it concerns are told.

### D. The merge queue as a maintained library part

This is an item per merge (`merge/<branch>`): queued → testing → merged, or bounced. A single-server program
block (pool of one) rebases, runs the declared suites with exit codes checked (claims, §12g), and merges.
Bounced work goes back to its source item's ready state as rework, closing the rework cycle in the model.
`main-broken` is a stock with a goal at zero and an interlock that shuts the merge valve while it is off: a
supervisory gate that switches a loop off. Batch size is a parameter. The part is not core. It is offered as
a starter set (`library/merge-queue`, `library/git-workspace`) built only from A's core and existing parts.

### Sketch (A with D, as wiring)

```yaml
items:
  change:
    id: change/*
    states: [ready, leased, submitted, merged, dead]
    on: {ergostat.lease.granted: leased, ergostat.lease.expired: ready,
         ergostat.lease.dead: dead, change.submitted: submitted, merge.merged: merged}
    fold: {expiries: sum}

stocks:
  ready:     {sensor: {items: change, state: ready}}             # the queue
  in-flight: {sensor: {items: change, state: leased}}
  stale:     {sensor: {items: change, state: leased, silent-for: parameter.lease-ttl}}
  dead-letter: {sensor: {items: change, state: dead}}            # reviewed by diagnosis (2.6)

flows:
  leased:  {from: ready, to: in-flight}
  expired: {from: in-flight, to: ready}                           # stalls recovered: the balancing loop
  died:    {from: in-flight, to: dead-letter}
  rework:  {from: in-flight, to: ready}                           # bounced by the merge queue

parameters:
  lease-ttl: 10m
  pool: 3
  retries: 2

goals:
  wip-limit:  {stock: in-flight, hold: "<= parameter.pool"}
  none-stale: {stock: stale, hold: "<= 0"}

blocks:
  developer:
    type: ai
    per-item: stock.ready        # one run per item, leased by ergostat, up to the WIP goal
    goal: wip-limit
    out: {submitted: flow.submitted}
  watchdog:
    type: program                # rule rung: expire, or dead-letter after `retries`
    goal: none-stale
    run: $ERGOSTAT_CMD lease expire --kind change --retries 2
    out: {expired: flow.expired, died: flow.died}

uses:
  - library/merge-queue: {from: change, state: submitted, tests: "uv run python -m pytest", batch: 1}
  - library/git-workspace: {for: change}   # a worktree per lease, released with it
```

`silent-for`, `per-item` and `uses` are where the core would change. Every other line uses parts that exist
today.

## 5. The modeling subsystem's role, and rate of change

Pool size, lease TTL, retries, batch size, the optimistic/pessimistic switch and the controller's gain on the
conflict rate are all parameters and setpoints. Only the modeling subsystem changes them, judged by replay
(§12e). Its focus is a neighbourhood of the graph: one pool's aging chain, its merge queue and the conflict
and expiry sensors. Little's law fitted against the record gives it a first estimate.

Leases make the rate-of-change question easy, and that is a strong reason to prefer them over locks:

- **TTL changes.** A lease keeps the terms it was granted under until its next renewal, so a new TTL needs no
  pause.
- **Pool reductions.** A smaller pool drains: no new leases while in-flight work is over the limit, and
  nothing running is killed.
- **Interlock tightening.** Tightening applies to the next lease only.

The Coordinator likewise never changes a running subagent's terms; it changes what the next one gets. The
footprint observer's prompt and model are also modelled parts, which the modeling subsystem improves from the
predicted-versus-actual error.

**How parity would be measured.** Seed a repository with a backlog like last night's: about eight items,
some overlapping, and two planted stalls (a worker killed mid-step, uncommitted). Compare the Coordinator's
log with ergostat's run on these measures:

- duplicate leases (must be zero);
- stalls recovered automatically, and in how long after the TTL (last night: by hand, after an unknown
  delay);
- merges that broke main (must be zero);
- conflicts per merge;
- orphaned worktrees;
- idle-worker share;
- lead time per item.

Parity means equal or better on each, with no human merging.

## 6. Recommendation

Build **A** in the core, draw **B**'s slots as stocks, and ship **C** and **D** as maintained library parts.
The reasons:

- A's one essential core change is item-driven dispatch: several runs of one block, each bound to one item.
  Without it ergostat has no fan-out at all. With it, leases, retries, dead letters and WIP limits are
  ordinary stocks, flows, goals and a rule-rung block, analysable in both views, rather than a script's
  `flock`.
- Renewal from the item's own events costs nothing, because transcripts already stream in as events.
- The judgement the harness brought (footprint) is isolated in one observer block, measured by its
  prediction error, so it can sit anywhere on the ladder and climb down it as it is learned.
- Merging is git-specific and policy-heavy. It is a library part made from core pieces, as the owner
  suggests.
- Start optimistic, with conflicts measured and the pool scheduled on them, and turn the interlock on only
  when the record shows it pays. That is control's habit of measuring the disturbance before designing
  against it.

**The old plan's Build, item by item:**

- **Worktree per item:** keep, re-scoped as the lease's workspace in a library part.
- **Lock on the parts an item touches:** retract. Replace it with leases (TTL plus renewal) on the item, and
  an optional footprint interlock that is predicted and measured, never declared.
- **Merge block, one at a time, after its judges:** keep, as the `merge-queue` library part, with an item per
  merge, the main-broken interlock and bounced work as rework.
- **Every session told what moved:** keep, through §12h messages, but routed by footprint overlap
  (feedforward) rather than broadcast.
- **Modelled stocks:** keep, and add the queue, in-flight, stale and dead-letter stocks and the expiry
  backflow.
- **Kind:** change it. The resource is core dispatch plus library parts; the old "part locks" resource goes.

**What was built last night:**

- §12h live delivery is the notification channel this design needs.
- §12g claims are the merge queue's test gate.
- image-squeeze's `lab.py` claim, resume and `flock` should later be rewritten on A, as the reference
  example. It is the clearest current case of hidden coordination.

**Depends on:**

- 2.6 dead letters and diagnosis;
- 2.9 and 2.15 queue order (the dispatcher's ordering is the attention valve);
- 2.4 messages;
- 2.2 a parent item's done computed from its fanned-out children (fan-in);
- 2.1 rate of change.

## 7. Open questions for the owner

1. Should a block's several runs at once be bounded by a goal on in-flight work (the WIP limit as a drawn
   loop), or by a plain count on the block?
2. Is any event about an item from its holder a good enough renewal, or must a worker renew explicitly?
3. When a lease expires while its run is still going, should ergostat kill the run, or only refuse its later
   output about that item?
4. Should conflicts be optimistic by default (measure, then throttle), with the footprint interlock opt-in?
5. Should the merge queue and git workspace parts live in the ergostat repository as maintained library
   parts, or in a separate starter set?
6. Is fan-out (one item split into children) a planner block's job that makes items, with the parent's done
   computed from its children, or should the model's structure express it?
