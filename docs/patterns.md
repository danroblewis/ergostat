# Multi-agent patterns, read as control systems

The common multi-agent design patterns, each read in control-theory and system-dynamics terms,
with the ergostat model it would take. The point is twofold: to see what each pattern really is
as a feedback structure (where the stocks are, what decides, what acts, what loops), and to test
the configuration format: every pattern here should be expressible, and where it is not, the gap
is named.

The YAML sketches predate `docs/SPEC.md` and use an earlier draft (controllers with `serves` and
`drives`, valves with `by` and `do`); the specification is the current form: controllers and
valves are blocks with `in` and `out`, and machines are named with `agent:` only when shared.
Neither is implemented yet.

Sources for the pattern list: Anthropic, [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
(prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer, and
autonomous agents); LangChain, [multi-agent architectures](https://docs.langchain.com/oss/python/multi-agent)
(network, supervisor, hierarchical, custom); Microsoft AutoGen,
[multi-agent design patterns](https://microsoft.github.io/autogen/0.4.0/user-guide/core-user-guide/design-patterns/intro.html)
(concurrent agents, sequential workflow, group chat, handoffs, mixture of agents, multi-agent
debate, reflection, code execution). Blackboard, human-in-the-loop and budgets are older or more
general patterns added for completeness.

## Three ideas used throughout

### Signals and work

Two kinds of thing move through these systems:

- **Work** moves through flows and piles up in stocks: tickets, drafts, pull requests, pages,
  subtasks. This is the system-dynamics side.
- **Signals** carry information about the work: a measurement of a stock (how many drafts are
  waiting), a goal (at most 3), an error (2 over), a command (do 5). This is the control-theory
  side.

They are the same system seen two ways. In a block diagram the plant's integrator is a stock and
its output is the stock's level; in a stock-and-flow diagram, a flow's rate equation that depends
on a stock is a decision rule (Forrester called it a policy): a controller, undrawn. The valve is
where the two meet: a signal (a command, a work order) becomes a flow of work.

### Servos and cascades

A plain valve takes a command and moves. A **servo** (a servomechanism) is an actuator with its
own feedback: it is given a target and corrects itself until it reaches it. An AI agent session
is a servo, not a plain valve: told "rewrite this page" or "make the tests pass", it loops
internally (plans, edits, checks, retries) until it meets the target or gives up.

Putting a servo under another controller is **cascade control**: an outer (primary) loop decides
what and how much, at a slow cadence, against stocks it can measure; the inner (secondary) loop
inside the servo decides how, fast, against goals of its own. To the outer loop the servo is an
actuator described by a simple wrapper model: the command it was given, what it actually
achieved, its limits, its usual delay, how often it fails. Its inside can be modelled as a loop
of its own when that is worth it.

This is why "deciders and doers" is the wrong split. The real split is by level: each level's
decisions are made against that level's stocks, and treat the level below as an actuator, judged
by what it did to the stocks, not by its report. The same model can sit at either level.

### What every pattern must answer

For each pattern: where are the stocks (the work that waits), what measures them, what decides,
what acts, and is there a loop: is anything ever compared with a goal and corrected? Many
patterns, as usually built, are open loops: they act, and nothing checks the result against a
measured goal. That is the most common finding.

## The patterns

### 1. Prompt chaining / sequential workflow

**What it is.** A task split into fixed steps, each processing the previous step's output,
optionally with a check (a gate) between steps.

**As a control system.** Stocks in series: work waiting before each step. Each step is a valve
(a servo) draining one stock into the next. A gate is a sensor plus a rule on the stock between
steps: pass, or send back. Without gates it is open loop: nothing compares the result with a
goal. This is the file-queue example, generalised.

```yaml
stocks:
  outlines: { sensors: { n: { run: "ls work/outline | wc -l" } } }
  drafts:   { sensors: { n: { run: "ls work/draft | wc -l" } } }
flows:
  outline: { to: outlines, valve: { by: claude, do: "prompt: outline the next request" } }
  draft:   { from: outlines, to: drafts, valve: { by: claude, do: "prompt: draft from the outline" } }
goals:
  few-outlines-waiting: { stock: outlines, hold: "<= 5" }
controllers:
  pace-drafting: { serves: [few-outlines-waiting], drives: [draft], rule: { when: "outlines > 5" } }
```

**Finds.** Where work piles up between steps; which step is the bottleneck; a step that is
starved (its input stock at zero). **Gap:** a gate that sends work *back* is a flow from a later
stock to an earlier one, which the format expresses, but the quality the gate checks needs a
measurement (see evaluator-optimizer).

### 2. Routing / handoffs

**What it is.** An input is classified and sent to a specialised handler: cheap requests to a
small model, hard ones to a capable one; or an agent hands the conversation to another.

**As a control system.** One inflow split into several flows, each with its own valve. The
router is a controller whose command is not "how much" but "which way": a splitter. Its goal is
usually implicit (cost, latency, quality per class). Handoffs are routing done by the handler
itself, mid-task.

```yaml
flows:
  to-small: { from: requests, valve: { by: haiku,  do: "prompt: answer" } }
  to-large: { from: requests, valve: { by: opus,   do: "prompt: answer" } }
controllers:
  router:
    serves: [cost-within-budget, quality-high]
    drives: [to-small, to-large]
    by: haiku
    do: "prompt: say which handler: small or large"
```

**Finds.** Whether routing actually keeps the goals it exists for: cost per request, quality per
class. **Gap:** a controller whose output picks among flows (a split ratio) rather than setting
an amount: the command needs a shape (which flow, per unit of work).

### 3. Parallelization: sectioning / concurrent agents

**What it is.** Independent subtasks run at once, results combined.

**As a control system.** One stock drained by several valves in parallel: a capacity decision.
The controller decides how many to run at once (the number of open valves), against a goal on
the waiting stock or on latency. The join is a stock of finished parts waiting for their
siblings.

**Finds.** Whether more parallel workers actually drain faster (saturation elsewhere: a shared
machine, rate limits, the join). **Gap:** none; this is valves with `at-once` on their machine.

### 4. Parallelization: voting / mixture of agents

**What it is.** The same task run several times (or by several models); outputs compared,
combined, or aggregated by a final model.

**As a control system.** Redundant sensors: several measurements of one thing, combined to
reduce error. Here the "thing measured" is the quality or correctness of an answer, and voting
is the estimator. Mixture of agents adds an aggregator: a controller that combines several
proposals into one command.

**Finds.** How often the voters disagree (the noise in the measurement), and whether more voters
improve anything. **Gap:** sensors that measure a property of a unit of work (its quality),
rather than the level of a stock.

### 5. Orchestrator-workers / supervisor / hierarchical teams

**What it is.** A central agent breaks a task into subtasks it decides on the fly, hands them to
workers, and combines the results. Hierarchical teams stack this: a supervisor of supervisors.

**As a control system.** Cascade control, directly. The orchestrator is the outer controller:
it measures the stock of remaining work and issues work orders. Each worker is a servo. In a
hierarchy, each middle supervisor is a controller to the level below and a servo to the level
above.

```yaml
stocks:
  subtasks-open: { sensors: { n: { run: "ls tasks/open | wc -l" } } }
goals:
  finish-the-feature: { stock: subtasks-open, hold: "== 0" }
flows:
  plan:   { to: subtasks-open }                        # what the orchestrator adds, as it decides
  worked: { from: subtasks-open, valve: { by: claude-worker, do: "prompt: do the subtask you are given" } }
controllers:
  orchestrator:
    serves: [finish-the-feature]
    drives: [worked, plan]
    by: claude-lead
    do: "prompt: given the open subtasks and what came back, issue the next work orders"
```

**Finds.** Whether the work stock actually falls; the orchestrator adding subtasks faster than
workers finish (a growing backlog it creates itself); workers that report done while the stock
says otherwise. **Gap:** a controller whose output is another controller's goal (true cascade),
and an agent that both creates work (`plan`) and commands its completion: the format can say
both, but the second makes the orchestrator its own disturbance, which ergostat should point out.

### 6. Evaluator-optimizer / reflection / author-critic

**What it is.** One agent produces, another (or the same one, reflecting) critiques, and the
producer revises, until the critic accepts.

**As a control system.** A feedback loop on quality. The draft's quality is the stock (or rather
its measurement); the critic is the sensor and the controller (it measures quality against a
standard and says what to change); the author is the servo. Reflection is the same loop inside
one agent: an inner loop invisible from outside.

Control theory warns about two things here. Without an iteration limit the loop can oscillate or
never settle (the critic always finds something): it needs a cap, the anti-windup of agent
loops. And the critic's standard is the setpoint: if it drifts, the loop holds the wrong thing
very precisely.

```yaml
stocks:
  drafts-below-standard: { sensors: { n: { run: "./count-failing-reviews.sh" } } }
goals:
  all-pass: { stock: drafts-below-standard, hold: "== 0" }
flows:
  revised: { from: drafts-below-standard, valve: { by: claude-author, do: "prompt: revise using the critique", max: 3 } }
controllers:
  critic:
    serves: [all-pass]
    drives: [revised]
    by: claude-critic
    do: "prompt: review each draft; list what must change"
```

**Finds.** Rounds per accepted draft; loops that never settle; a critic that accepts everything
(a sensor stuck at zero). **Gap:** a limit on revisions per unit of work, not per run.

### 7. Group chat / network / swarm

**What it is.** Several agents share a conversation; a manager (round-robin or a model) picks who
speaks next, or any agent can call any other.

**As a control system.** A shared stock: the conversation, or its open questions, is the
blackboard every agent reads and writes. The manager is a controller choosing which valve opens
next. With no manager (network, swarm), control is distributed: every agent is both a controller
and a valve, and the coupling is everything. This is where the stock-and-flow view matters most,
and where loops nobody designed appear.

**Finds.** Whether the open questions actually fall; agents that keep talking without changing
the stock; two agents undoing each other. **Gap:** many controllers commanding many valves with
no single owner: the format can declare it, and ergostat should flag it as uncoordinated.

### 8. Multi-agent debate

**What it is.** Agents propose and challenge each other's answers over rounds, converging on one.

**As a control system.** Several controllers proposing commands for one decision, with
arbitration: their commands are combined (by vote, by a judge, or by convergence). In control
terms it is a way of reducing the error of one decision by redundancy, close to voting, with
feedback between the proposers.

**Finds.** Rounds to converge; whether debate changes the outcome versus one agent. **Gap:**
several controllers driving one valve, with the arbitration rule written down.

### 9. Blackboard / mediator

**What it is.** Agents coordinate only through a shared store (the blackboard), or through a
mediator that relays between them, never directly.

**As a control system.** The blackboard is a stock, and coordination through it is ordinary
feedback: each agent reads the shared state and acts on it. The mediator is a controller that
owns the coupling. This is the pattern closest to ergostat itself.

**Finds.** The blackboard growing without bound (nobody consumes what is posted).

### 10. Human in the loop

**What it is.** A person approves, edits or decides at some step.

**As a control system.** A valve in `advise` or `manual` mode: the work waits for a person, whose
response time is the loop's dominant delay (hours, against an agent's minutes). Or a person as
the controller, deciding what the agents do.

**Finds.** The person as the bottleneck; a backlog of things awaiting approval (windup: the
agents keep proposing faster than the person approves). The deps example is this pattern.

### 11. Budgets, guardrails and rate limits

**What it is.** Limits on spend, tokens, calls or actions.

**As a control system.** A goal on a cost stock (spend this hour), and saturation of the valves
below it when the budget is near. Guardrails are constraints at the valve: commands outside
bounds are refused.

```yaml
stocks:
  spend-this-hour: { unit: USD, sensors: { usd: { run: "./spend.sh" } } }
goals:
  within-budget: { stock: spend-this-hour, hold: "<= 20", critical: true }
```

**Finds.** Which loops are being held back by the budget (saturated by cost, not by work).
**Gap:** a goal on one stock that limits valves on other flows: a constraint rather than a
setpoint, shared across controllers.

### 12. Autonomous agent / code execution

**What it is.** One agent with tools, deciding its own steps until done; or an agent that writes
and runs code.

**As a control system.** A single servo with a rich inner loop, and often no outer loop at all:
open loop from the outside. To make it part of a control system it needs an outer controller and
a measured goal: what stock should it change, and how will anyone know it did?

**Finds.** Whether the session's claimed result shows in a measured stock.

## What the patterns ask of the format

Most patterns fit the draft format as it is: stocks with sensors, goals, flows with valves,
controllers serving goals and driving flows, agents as machines. Collected from the gaps above,
the format still needs:

1. **Commands with a shape.** Not only "how much" but "which way" (routing) and "which item"
   (orchestrators assigning specific work).
2. **Cascade.** A controller whose output is another controller's goal.
3. **Limits per unit of work,** not only per run (revision rounds in evaluator-optimizer).
4. **Measurements of a property of work,** not only of a stock's level (quality, correctness).
5. **Several controllers driving one valve, with the arbitration written down** (debate, group
   chat); and ergostat flagging it when nothing coordinates them.
6. **Constraints shared across controllers** (budgets): a goal on one stock that bounds valves on
   others.

And what ergostat should find in any of them: stocks that only grow, loops that never settle,
agents that are their own disturbance, workers whose reports disagree with the stocks, and the
person or machine that is everyone's bottleneck.
