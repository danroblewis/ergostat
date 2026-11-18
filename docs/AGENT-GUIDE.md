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
5. **One block per step that does the work**, taking items in its state:
   `takes: {kind: KIND, at: STATE, to: [NEXT]}`, with `pool:` (how many at once) and, for AI work, a
   prompt. A run leases its item, does the step, and prints the event that moves the item on.
   ergostat retries a run that fails or goes silent, and parks an item that keeps failing as a dead
   letter. A program may **print events as it goes**: each line is taken when it is printed, not
   when the run ends, so a long run's findings land at once (flush each line: `print(...,
   flush=True)`), and every event it prints renews the lease it holds, so a run that reports its
   progress is never taken for silent. If it is stopped part way, what it printed stays. A step a person must do is a `type: person` block with `ask:`; it is asked while its goal
   is off (only `program` and `ai` blocks take items one at a time).
6. **Goals on what matters**: how long the oldest item has waited in a state
   (`measure: oldest` on a stock's sensor, `hold: "<= 4"` hours), how many are waiting, throughput.
   A goal is what makes a block's work a feedback loop; give each step's queue one.
7. **Gated actions for anything that acts outward** (moving a Jira ticket, opening a PR, posting a
   message): declare them under `actions:` with a gate (`approve` to start, `auto` once trusted), and
   have the step ask for them (`$ERGOSTAT_CMD act NAME --arg k=v` from a script, or as a tool from an
   AI session). See SPEC section 12k.
8. **Check and look** (section 3), and fix everything it finds before showing the person.
9. **Last, reconcile the three views.** Run it (stand-ins are enough), then `ergostat check` again: its
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
      second's results finish the first. None means the runs do not record `causedby`.
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
- [ ] Every block says what its work moves (`out: flow.NAME`). Without it the block has "no visible
      effect", is not drawn into any loop, and the Blocks view looks empty.
- [ ] Every goal has a block whose `out:` moves a flow of what the goal holds (`ergostat check` says
      "missing feedback" otherwise).
- [ ] Ages, ratios and scores are **auxiliaries**, not stocks: a stock is something with memory that
      only flows change.
- [ ] Every outward act goes through a gated action.

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

## 4. Common mistakes

| Looks like | What went wrong | Fix |
|---|---|---|
| Many stocks, each with only an outflow to a cloud | Each state modelled on its own; moves between states drawn as leaving the system | Chain the flows: `from:` the earlier state's stock, `to:` the later one's |
| Many feedback loops that share nothing | Same cause: the stocks they hold are not connected | Chain the stocks; each step's loop then shares the chain |
| Loops with no visible way work arrives | No collector; items appear by hand | Add the collector block that polls the source |
| An empty Blocks view; blocks drawn with nothing attached | Blocks without `out: flow.NAME` | Give each block the flow its work moves |
| A goal nobody acts on | A goal whose blocks move no flow of what it holds | Point the step's `out:` at the flow that drains the goal's stock |
| A step that does everything | One big block hides the process | Split it into states and steps; the diagrams can then show it |

## 5. Tools

- **CLI**: `ergostat check`, `explain`, `run`, `status`, `item`, `lease`, `actions`, `remote`, `help TOPIC`.
- **MCP**: `claude mcp add ergostat -- ergostat -C PROJECT_DIR mcp` gives you `spec`, `check`,
  `coherence` (the three views against each other), `explain`, `status`, `items`, `try_change` (test a
  change before writing it) and more.
- **Docs**: [SPEC.md](SPEC.md) (the format; sections 5a items, 6 sensors, 7 flows, 8 goals, 9 blocks,
  9.5 leases, 12k gated actions, 4c remote systems), [MODELLING.md](MODELLING.md) (improving a model from its record),
  [QUICKSTART.md](QUICKSTART.md), `examples/ticket-factory/` and `examples/the-job/`.

## 6. When ergostat itself is wrong

If ergostat cannot express something the person needs, or behaves wrongly, write it down generically
(no employer names, systems, people or data) and offer the person a GitHub issue for this
repository. File it only after they approve the exact text.
