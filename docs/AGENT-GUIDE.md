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
   letter. A step a person must do is a `type: person` block with `ask:`; it is asked while its goal
   is off (only `program` and `ai` blocks take items one at a time).
6. **Goals on what matters**: how long the oldest item has waited in a state
   (`measure: oldest` on a stock's sensor, `hold: "<= 4"` hours), how many are waiting, throughput.
   A goal is what makes a block's work a feedback loop; give each step's queue one.
7. **Gated actions for anything that acts outward** (moving a Jira ticket, opening a PR, posting a
   message): declare them under `actions:` with a gate (`approve` to start, `auto` once trusted), and
   have the step ask for them (`$ERGOSTAT_CMD act NAME --arg k=v` from a script, or as a tool from an
   AI session). See SPEC section 12k.
8. **Check and look** (section 3), and fix everything it finds before showing the person.

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

- **CLI**: `ergostat check`, `explain`, `run`, `status`, `item`, `lease`, `actions`, `help TOPIC`.
- **MCP**: `claude mcp add ergostat -- ergostat -C PROJECT_DIR mcp` gives you `spec`, `check`,
  `explain`, `status`, `items`, `try_change` (test a change before writing it) and more.
- **Docs**: [SPEC.md](SPEC.md) (the format; sections 5a items, 6 sensors, 7 flows, 8 goals, 9 blocks,
  9.5 leases, 12k gated actions), [MODELLING.md](MODELLING.md) (improving a model from its record),
  [QUICKSTART.md](QUICKSTART.md), `examples/ticket-factory/` and `examples/the-job/`.

## 6. When ergostat itself is wrong

If ergostat cannot express something the person needs, or behaves wrongly, write it down generically
(no employer names, systems, people or data) and offer the person a GitHub issue for this
repository. File it only after they approve the exact text.
