# Modelling someone's work: a guide for AI agents

You are an AI agent (Claude Code or similar) setting up ergostat for a person: turning the work they
describe into a model that ergostat runs. This page is how to do that well. Read it before writing any
YAML. The full format is [SPEC.md](SPEC.md); improving a model once it runs is [MODELLING.md](MODELLING.md).

The most common failure is not a broken model: it is a model that **runs and does the work, but is
the wrong shape**, so its diagrams show disconnected pieces and the analysis tools can say nothing.
Everything below is about getting the shape right the first time, and then checking it.

## 1. What you are building

ergostat models work as a **system**, read two ways:

- **System Dynamics** (the Dynamics view): work is material in **stocks** (things waiting in some
  state), moved by **flows** (things changing state per hour). Stocks are joined by flows into
  chains; work arrives from outside at one end and leaves at the other.
- **Control engineering** (the Blocks view): each **goal** holds a measured quantity at a setpoint;
  a **sensor** measures it, a **block** (program, AI agent, person) acts when it is off, and its
  action moves a flow. That is a feedback loop.

A good model of a workflow is **one connected chain per kind of work**, with the steps' loops all
acting on that chain. If your drawing has many separate stocks each draining to a cloud, or many
loops that share nothing, the model is the wrong shape (section 4).

Items are how individual pieces of work are tracked: each ticket, request or pull request is an
**item**, a fold of the events about one id. An item kind lists its **states** in order. The stocks
count items in each state; the flows count items moving between states. That is the bridge between
"a ticket moves through my process" and the diagrams.

## 2. The method: from a described workflow to a model

Work through these steps in order. Ask the person only what you cannot infer.

1. **Name the kind of work and its states, in order.** "A change request is *new*, then
   *researching*, then *awaiting-approval*, then *rolling-out*, then *done*." Add the side exits
   (*rejected*, *abandoned*). This list is the backbone of everything else.
2. **One stock per state where work waits or is worked on** (not the final states). Each is measured
   by counting items in that state: `sensor: {items: KIND, state: STATE}`.
3. **One flow per move between states, chained from stock to stock.** A move from *researching* to
   *awaiting-approval* is a flow `from: researching-stock`, `to: awaiting-stock`, measured as items
   entering the later state. Arrivals come **in** from outside to the first stock; completions and
   side exits go **out** to outside from the last stock that holds them. Never model a move between
   two of your own states as "leaving to outside": that is what disconnects the diagram.
4. **A collector that finds the work**: a program block (or sensor) that polls the outside system
   (Jira, GitHub, a queue) and prints one event per new or changed item, e.g.
   `{"event": "request.new", "item": "request/123", "data": {"title": "...", "url": "..."}}`. The
   kind's `on:` maps event types to states. This is the **sensor** of the whole workflow: without it
   nothing arrives.

   **When the work is related** (a ticket blocked by another, tickets under an epic, a duplicate), declare the
   relations on the kind and have the collector record them as fields (SPEC §5a, *Relations*):

   ```yaml
   items:
     ticket:
       id: ticket/*
       relations:
         blocked_by: ticket          # precedence: ready once each one it names is done
         parent: epic                # cross-kind: the epic it is part of
     epic:
       id: epic/*
   ```

   An issue tracker's links map onto them: Jira's "is blocked by" links (inward, of the type Blocks) are
   `blocked_by`, "blocks" is the inverse ergostat derives (never record both), the epic link or parent is
   `parent`, "duplicates" is `duplicates`. A collector that reads every link of an issue each time it polls says the
   whole set, so a link taken away in the tracker goes here too:
   `{"event": "ticket.seen", "item": "ticket/PROJ-12", "data": {"blocked_by": {"set": ["ticket/PROJ-9"]}, "parent":
   {"set": ["epic/PROJ-1"]}}}`. One that sees changes says them: `{"blocked_by": {"add": "ticket/PROJ-9"}}`,
   `{"remove": ...}`. Use the same ids the items have (`ticket/PROJ-9`, not `PROJ-9`), and record the related item
   too, or it shows as "not recorded" and counts as unfinished. Then the step that starts the work can take only
   what is unblocked, the critical first: `takes: {kind: ticket, at: todo, unblocked: true}`. Look at the Items
   page's **Graph** (what waits on what, the critical path) and **Timeline** (what happened, and what is projected)
   to check the links came through (the Timeline's projection and the list's **done by** are the completion
   estimates: see "When will it be done", below); `examples/roadmap/` is a small model built this way. A parent that moves on
   when its children do (an epic shipped once every ticket is done) is a rule on its kind, never a block:
   `join: {children: parent, all: done, to: shipped}` (`any:` for the first child to start).
5. **One block per step that does the work**, taking items in its state:
   `takes: {kind: KIND, at: STATE, to: [NEXT]}`, with `pool:` (how many at once) and, for AI work, a
   prompt. A run leases its item, does the step, and prints the event that moves the item on.
   ergostat retries a run that fails or goes silent, and parks an item that keeps failing as a dead
   letter. A program may **print events as it goes**: each line is taken when it is printed, not
   when the run ends, so a long run's findings land at once (flush each line: `print(...,
   flush=True)`), and every event it prints renews the lease it holds, so a run that reports its
   progress is never taken for silent. A run silent past its lease's TTL is **killed** (SIGTERM, then
   SIGKILL), its item retried: a long, quiet step must print progress or `$ERGOSTAT_CMD lease --renew`, or
   be given a longer `lease: {ttl: ...}`. If it is stopped part way, what it printed stays. A step a person must do is a `type: person` block with `ask:`; it is asked while its goal
   is off (only `program` and `ai` blocks take items one at a time).
6. **Goals on what matters**: how long the oldest item has waited in a state
   (`measure: oldest` on a stock's sensor, `hold: "<= 4"` hours), how many are waiting, throughput.
   A goal is what makes a block's work a feedback loop; give each step's queue one. A limit on each item
   or on each group of items ("no ticket in review over 48 hours", "each epic's open tickets <= 10") is
   `per: item` or `per: parent` on the goal over the counted stock (SPEC §8): it goes off naming the items
   or groups that break it, where a plain goal on the oldest would name none.
7. **Gated actions for anything that acts outward** (moving a Jira ticket, opening a PR, posting a
   message): declare them under `actions:` with a gate (`approve` to start, `auto` once trusted), and
   have the step ask for them (`$ERGOSTAT_CMD act NAME --arg k=v` from a script, or as a tool from an
   AI session). See SPEC section 12k.
8. **Check and look** (section 3), and fix everything it finds before showing the person.
9. **Give it the modelling loop: `uses: {modelling: {use: modelling}}`.** Every model should have it (`check`
   notes one without it, `no-modelling-loop`). One line makes the model improve as a loop of its own (SPEC
   §12e): its fit to the record (`model-error`) is a stock held by a goal (`model-fits`), an improver proposes
   changes with their evidence while it is off, and ergostat's judge tests each on the record after it; the
   owner accepts what passes (or `accept: {parameter: auto}` writes passed values at once). It runs free on a
   stand-in improver until given a prompt and `run: ""` (a Claude session) or a program; its options are in
   `docs/ADDING.md` (modelling). With `ai: true` it also reviews the structure on its own, a system at a time (the
   redesigner, `when: auto`), and what it proposes waits for the owner: keep the systems small (40 parts or fewer)
   so each can be reviewed whole. Do not hand-write these parts.
10. **Last, reconcile the three views.** Run it (stand-ins are enough), then `ergostat check` again: its
   **Coherence** section (or the MCP `coherence` tool) holds what really happened against the model, and the model
   against its blocks. Fix the model, or the blocks, until every kind agrees (section 3, *Reconcile the three
   views*).

### A small example, connected

```yaml
items:
  request:
    id: request/*
    states: [new, researching, awaiting-approval, rolling-out, done, rejected]
    on:
      request.new: new
      request.researching: researching
      request.researched: awaiting-approval
      request.approved: rolling-out
      request.rejected: rejected
      request.done: done
    show: [title, url]

stocks:
  requests-new:        {unit: requests, sensor: {items: request, state: new, every: 1m}}
  requests-researching: {unit: requests, sensor: {items: request, state: researching, every: 1m}}
  requests-awaiting:   {unit: requests, sensor: {items: request, state: awaiting-approval, every: 1m}}
  requests-rolling-out: {unit: requests, sensor: {items: request, state: rolling-out, every: 1m}}

auxiliaries:                     # no memory of its own: an age, a ratio, a score
  oldest-awaiting:
    unit: hours
    driven-by: [+stock.requests-awaiting]
    sensor: {items: request, state: awaiting-approval, measure: oldest, every: 1m}

flows:
  arriving:     {to: requests-new, sensor: {items: request, entering: new}}
  started:      {from: requests-new, to: requests-researching, sensor: {items: request, entering: researching}}
  researched:   {from: requests-researching, to: requests-awaiting, sensor: {items: request, entering: awaiting-approval}}
  approved:     {from: requests-awaiting, to: requests-rolling-out, sensor: {items: request, entering: rolling-out}}
  rejected:     {from: requests-awaiting, sensor: {items: request, entering: rejected}}
  completed:    {from: requests-rolling-out, sensor: {items: request, entering: done}}

goals:
  approvals-prompt: {auxiliary: oldest-awaiting, hold: "<= 4"}
  research-kept-up: {stock: requests-new, hold: "<= 3"}

blocks:
  find-requests:                 # the collector: the workflow's sensor
    type: program
    run: scripts/fetch-requests  # prints one event line per new or changed request
    every: 5m
    out: flow.arriving           # what its work moves: this is what draws it into the loop
  researcher:
    type: ai
    takes: {kind: request, at: new, to: [awaiting-approval]}
    pool: 2
    goal: research-kept-up
    prompt: prompts/research.md
    out: flow.started            # taking a new request drains requests-new: the loop on research-kept-up
  approver:
    type: person                 # the person decides; ergostat asks while the goal is off
    ask: "Approve or reject the requests awaiting approval (oldest first)"
    goal: approvals-prompt       # they record each with an event: request.approved / request.rejected
    out: flow.approved
  roll-out:
    type: program
    takes: {kind: request, at: rolling-out, to: [done]}
    run: scripts/roll-out
    out: flow.completed
```

`ergostat check` on this example says every goal is closed by a loop, and notes one thing that is
expected: the collector `find-requests` "moves flow.arriving on its own schedule; nothing commands it".
That is right: arrivals are the outside world's doing, so the collector is an open loop on purpose.

This draws as one chain in the Dynamics view (new → researching → awaiting → rolling-out, in from
outside, out to done and rejected), and in the Blocks view as loops that act on that chain. A full,
real workflow built this way is `examples/ticket-factory/` (Jira, GitHub, CI, review), with its README.

Keep the person's scripts and prompts in a private folder outside any repository if they ask;
`run:` and `prompt:` paths may point anywhere.

## 3. The feedback loop: check, look, fix

You are not done when the YAML loads. Do this every time you change the model:

(Edit freely while `ergostat run` runs: it takes your edits once the files have been still for about 1.5 s, and
while they have errors it keeps running the last good model, saying so, with each error's file and line, in its log,
`ergostat status` and the page's header. Nothing half written is ever taken. Meanwhile the commands that only read,
`ergostat status`, `item`, `event`, `fit`, `residual`, the parts and the like, still answer from the last model the
engine took, with one line on stderr naming the first error; anything that acts (`event --add`, `block --now`,
`accept`, `run`, ...) refuses until the YAML is fixed, so fix it before you act.)

1. **`ergostat check`** (or the MCP `check` tool). It reports errors with file and line, then what
   the model is missing. Treat every finding as something to fix or to explain to the person.
2. **`ergostat explain`** (or MCP `explain`): read the model back in sentences. If the sentences do
   not describe the person's process, the model is wrong.
3. **Look at both diagrams.** Run `ergostat run`, open the page it prints, and look at the Diagram
   page in both views (Dynamics and Blocks), or take screenshots and read them. Then go through the
   checklist below. An agent that looked at its diagrams fixed a disconnected model on its own; one
   that did not, did not notice.
4. **Run it briefly with stand-ins** (scripts that print plausible events) before connecting real
   systems, and watch items move through the chain on the Items page.
5. **Check that the work moves as modelled, in the Process view.** The Diagram page's Process view
   (SPEC §5b) is the process map the record draws: for each kind, the states its items really
   entered and the moves between them, how often, and the median time each took. Hold it against
   the chain you modelled (below).
6. **Reconcile the three views** (the last step): `ergostat check` once the model has run, or the MCP
   `coherence` tool, and fix until every kind agrees (below).

### The Process view: does the workflow behave as modelled?

The Dynamics view is the workflow you declared; the Process view is the one that happened. Open it
(`/diagram?view=process`, the person's system chosen) once items have moved, and look for:

- [ ] **Every move you modelled as a flow is a line**, and every line is a move you modelled. A line
      between two states with no flow between their stocks is work leaving or arriving where the model
      says it cannot: a missing flow, or an `on:` mapping that is wrong.
- [ ] **No state is left out**: a state no item ever enters in a long window is dead, or its event is
      never printed (look at the collector).
- [ ] **Items end where the work ends.** The end node should follow your final states; an item that
      ends in a waiting state means a step that never reports.
- [ ] **Rework is what the person expects.** Lines marked ↺ run back to an earlier state: a review
      sending work back is real; a lease handing items back over and over is a failing step (its median
      time says how long each try took).
- [ ] **Fan-out and join** (dashed lines between kinds): work that starts other work (a ticket
      spawning research items) shows a line from the first kind into the second, and back where the
      second's results finish the first. None means the runs do not record `causedby`. A sweep on
      `every:` or `cron:` that opens items draws its fan-out from its block's node in the **schedules** frame.
- [ ] Switch **Events** on to see what happens between the moves (comments, retries, a session's
      steps), and **Times** to see where the time goes. Click a line to list the items that took it.

The first four are what `ergostat check`'s Coherence section checks for you, with the fix for each
(below); the map is where you see why.

### Reconcile the three views

The Process view (what the items did), the Dynamics view (the chain you modelled) and the Blocks view
(what moves the work) are one system drawn three ways, and they must agree. `ergostat check` holds
them against each other over the record (SPEC §12l; the MCP tool `coherence`, the Check page's
Coherence section): per kind a score, `ticket: 41 of 44 agree (93%)`, or how much more record it
needs; and each mismatch with its file and line, its fix, the pair of views that disagrees, and the
`check` finding it is linked to. This is your feedback loop: run, check, change the model (or the
blocks), run again, until every kind reads `N of N agree`. How to read each:

| Mismatch | Pair | What it means | What to change |
|---|---|---|---|
| `move-without-flow` | Process ↔ Dynamics | items moved between two states with stocks, and no flow carries them | add the flow it names (or re-point the cloud flow it names) |
| `rework-without-flow` | Process ↔ Dynamics | items went back to an earlier state (↺ on the Process view) and the chain has no way back | a flow from the later state's stock back to the earlier one's |
| `chain-skipped` | Process ↔ Dynamics | items went straight from A to C; the chain only carries them through B | a flow from A's stock to C's, or fix the `on:` mapping if B was meant to be entered |
| `order-contradicted` | Process ↔ Dynamics | items went from A to B; the chain's flows run from B to A | the flows are the wrong way round: re-point them |
| `arrival-not-modelled`, `completion-not-modelled` | Process ↔ Dynamics | items arrive where no flow brings them in, or finish where no flow takes them out | the arrivals flow from outside into that stock, or the completions flow out |
| `waiting-without-goal`, `goal-without-loop` | Dynamics ↔ Blocks | items wait for the model's blocks in a stock no goal holds, or no loop closes | a goal on the stock (`hold: "<= 0"`), served by the block that moves them on |
| `flow-moved-by-nothing` | Dynamics ↔ Blocks | a flow of the chain no block moves and nothing measures | the block's `out:`, or an external block or a sensor when the outside moves it |
| `loops-not-connected`, `block-moves-no-flow` | Dynamics ↔ Blocks | the steps' loops share no stock; a block takes items and moves no flow | chain the stocks; give the block `out:` the flow it moves |
| `acts-undeclared` | Blocks ↔ Process | a block's runs moved items it does not declare | add the state to its `takes:` (`at:`, `to:`), or the flow to its `out:` |
| `moved-without-its-block` | Blocks ↔ Process | items moved with no block's run behind them, along a flow the model says a block moves | make the block record its events (event lines from its run), or say the outside does it (an external block) |
| `declared-not-seen-acting` | Blocks ↔ Process | a block had work and something else moved it on | as above: its events are not its own, or the model names the wrong mover |

Notes are not mismatches: `flow-not-seen` (a path the record has not taken yet: a retry, a dead letter), a block with
no work in the window, a kind whose states no chain models. Too little record says how much more it needs: run
longer, then check again.

### What "looks right" means

- [ ] Each kind of work is **one connected chain** of stocks in the Dynamics view.
- [ ] Work **arrives from outside** into the first stock, and **leaves to outside** only from the
      states where it really ends (done, rejected).
- [ ] **No stock without an inflow**, unless it is where work arrives.
- [ ] Every step's **block acts on a flow of the chain**, and its loop shares stocks with its
      neighbours: in the Blocks view the loops connect.
- [ ] A **collector** (the sensor) feeds the first state.
- [ ] Where the work is related, the **relations** are declared and recorded by the collector, and the Items
      page's Graph shows them (no item "not recorded", no cycle needing attention).
- [ ] Every block says what its work moves (`out: flow.NAME`). Without it the block has "no visible
      effect", is not drawn into any loop, and the Blocks view looks empty.
- [ ] Every goal has a block whose `out:` moves a flow of what the goal holds (`ergostat check` says
      "missing feedback" otherwise).
- [ ] Ages, ratios and scores are **auxiliaries**, not stocks: a stock is something with memory that
      only flows change.
- [ ] Every outward act goes through a gated action.
- [ ] Once the model has **systems**, each says what it is for (`description:`), and `check`'s architecture notes
      (`system-splits`, `systems-merge`, `interface`, `time-scales`, `purpose`) are answered or knowingly left: loose
      parts that fall into unlinked clusters may each be a system. A system whose subsystems share few links is
      nearly decomposable (`explain` says so): that is a good hierarchy, so leave its structure alone and change one
      subsystem at a time (`docs/proposals/architecture.md`).

### Modelling well: beyond correct

A model that passes every check above can still look amateur to the people who read it. Once it is correct, go
through [MODELLING-WELL.md](MODELLING-WELL.md) (`ergostat help modelling-well`) and its three review checklists.
The essentials:

- **Dynamics**: stocks named as quantities with natural units; ages and ratios as auxiliaries; an equation on
  every flow but the measured arrivals, its numbers parameters with units and `estimate: true`; four to nine stocks
  a system.
- **Blocks**: one goal per loop with `hold:` and `tolerance:` written (an item step's queue `"<= 0"`, tolerance 0:
  a step that takes items works only while its goal is off); a described sensor and collector; one block per step
  with `out:`; person and AI steps typed as such, on declared agents; cascades set setpoints; no `process:` that was
  not identified.
- **Process**: states declared; events `kind.verb-past`; fan-out and join done inside a run that holds the causing
  item's lease (the run's printed events, and `$ERGOSTAT_CMD event --add` from it, are recorded as caused by it),
  so the dashed lines between kinds appear; rework as a declared move back.
- **Everywhere**: the same names in every view, a description on every part.

## 3a. A system another ergostat runs: compose it, never copy it

When part of the person's work is run by **another ergostat** (another team's, another machine's), do
not re-model it and do not copy its YAML: compose it as a **remote system** (SPEC §4c). Its own ergostat
keeps running it; this model reads it.

1. **On the remote**, its owner makes a token for this model: `ergostat remote token support` (printed
   once). The token goes in a file here, never in the YAML (`incidents.token`, git-ignored).
2. **Here**, declare it and look before referencing anything:

   ```yaml
   remotes:
     incidents:
       url: http://127.0.0.1:8795       # https, or an SSH tunnel to the remote's page
       token-file: incidents.token
       every: 1m
   ```

   `ergostat remote` says whether it answers and which version of its model was read; `ergostat explain
   system.incidents` and the Diagram (its box, opened) show its parts, named `incidents-PART`.
3. **Link to its parts by those names**, only to read them: a cause (`driven-by: [+stock.incidents-open]`)
   for the load it puts on our stocks, a goal here on one of its measures, a block's input. Never point a
   block's `out:` at a remote part (`remote-output`): its actuators are its own. If it should act
   differently, write that down for its owner.
4. **Check against what it serves now**: `ergostat check` asks the remote first. A
   `remote-reference-unresolved` finding means the remote renamed or dropped a part you reference: fix the
   reference here (a stand-in is drawn meanwhile). `remote-unreachable` means it did not answer: the model
   runs on what it read last, with its age shown; fix the URL, the tunnel or the token.
5. **Use its measures, not its items.** The local fold never sees the remote's items: count them through
   the remote stock that counts them (its sensor is mirrored), or a sensor of your own, `query: {source:
   incidents, ref: stock.open}`.

A worked pair is `examples/remote-pair/` (a local *support* model reading a remote *incidents* model).

## 3b. A budget on what the agents cost

ergostat measures every run itself (SPEC §9.1): what its AI sessions cost (dollars as Claude Code reported them, or
estimated from tokens), its tokens, the CPU time and peak memory of its processes, its wall time and exit. You do not
write anything for this: an `ai` block's own `claude -p`, and `ergostat session` inside any block's `run:`, report
through the run. The Agents page shows each agent's totals and history; `ergostat agent NAME` the same.

When the person wants a limit ("no more than $5 a day on AI"), make it a goal, read from a built-in measure, and gate
the AI blocks on it, so the loop that does the work also stops when the money is spent:

```yaml
auxiliaries:
  ai-spend:
    unit: USD
    description: what the AI sessions cost over the last day
    driven-by: [+flow.rewritten]           # the more the writer works, the more it costs
    sensor: {builtin: ergostat.cost.usd, every: 5m}
goals:
  ai-budget:
    auxiliary: ai-spend
    hold: "<= 5"                           # $5 a day
blocks:
  go:
    type: expr                             # work while pages wait, and only while money is left today
    in: {waiting: goal.backlog-short.off, over: goal.ai-budget.off}
    expr: waiting * (1 - over)
    out: block.writer
  writer:
    type: ai
    prompt: prompts/rewrite.md
    in: block.go
    out: flow.rewritten
```

- `ergostat.cost.usd` is the last day's spend; `ergostat.cost.usd-hour` the last hour's (a rate limit). Narrow it to
  one block with `@writer`, or one model with `@model:opus`. Tokens, CPU and memory have measures of the same shape
  (`ergostat.cost.tokens`, `.cpu`, `.memory`, `.runs`): `ergostat measure` lists them.
- Spend is an auxiliary, not a stock: it is a sum over a moving window, with no memory of its own.
- `ergostat check` should say both goals are closed by a loop. Without the gate, the budget goal is "missing
  feedback": a number watched, not held.

## 3c. Stale readings and estimates

A controller acts on the newest reading as if it were now. When a sensor stops (a script failing, an API down, a
person away), its reading goes **stale** once 3 of its readings are overdue. Nothing watches for that unless the model
asks (SPEC §9.6): say on each goal whose loop must not act blindly what it should do then, from what the person told you
about the work:

- `on-stale: act` (the default): carry on with the old value. Right when acting on a slightly old value is harmless.
- `on-stale: hold`: keep the last command. Right when guessing is worse than waiting (scaling, spending, deleting).
- `on-stale: off`: count the goal as off, so its controller acts. Right when not knowing is itself the danger (a disk,
  a backup, a heartbeat): fail towards the safe side.

A block may say the same for what it reads directly. A machine block's input names its stale readings (`stale`), so a
program or an AI can say what it did about them.

Read a stock's **estimate** (`in: stock.X.estimate`, and `stock.X.uncertainty` beside it; or `observe: true` on the
stock to keep its estimate and innovations without a block reading them) when its sensor is slow,
sparse or noisy and the model knows its flows: the estimate moves with the flows between readings. Keep reading the
measured value when the sensor is quick and exact (a count of items), or when the stock's flows are not modelled (the
estimate then only carries the last rate on). A `model-disagrees` finding on a stock means its readings keep landing
away from what its flows predict: fix the model (a missing flow, a wrong rate) before trusting its estimate. The estimate
is only as good as the model: a model that is wrong in its structure drives the gain to 1, and the estimate is then the
readings again.

## 3d. People in the loop: rare, reached, and graduated

Human approval (a gated action's `gate: approve`, a block's `mode: advise`, a `person` block, a change waiting for the
owner) is for a system's **early stages**, while the person and you are still working out its feedback loops. Each one
is evidence of a loop not yet modelled; plan for it to go (SPEC §12o, §12p):

- **Reach the person while it lasts.** Everything waiting on them is one list, `ergostat inbox`, answered there
  (`ergostat inbox ID --approve | --deny | --done N`), from the page's *Needs attention* (Approve / Deny inline) or by
  the MCP `answer` tool when they tell you to (recorded as `owner via mcp`: never evidence for graduating). Set up
  `notify:` with the channels they use: `macos` on their own machine; `email` with `to:`; `slack` or `discord` with the
  webhook's URL in an environment variable (`url-env:`) or a file (`url-file:`), never in the YAML. Each channel is a
  gated action: at work, ask which channels may carry what, and write `gate: deny` (or `approve`) for the rest. Keep
  `group:` (2m) and `per-hour:` so they are not flooded; add `quiet:` hours, and `wait-at-most:` with `escalate-to:`
  when something must not wait. Messages carry only ids, kinds, classes and links unless a channel says `detail: full`
  (then scrubbed). Try it with a `command` channel (`run: "cat >> notified.txt"`) before any real one; never send a real
  message from a test.
- **Model them away.** Add `uses: {interventions: {use: interventions}}`: the interventions waiting become a stock, a
  goal holds the trend of those asked a day from rising, and each recurring class becomes an `ergostat.model-request`
  naming its remedies. Work the top request first (`ergostat inbox --stats` ranks them by the time they blocked their
  processes): automate the person's step with a block, add the loop that makes the approval a rule, change the software,
  or graduate the gate. Mark the request `--invest` while you work on it: for up to two weeks its class counts at most
  at its rate before, so the approvals the fix needs do not count against the trend.
- **Graduate with evidence, never silence.** `ergostat inbox --stats` says when a class has always been approved (five
  or more, none denied): then propose `gate: auto` (or an AI approver, or `mode: auto`) to the owner. Removing an alarm,
  raising its threshold, denying a channel or dropping a gate without automating what it guarded is recorded as
  **suppression**: it never lowers the measure, and the request stays open until the guard is back or the work is
  automated. Never change a gate yourself without the owner.

## 3e. Many sensors, or many items: a daemon instead of a process each

A `run:` sensor starts a process for every reading, and a `run:` block one for every run. That is right for a few;
for many (a hundred sensors every few minutes, items arriving faster than a process starts, a client slow to log
in) write a **daemon** (SPEC §9.7): one long-lived process ergostat hands readings and runs to as JSON lines.

**Before writing or changing one, read the skill's resource file `docs/skills/ergostat-author/daemons.md`** (beside
the skill's SKILL.md wherever it is installed). It has the shapes (a sensor's own daemon; one shared daemon per
outside service, with a kept session and batched reads; a push daemon; a block daemon taking items under leases),
the protocol, the rules, a tested template for each shape, and the checklist to run before you call a daemon done.
The rules in brief:

- one daemon per outside service, so a failure takes down only that service's sensors;
- never block the standard-input reader: work on other threads, print whole lines under one lock;
- tag every line with its `run` or `request`; end each run with exactly `{"done": EXIT, "run": ID}`, an int;
- honour `cancel` within 10 s; heartbeat at a third of the declared `heartbeat:`;
- fail hard (exit non-zero) on what you cannot handle; answer `{"error": WHY}` for one reading you could not take;
- an item's `env` goes to what you start for that item, never into the daemon's own environment;
- done means: `check` passes, a pipe test by hand passes, a short run on a scratch copy records readings and
  moves items with no restarts, and replaced `run:` sensors read the same.

## 3f. A controller that already runs: an autoscaler, an alert rule

Much of the control in a company already runs elsewhere: a Kubernetes HPA, a cloud autoscaling group, an alert rule
that pages, a vendor's rate limiter. Never rebuild one as a `program` block. Draw it as what it is, an **external**
block (ergostat never runs it), reading what it watches and moving what it moves, and ask ergostat to **identify** its
law from the record (SPEC §12d, *Existing controllers*):

```yaml
stocks:
  replicas: {unit: pods, sensor: {run: ./replicas.sh, every: 15s}}     # what it sets, as the cluster reports it
auxiliaries:
  load: {unit: pods, sensor: {run: ./busy.sh, every: 15s}}                # the work, in pods' worth of CPU
  utilisation: {unit: pods/pods, sensor: {run: ./cpu.sh, every: 15s}, equation: auxiliary.load / stock.replicas}
flows:
  scale: {to: replicas, two-way: true}                                   # how it moves it: up and down
blocks:
  hpa-checkout:
    type: external
    agent: kubernetes                                                    # agents: {kubernetes: {external: true}}
    in: auxiliary.utilisation
    out: flow.scale
    identify: {input: auxiliary.utilisation, output: stock.replicas}
```

- `input` is the signal it watches (a stock, flow or auxiliary with a sensor); `output` is what it sets: a **stock**
  it holds at a level (replicas, a pool's size: then its `out:` is a two-way flow into that stock), a **flow** it sets
  directly (a rate limit), or an **auxiliary** (an alert's firing, 0 or 1: identified and drawn, but not run ahead).
  Write `in:` and `out:` as well: they are what the diagrams draw.
- Read both at the controller's own pace (its sync period, an alert's evaluation interval): the grid is the output's
  sensor period, and a law faster than its sensors cannot be told.
- ergostat fits an on-off law (an alert: thresholds, hysteresis, `for:`, minimum on and off times), proportional with
  saturation, PI with a deadband, and three-position step (floating) control (the HPA's shape: up and down by a step after a
  duration past a threshold, each with a cooldown), each with a delay, and keeps the one that predicts the held-out record best for its
  number of parameters. The Blocks view writes the law in the block, marked *identified*; the closed-loop projection,
  what-if and risk run it in place of a generic stand-in.
- `external-unidentified` means too little record (40 points of both at least, and three moves of its output) or no law
  fits: wait for more, or check the sensors read the right series. `external-not-run` means its output is an auxiliary
  (or a stock its `out:` flow does not move): the law is drawn, but the projection runs a generic stand-in.
- Inside its own loop (an HPA reads utilisation, which its replicas change at once), a proportional or PI law fitted with
  no delay has its gain biased toward 0 (Ljung ch. 13), and says so: read its gain as a lower bound. A switching law's
  thresholds carry a *spread* (how far they could move and tell the moves as well), not a standard error.
- If the owner retuned the controller in the window, the law fitted mixes both: identify again once the record since the
  change is long enough (ergostat does not yet say that a law changed).
- When the vendor documents the law (the HPA's is public), say so in the block's `description:` and compare: the
  identified thresholds and cooldowns are what it actually did, which is the point.

## 3g. A loop the record does not identify, and projections far off after a burst

- **`loop-not-identifiable`** on a goal means the record so far does not identify its loop's process (it follows little
  of the record held out, or its errors are not white, or not independent of u): no `process:` is proposed, and you must
  not write one by hand from those numbers. Do what the finding says would identify it: approve the **step test** it
  offers (from the loop's panel, or the inbox; ergostat must be running), or wait for a large outside change in its
  input (a burst of arrivals identifies it best: ergostat looks around one by itself and says "identified around an
  outside step at T"), or for more record. A loop that never sees either stays unidentified, and that is the honest
  answer.
- **Projections far off after a burst** (the strip says "Low confidence: ..." in front, the band wide): the model fit the
  quiet record, and the burst found what it lacks. Before tuning a value, suspect missing structure: a **capacity**
  (reviewers or workers at their most: a `MIN(stock / time, capacity)` outflow, or a block's `pool:`), a queue that
  drops or times out, a second path the burst took. Say so to the owner and ask for a redesign (the modelling loop's
  `redesign`, or a proposal of the structure with the record of the burst as its evidence); value proposals on a
  model missing structure only chase the burst.
- The proposals ergostat makes are the same items as the record grows: one revised in place (`revisions`) is not
  churn. One superseded says why (what it was about was edited or removed, or it is no longer found).

## 3h. When will it be done: the items' completion estimates

The Items list's **done by**, an item's page and the Timeline give each open item a p50 and a p90 finish (SPEC §5a,
*Completion estimates*). They are not a median per state added up: they come from a simulation of every open item
together, run 200 times from the record of the last two weeks:

- each step a block takes is a **queue** at that block, at most its capacity at once: the smallest of its `pool`, its
  agent's `at-once` and its daemon's `concurrency` (an agent's seats are shared by every block it runs); a
  `workspace:` pool of three keeps at most three items between their first take and their finish; 100 tickets
  and a pool of six finish about 100 / 6 run times after now, not one run time after it;
- each run is one the block really made, drawn whole: how long, and whether it moved the item on, gave it back
  (rework: back in the queue, after its put-off) or expired;
- a step no block takes (a person's review, CI that pushes its answer) is the time items stayed there, given how
  long this item has been there already (Kaplan–Meier: the ones still waiting count, as censored);
- where an item goes next is where the record's items went (the rework loops too); what it waits on (`blocked_by`)
  holds it in its first state.

The item page says why ("6 of 6 busy in dev; 34 ahead of it; a run takes 18m (median)"); the what-if beside a
block's identified model (its pool, its share of failed runs) moves the estimates. **What makes them wrong**, and
so what to model: a capacity no block declares (one reviewer for two kinds, an API's rate limit: give the step a
`pool` or the agent an `at-once` that says it), a goal that switches a block off
(the estimate assumes it takes whenever it has room), a process that changed in the last two weeks (the old runs
still count), a step whose runs give the item back while they wait for something undeclared (the simulation
takes each give-back as rework, so the estimates come out late), and a step nothing has
left yet (its items are assumed to go to the next state in order). Under twenty runs no p90 is said. A block with
fewer than five runs on record is said as assumed on the item's page.

## 3i. Programs fail hard, and are repaired

The scripts the model's blocks run (collectors, steps, actuators) will fail: an API changes shape, a field goes
missing, a token expires. Write them to **fail hard**: let an error they cannot handle raise, its traceback on standard
error, and exit non-zero. Never `except: pass`, `except Exception: pass` or `|| true` on the whole command: a failure
hidden is one nobody sees and nothing can fix.

Add `use: repair` (once a model, like `modelling`; SPEC §12r) when the owner wants failures fixed without them. Each
failed run becomes an `ergostat.failure` item, one per signature, counted; one whose block runs a program of the
project's is fixed by an AI (haiku by default, with no tools: ergostat gives it the program and the files beside it) in
a clone of the repository, tested in the sandbox, and proposed as the gated action `apply-fix` with its impact report.
What you set:

- **`read-only: true`** on a block whose program changes nothing outside (a collector that only reads): its fix is
  re-run for real on the input that failed. Say it of nothing that writes. List the hosts it reads in `network:`
  (`[tracker.example.com]`): only those, for GET and HEAD.
- **`test:`** in `with:` for programs that write: the project's tests, run in the sandbox. Without it such a fix is
  untested, and only a person may approve it.
- **`approver:`** `person`, the only one for now: the owner reads each fix in the inbox. `ai` is refused by `check`
  until a sound guard exists (GAPS).
- **`daily:`** and **`budget:`**: what the loop may spend. The model's folder must be in a git repository, its programs
  committed.

## 4. Common mistakes

| Looks like | What went wrong | Fix |
|---|---|---|
| Many stocks, each with only an outflow to a cloud | Each state modelled on its own; moves between states drawn as leaving the system | Chain the flows: `from:` the earlier state's stock, `to:` the later one's |
| Many feedback loops that share nothing | Same cause: the stocks they hold are not connected | Chain the stocks; each step's loop then shares the chain |
| Loops with no visible way work arrives | No collector; items appear by hand | Add the collector block that polls the source |
| An empty Blocks view; blocks drawn with nothing attached | Blocks without `out: flow.NAME` | Give each block the flow its work moves |
| A goal nobody acts on | A goal whose blocks move no flow of what it holds | Point the step's `out:` at the flow that drains the goal's stock |
| A step that does everything | One big block hides the process | Split it into states and steps; the diagrams can then show it |
| A step that never runs though items wait | Its goal has a tolerance (or a setpoint above 0), so it is never off | An item step's goal is `hold: "<= 0"`, `tolerance: 0` |
| Two kinds of work and no dashed line between them in the Process view | The children were opened by a scheduled block, which nothing caused | Open them from the run that holds the parent's lease (MODELLING-WELL.md section 3) |

## 5. Tools

- **CLI**: `ergostat check`, `explain`, `run`, `status`, `item`, `lease`, `actions`, `remote`, `help TOPIC`.
- **MCP**: `claude mcp add ergostat -- ergostat -C PROJECT_DIR mcp` gives you `spec`, `check`,
  `coherence` (the three views against each other), `explain`, `status`, `items`, `try_change` (test a
  change before writing it) and more.
- **Docs**: [SPEC.md](SPEC.md) (the format; sections 5a items, 6 sensors, 7 flows, 8 goals, 9 blocks,
  9.5 leases, 12k gated actions, 4c remote systems), [MODELLING.md](MODELLING.md) (improving a model from its record),
  [MODELLING-WELL.md](MODELLING-WELL.md) (the craft of each diagram),
  [QUICKSTART.md](QUICKSTART.md), `examples/ticket-factory/` and `examples/the-job/`.

## 6. When ergostat itself is wrong

If ergostat cannot express something the person needs, crashes, or behaves wrongly, draft a report and
tell the person where it is. **Never post anything yourself**: no `gh`, no issue, no web form.

- Draft it with the MCP tool `report_upstream` (`says`: what went wrong, in a line; `details`; `parts`: the parts
  involved, from which ergostat makes a generic reproduction; `findings`; `repro`: a tiny generic model you wrote
  that shows it), or `ergostat report --draft "..." [--part P] [--repro FILE]`. A block (the modelling loop's improver
  or redesigner) prints `{"report": "what ergostat could not express"}`.
- ergostat scrubs it before anyone reads it (the model's names, paths, hosts, URLs, emails, keys, ticket keys and the
  owner's denylist become stand-ins like `stock-1`; SPEC §12m) and writes it to the state directory's `reports/`
  folder. Its own crashes are drafted the same way, once each.
- Tell the person: the file it returns, and `ergostat report ID` (or the report's item page), which shows the text,
  the scrub log and a link that opens a new issue with the title filled in. They read it and submit it by hand, or
  dismiss it.
