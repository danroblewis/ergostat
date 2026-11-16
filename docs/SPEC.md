# The ergostat model: specification (draft)

This specifies the configuration format: the files people and AI agents write to describe a
system. It replaces the TOML format. The ideas behind it are in `docs/CONCEPTS.md`, the names
come from `docs/vocabulary.md`, and `schema/ergostat.schema.json` is the machine-checkable form
of this document.

**Status: draft for review, implemented.** `ergostat check`, `convert` and `run` follow this document
(`ergostat/spec/`). Where building it settled a question, the decision is marked *Decided*.

## 1. Principles

1. **Four kinds of thing are written, and a fifth when it says something.** Stocks, flows, goals
   and blocks; and agents, only for machines shared by several blocks. (Kinds of item, section 5a,
   say how to read the record, not what the system is.) Valves, controllers,
   disturbances, errors, loops and diagrams are worked out from them, never declared.
2. **Two layers.** The material layer (stocks and flows: where work moves and accumulates) and
   the information layer (blocks and the signals between them: deciding and commanding). This is
   system dynamics' stocks and flows plus converters and connectors, and control engineering's
   function blocks and signals.
3. **Every reference is written once, on the side that acts.** A goal names its stock or flow; a
   flow names the stocks it connects; a block names its inputs and outputs, and its machine when
   it has one. Flows are passive: they never say who moves them. Reverse relations (a stock's
   goals, a flow's actuator, a machine's blocks) are looked up, never written, so they cannot
   drift.
4. **Nest only what is exclusively owned.** A sensor measures exactly one stock or flow, so it
   is written inside it. Everything else is top-level and referenced by name.
5. **What is real is measured.** A stock's value is only ever its sensors' readings. What blocks
   report is evidence, judged against the stocks.
6. **Nothing is a claim nobody acts on.** Every block is executed by ergostat, executed by a
   machine ergostat runs, or explicitly observed (`external`): the file never describes behaviour
   that nothing performs.
7. **Each key says what it names.** `from` and `to` are stocks, `stock` and `flow` say which kind
   a goal is about, `agent` is a machine; no word means two things.

## 2. Files

- The main file is `ergostat.yaml` at the root of the project. YAML 1.2; a JSON file is also
  valid YAML and is accepted.
- `include:` names more files (paths or globs, relative to the including file). Included files
  may include others. All files share one namespace.
- Each top-level section is a map keyed by name; maps from all files are merged. **Defining a
  name twice is an error**, reported with both files and lines. There is no overriding.
- A file may set `defaults:` (at present only `system:`), which applies to the stocks, flows,
  goals and blocks defined in that file, and not to the files it includes.

## 3. Names, references and values

**Names** are lowercase letters, digits and `-`, starting with a letter: `inbox`,
`keep-inbox-short`. Names are unique within each section; the same name may be used in two
sections (a stock and a goal both called `inbox`), but it is discouraged.

**References** point at a thing, or at one port of it:

| Reference | Means |
|---|---|
| `stock.inbox` | The stock's measured level (its current best reading) |
| `stock.inbox.count` | The reading of one of its sensors, `count` |
| `variable.quality` | A variable's value (as an output: what a block sets it to) |
| `flow.processed` | As an input: the flow's measured rate. As an output: what a block moves along this flow |
| `goal.inbox-short` | The goal's setpoint (r) |
| `goal.inbox-short.error` | The goal's error, e = r − y |
| `goal.inbox-short.off` | 1 while the goal is off, 0 while it holds |
| `block.decide` | A block's output (its only output, or its output named `out`) |
| `block.decide.urgent` | A block's output port `urgent` |

Where a key can only name one kind of thing, the name is written bare: a goal's `stock: inbox`, a
block's `agent: claude`, an `onoff` block's `goal: inbox-short`.

**Durations**: `30s`, `5m`, `2h`, `1d`, or a number of seconds.

**Setpoints**: `"<= 20"`, `"< 20"`, `">= 5"`, `"> 5"`, `"== 50"`. Quote them (YAML reads `>` as
a folding marker).

**Commands** (`run:`) are shell commands, run with `sh -c` in the project's root, with the
inputs described in section 9 on standard input.

**Style.** The examples use block-style YAML: one key per line. Short lists may stay on one line
(`in: [goal.a.error, goal.b.error]`). Flow style (`{ ... }`) is valid but not used here.

## 4. Top level

```yaml
name: checkout                  # the project's name (default: the folder's)
include:
  - systems/*.yaml
keep: 30d                       # how long the record is kept
defaults:
  system: core
sources:                        # where existing metrics live
  ...
items:                          # optional: kinds of item, read from the record
  ...
systems:                        # optional: systems, and the systems they are within (section 4a)
  ...
stocks:
  ...
flows:
  ...
goals:
  ...
blocks:
  ...
agents:                         # optional: machines shared by several blocks
  ...
```

## 4a. Systems: parts made of parts

A system is a named part of the model, and it may be part of another: they nest, the way a
cascade's inner loop is one block of the outer loop. Each stock, flow, goal and block belongs to
one system (its `system:`, or its file's `defaults: system:`), and so to every system that one
is within.

```yaml
systems:
  factory:
    description: tickets in, releases out
  intake:
    within: factory
  delivery:
    within: factory
  product:                       # within no other system: the top level
    description: what customers use
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `description` | string | none | |
| `within` | system name | the top level | The system it is part of. A system within itself, at any depth, is an error |
| `show` | stock, flow or variable references | its goals' | The measures its box shows when it is drawn as one part: its control panel |

A system named by a part and not described here is a top-level system.

**Its interface is worked out, never written.** Whatever crosses a system's boundary is one of
its ports:

| Port | In | Out |
|---|---|---|
| setpoint | a block outside sets a goal inside (a cascade) | a block inside sets a goal outside |
| command | a block outside commands one inside | the other way |
| action | a block outside moves a flow inside | a block inside moves a flow outside |
| signal | a block inside reads a stock, flow or goal outside | a block outside reads one inside |
| material | a flow from a stock outside into one inside | a flow out to a stock outside |
| influence | a flow inside is `driven-by` something outside | something inside drives a flow outside |

A system whose setpoint comes in from outside, and whose goal's measurement goes back out, is an
**inner loop**: seen from outside, it is one block that holds what it is told, and an outer loop
can treat it so. `ergostat explain system.NAME` says what goes in and out, and names it an inner
loop when it is one.

**Drawn as parts.** The control diagram draws each system as one box: its ports on its edges
(inputs left, outputs right, each named for the part inside it reaches, with that part's
reading), how the loops inside it are doing, and its measures: each one's value, setpoint, health
and trend (`show:`, or by default what its goals hold). With every system closed, the diagram is
the model's control panel. A box opens in place (its parts, laid out
together inside its outline, its own systems still boxed), or is drawn alone: its parts, and
what it reaches outside as terminals at its edge, each naming the system it is in. A system alone
at its level starts open; the others start as boxes.

## 5. Stocks

What accumulates. Real, measured, trusted.

```yaml
stocks:
  inbox:
    unit: files
    limit: 10000                       # optional: where it physically fails
    system: intake                     # optional
    description: files waiting to be processed
    sensors:                           # zero or more, keyed by name
      count:
        run: ls inbox | wc -l
        every: 5s
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `unit` | string | none | Its unit. Flows and sensors on it must use the same unit |
| `limit` | number | none | The physical limit: a full disk, a queue's capacity. Used to estimate time to failure |
| `initial` | number | none | A starting value, for simulation only |
| `system` | name | the file's default | The group it belongs to |
| `description` | string | none | |
| `sensors` | map of sensors | none | How it is measured (section 6) |
| `sensor` | sensor | none | Shorthand for a single sensor named `main` |

A stock with no sensor cannot be judged: any goal on it is reported (section 12).

## 5a. Items

What the work is made of, one thing at a time: a ticket, a pull request, a deploy, a customer's
order. An item is not written in the model; it is every event about one id, replayed in order.
Its id names it the way the system it lives in does, with a `/` in it: `ticket/12`,
`github/pull_request/4231`. (ergostat's own events are about the model's parts, whose names never
have a `/`; the two never mix.) An event about an item comes from a block's output
(`{"event": "pr.merged", "item": "github/pull_request/4231", "data": {...}}`), from
`ergostat event --add`, or from an agent over MCP (`record_event`).

A kind of item says which ids are that kind, and the states they move through:

```yaml
items:
  pr:
    id: github/pull_request/*        # a glob over ids
    states: [open, review, merged, closed]
    on:                              # event type: the state it moves the item to
      pr.review-asked: review
      pr.merged: merged
      pr.closed: closed
    show: [title, author]            # fields worth a column on the Items page
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `id` | glob with a `/` | required | Which ids are this kind. The first kind that matches an id is its kind |
| `states` | list of names | none | The states, in their usual order; a new item starts in the first |
| `on` | map of event type → state | none | Which events move an item, and where to |
| `show` | list of field names | none | Columns for the Items page and `ergostat item` |
| `formats` | map of field → format | by extension | How a file a field names is shown: `image`, `markdown`, `code`, `text`, `json`, or `claude-session` (a Claude Code transcript, as the conversation) |
| `system`, `description` | | | |

**Folding.** An item's fields are its events' `data`, merged in order (the latest value of each
field wins). It arrives in the first state (a move from nowhere, so a flow can count arrivals
with `entering:`), and stays there until an event its kind maps moves it; every move is kept
(from, to, when, by which event), so how long it spent in each state is known. An item no
kind matches is still shown, with its fields and no state.

A field whose value is `file:PATH` names a file in the project (a picture a program made, a report,
an agent's transcript): the page shows it where the item is shown, as what it is (`formats`, or its
extension: an image as an image, Markdown rendered, code highlighted, a Claude Code transcript as the
conversation, re-read while it grows; raw HTML in Markdown is shown as text, never run), and serves
only files inside the project and its state directory. A file is kept apart from the record: the
record holds what happened, the file what was said.

Items are counted by sensors (section 6): a stock may be the number of items in some states, and
a flow the rate at which items enter or leave one. The record is then the instrument: what is
counted is what the events say, so a stock counted from items is only as true as the events
reporting them.

## 6. Sensors

An instrument: it measures one stock or one flow, and nothing else. It never decides or acts. It
is written inside the stock or flow it measures. Exactly one of `run`, `query`, `manual` or
`items`:

```yaml
sensors:
  count:
    run: ls inbox | wc -l
    every: 5s
  depth:
    query:
      source: prom
      promql: 'sum(queue_depth{app="checkout"})'
    every: 30s
  eyes:
    manual: true                 # a person records readings: ergostat sensor inbox.eyes --read 12
```

Counting items (section 5a), on a stock and on a flow:

```yaml
stocks:
  in-review:
    unit: prs
    sensor:
      items: pr
      state: review              # one state, or a list: [open, review]
      where:                     # optional: only items whose fields match
        label: bug
      every: 30s
flows:
  merging:
    from: in-review
    sensor:
      items: pr
      entering: merged           # or leaving: review
      over: 1h                   # the rate per hour over this window (default 1h)
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `run` | command | | A command whose output is the reading: a bare number, or JSON `{"value": n}` |
| `query` | map | | A query against a source (section 11): `source` and the source's own fields |
| `manual` | bool | | Readings recorded by a person |
| `items` | item kind | | Counted from the record: on a stock, the items in `state` (any state when left out); on a flow, the items `entering` or `leaving` a state per hour, over `over` |
| `state` | state or list | any | On a stock: which states count |
| `measure` | `count` or `oldest` | `count` | On a stock: how many, or the hours the oldest of them has been in its state |
| `entering`, `leaving` | state | | On a flow: exactly one; the move it counts |
| `over` | duration | `1h` | On a flow: the window the rate is taken over |
| `where` | map of field → value (or list) | | Only items whose fields match |
| `every` | duration | `1m` | How often it reads (`run`, `query`) |
| `cron` | cron expression | | Instead of `every` |
| `timeout` | duration | `30s` | |
| `parse` | regex with one group | | Takes the number from a line of text |
| `unit` | string | the stock's | Must equal the stock's (or the flow's rate unit) |

On a flow, a sensor's reading is a rate per hour.

## 7. Flows

What changes stocks: into one, out of one, or from one to another. Leaving out `from` or `to`
means outside the system (at least one is required). A flow is passive: it says which stocks it
connects, never what moves it.

```yaml
flows:
  arrivals:
    to: inbox
  processed:
    from: inbox
    to: outbox
  time-passing:
    to: report-age
    rate: 3600                   # a known, declared rate per hour
  churn:
    to: stale-docs
    sensor:                      # a measured rate
      run: ./churn.sh
      every: 5m
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `from`, `to` | stock name | outside | The stocks it drains and fills |
| `unit` | string | the stocks' | Must equal theirs |
| `rate` | number | none | A known, declared rate per hour |
| `sensors` / `sensor` | | none | Measurements of its rate |
| `driven-by` | flow or stock references | none | What its rate follows: an influence from elsewhere in the system (see below) |
| `system`, `description` | | | |

**`driven-by`: an influence, not a pipe.** Some flows are moved by nothing in the model, yet follow
something that is: a deploy (`flow.deployed`) is what fixes the product's broken features
(`flow.fixed`), though nothing pipes one into the other. `driven-by: [flow.deployed]` says so. It
is a claim about how the system works, drawn as a dashed arrow; nothing checks it against the
record yet. It also lets a loop close the long way (section 12).
It never says who moves the flow.

What sets a flow is the block whose `out` names it (at most one). Seen from a goal's loop:

- a flow set by a block that the loop's controller commands is that loop's **valve**;
- any other flow on the goal's stock is a **disturbance** to that loop: set by nothing in the
  model (its rate declared, measured, or estimated from what the stock does that the other flows
  do not explain), by an `external` block (something known, not run by ergostat), or by a block
  no controller of this loop commands.

## 7a. Variables

What is measured or set but does not accumulate: a score, a ratio, an age, a setting. Nothing
flows into a variable, so it is not a stock (system dynamics calls it an auxiliary). In a loop it is
either the **process variable**, measured, which a goal holds, or the **manipulated variable**, a
knob a block sets, which the loop turns.

```yaml
variables:
  quality:
    unit: ssim
    description: how close the compressed images look to the originals
    sensor:
      run: python3 world/read.py quality
      every: 10s
    driven-by: variable.quality-setting       # what it follows
  quality-setting:
    unit: jpeg-q
    description: the encoder's quality, which the tuner sets
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `unit`, `system`, `description` | | | |
| `sensors` / `sensor` | | none | How it is measured (section 6), as a stock is |
| `driven-by` | references | none | What it follows (flows, stocks, variables): an influence, as on a flow |

A block sets a variable by naming it in `out:` (`out: variable.quality-setting`) and printing the
value (`{"out": "variable.quality-setting", "value": 82}`, or a bare number); what it set is the
variable's reading, as if a sensor named `set` had read it, and is recorded as `variable.set`. One
block sets a variable. A goal may be about a variable (`variable: quality`), and its loop closes
when what the controller sets reaches it: directly, or through what it drives.

A stock no flow fills or drains is reported (`stock-without-flows`): it is probably a variable.

## 8. Goals

What we want. Each goal is about exactly one stock (its level) or one flow (its rate).

```yaml
goals:
  inbox-short:
    stock: inbox
    hold: "<= 20"
    tolerance: 5
  disk-headroom:
    stock: disk
    hold: "<= 80"
    critical: true
    owner: platform
  low-errors:
    flow: errors                 # a goal on a rate
    hold: "<= 1"
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `stock`, `flow` or `variable` | name | required, exactly one | What it is about: a stock's level, a flow's rate, or a variable's value |
| `hold` | setpoint | required | The setpoint |
| `tolerance` | number | 0 | Hysteresis for the status: off past the setpoint by more than this; holding again only back within the setpoint (for `==`, within half of it) |
| `critical` | bool | false | It guards against a cascade or an accumulating failure: watched for decay |
| `owner` | string | none | Who answers for it |
| `system`, `description` | | | |

A goal exists whether or not anything serves it. A goal nothing serves is **missing feedback**.

## 9. Blocks

A block is a function: inputs to outputs. Blocks are the information layer: system dynamics'
converters and control engineering's function blocks. Every controller, every actuator, and every
piece of logic between them is a block.

```yaml
blocks:
  keep-short:
    type: onoff
    goal: inbox-short            # on while the goal is off ...
    until: "<= 15"               # ... until the stock is back to here
    out: block.worker            # commands the worker

  worker:
    type: program
    run: ./process.sh
    in: block.keep-short         # runs while commanded
    out: flow.processed          # reports what it moved along this flow
    max: 25                      # the most one run may move
```

Common keys:

| Key | Type | Meaning |
|---|---|---|
| `type` | block type | What it computes (below) |
| `in` | reference, list, or map of port → reference | Its inputs |
| `out` | reference, list, or map of port → reference | Where its outputs go: a flow (it sets that flow), another block (it commands it), or a goal's setpoint (cascade) |
| `role` | `controller`, `actuator`, `logic` | Optional label, for drawing and checks. Derived when left out |
| `system`, `description` | | |

Every block has an output. A block with none has no visible effect: either it does nothing worth
modelling, or the flow it changes is missing from the model; `check` reports it.

### 9.1 How blocks run

- **Built-in blocks** (9.2) are executed by ergostat itself, on every reading of their inputs:
  no program, no machine. They are how ergostat closes loops by itself.
- **Machine blocks** (9.3) run a program, an AI prompt or a request to a person. They run:
  - when an input commands them (the input becomes nonzero, or a new command arrives); or
  - on their own schedule (`every`, `cron`), when nothing commands them: an open loop.

  A machine block never runs twice at once. A command that arrives while it is running is held,
  not queued (anti-windup): the latest command is used when it finishes. Without an `agent`, a
  machine block runs locally, launched by ergostat.
- **External blocks** (`type: external`) are performed by something ergostat does not run (an
  autoscaler, a Kubernetes controller, a team). They are declared for the structure: their
  inputs and outputs are what that thing reads and moves, judged by the stocks' and flows'
  sensors.

A machine block receives on standard input (or, for `ai`, in its prompt):

```json
{"block": "worker", "command": {"amount": 12, "from": "keep-short"},
 "inputs": {"stock.inbox": 32, "goal.inbox-short.error": -12},
 "goals": {"inbox-short": {"hold": "<= 20", "value": 32, "error": -12, "status": "off"}},
 "trigger": "command"}
```

and reports on standard output, one JSON line per output, or a bare number when it has a single
output:

```json
{"out": "flow.processed", "moved": 12}
{"out": "block.writer", "command": {"amount": 3, "item": "install.md"}}
{"decision": "12 waiting: process them", "why": "over the goal by 12"}
```

ergostat records what was **commanded** and what was **moved**: the gap is the direct evidence of
saturation.

### 9.2 Built-in block types

A first set, kept small:

| Type | Inputs | Output | Parameters |
|---|---|---|---|
| `onoff` | a goal | 1 while it should act, else 0 | `goal`, `until` (the release point: hysteresis), `min-on`, `min-off` |
| `compare` | one signal | 1 or 0 | `above` or `below`, `back-below` / `back-above` |
| `proportional` | a goal | an amount: `gain × error`, clamped | `goal`, `gain`, `min`, `max` |
| `limit` | one signal | the signal, clamped | `min`, `max`, `rate` (most change per hour) |
| `delay` | one signal | the signal, later | `delay` (a duration) |
| `schedule` | none (time) | a value by time of day or week | `table`: times to values (a lookup on the clock) |
| `lookup` | one signal | a value from a table | `table`: points, linear between them |
| `select` | several | the minimum, maximum, or the first nonzero | `pick: min`, `max` or `first` |
| `expr` | several | an arithmetic expression of them | `expr: a * 2 + b`, with `in` as a map naming them |
| `timer` | one signal | 1 once it has been nonzero this long | `after` |
| `counter` | one signal | how many times it became nonzero | `reset` (a duration) |
| `alarm` | one signal | raises a finding while out of bounds | `above`, `below`, `for` |

More (filters, rate of change, latches) can be added when a case needs them.

### 9.3 Machine block types

| Type | What it runs | Key fields |
|---|---|---|
| `program` | a shell command | `run`, `parse` |
| `ai` | a prompt, given to a model | `prompt` (text or a file), `model` (when it has no agent), `run` (an optional wrapper command) |
| `person` | a request to a person | `ask` (what they are asked to do); they report with `ergostat block NAME --done ...` |
| `external` | nothing: observed only | none |

Common to machine blocks: `agent` (optional: the shared machine it runs on, section 10), `max`
and `min` (limits on one run's amount), `timeout`, `every`/`cron` (its schedule when nothing commands it; when something does, `every`
is the least time between runs),
`mode` (`auto`, or `advise`: its commands wait for a person to approve).

**A machine block may name its goal.** `goal: inbox-short` (and optionally `until:`) on a
`program`, `ai` or `person` block means "run while this goal is off, until it is back to `until`
(or holding)". It is the commonest loop there is ("when the disk is over 80%, clean it"), written
in one block: ergostat puts an `onoff` block in front of it, named `keep-<goal>` (one per goal
and release point, shared by every block that names it), and draws and runs it like any other.
`ergostat block` lists it as implied. *Decided* (question 1).

```yaml
blocks:
  worker:
    type: program
    goal: inbox-short            # runs while the goal is off ...
    until: "<= 15"               # ... until the inbox is back to 15
    run: ./process.sh
    out: flow.processed
```

**How a commanded block runs.** While its command is nonzero it runs, once per fresh reading:
after each run it waits for a new reading of the system before running again, so it never
outruns its sensors. `every` on a commanded block paces it: it runs at most that often while
commanded (a worker pool that is always commanded would otherwise run back to back). When it moves a flow, the sensors of that flow's stocks read at once. The
command it gets is clamped to its `max` (and `min`); `block.commanded` records both the clamped
amount and, when they differ, what was asked.

**Reading a machine block's output.** A bare number goes to its single output (a flow: what it
moved; a block: a command; a goal: a setpoint). JSON lines may also be `{"moved": n}` without
`out` when it moves one flow, and `{"event": "backup.verified", "item": "backup/nightly"}` for
anything else that happened (an event about an item, section 5a; `data` holds its fields). Lines that are not JSON go to its log (`logs/<block>.log` in the state
directory). Its environment carries `ERGOSTAT_BLOCK`, `ERGOSTAT_COMMAND` (the amount),
`ERGOSTAT_STATE_DIR`, and `ERGOSTAT_CMD`, the command that runs this ergostat on this project
(`$ERGOSTAT_CMD item --kind ticket --state open --json`, `$ERGOSTAT_CMD event --add ...`), for a
block, or the AI agent it starts, to read and record items while it works. An `ai` block without `run` is given to `claude -p` (or `$ERGOSTAT_AI`),
with its prompt, the JSON above, and how to answer.

### 9.4 Roles

Roles are derived (or labelled with `role:`):

- a block whose output is a flow is an **actuator** (the flow's valve);
- a block whose output commands another block, or sets a goal's setpoint, and that reads a goal
  or a stock, is a **controller**;
- anything else is **logic**.

Sensors are not blocks: they are always inside a stock or flow. At most one block may output to a
given flow.

## 10. Agents

A machine shared by several blocks. Declare one only to say something true across them; whatever
concerns one block alone belongs on the block.

```yaml
agents:
  claude:
    kind: ai
    model: claude-opus-5-5
    at-once: 2                   # the blocks on it share this
    cost: 0.02/run
  oncall:
    kind: person
  hpa:
    external: true               # ergostat only observes it
  build-box:
    host: build-box.internal
    at-once: 4
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `kind` | `person`, `ai`, `narrow-ai`, `decision`, `program`, `rule` | from its blocks | Its rung on the ladder, when it adds something to the blocks' types |
| `external` | bool | false | ergostat never runs it; it only observes what its blocks do |
| `at-once` | integer | 1 | How many of its blocks may run at the same time |
| `model` | string | none | For an AI machine: which model |
| `cost` | string | none | What a run costs, for budgets counted across its blocks |
| `host` | string | local | Where its commands run (local only at first) |
| `description` | string | none | |

What an agent is for:

- **shared limits**: blocks on one machine queue behind its `at-once`, and ergostat can show the
  machine as a bottleneck;
- **identity**: a named person, an on-call rotation, an AI allowance, an external system, whose
  work and response times are seen across every block it fills;
- **location**: a host, for every block sent there;
- **budgets**: cost counted across its blocks.

Which blocks an agent runs is looked up from the blocks' `agent:`.

## 11. Sources

Where existing measurements live. Read only.

```yaml
sources:
  prom:
    type: prometheus
    url: http://prometheus:9090
```

| `type` | Fields | A sensor's `query` |
|---|---|---|
| `prometheus` | `url` | `source` and `promql`: an instant query, which must return one series |
| `command` | none | (the same as `run`) |

More types (Datadog, CloudWatch, SQL) can follow the same shape.

## 12. What ergostat derives and checks

**Derived** (never written): valves and actuators, controllers, disturbances, errors, loops
(a goal, the sensors of what it is about, the blocks serving it, and the flows they set), the
stock-and-flow diagram, block diagrams, the wiring of agents.

**A loop that closes the long way.** When nothing a goal's controller commands moves a flow of the
goal's stock directly, the loop may still close through other stocks: the controller moves work
into a queue (it files tickets into a backlog), that queue's own goal and blocks work it off, and
what they move drives a flow of the first stock (`driven-by`). ergostat finds the shortest such
path, from the controller through blocks, flows, stocks and influences to a flow of the goal's
stock, and the loop closes along it (`explain` names each part). Its delay is the sum of every
queue along the way.

**Errors** (the model is refused until fixed; each names the file and line):

- a reference to something that does not exist, or of the wrong kind;
- a name defined twice;
- a flow with neither `from` nor `to`;
- a goal without exactly one of `stock` and `flow`, without `hold`, or with a setpoint that does
  not parse;
- a sensor with none or more than one of `run`, `query`, `manual`, `items`;
- an item kind whose `id` has no `/`, an `on` naming a state not in `states`, or a sensor counting
  a kind or state that does not exist (or `state`/`measure` on a flow, `entering`/`leaving`/`over`
  on a stock);
- two blocks outputting to the same flow;
- a `run`, `prompt` or `ask` on an external block, or a built-in block with an `agent`;
- a block whose agent cannot run its type (an `ai` block on an agent of kind `person`);
- units that disagree between a flow and its stocks, or a sensor and what it measures;
- a cycle of built-in blocks with no delay (an algebraic loop).

**Findings** (reported, not errors):

- **missing feedback**: a goal no block serves;
- **unjudgeable goal**: a goal on something with no sensor;
- **heading for a limit**: a stock with a `limit`, growing, and no goal: time to failure;
- **no visible effect**: a block with no output;
- **acting on its own**: an actuator nothing commands (an open loop);
- **competing commands**: two controllers commanding one block;
- **its own disturbance**: a controller that also adds to the stock it holds;
- **critical goal decaying**: answering more slowly, saturating more often, its machine changed.

## 13. Examples

### First loop: an inbox kept short (ergostat closes the loop)

```yaml
name: first-loop

stocks:
  inbox:
    unit: files
    sensor:
      run: mkdir -p inbox; ls inbox | wc -l
      every: 5s

flows:
  arrivals:
    to: inbox
  processed:
    from: inbox

goals:
  inbox-short:
    stock: inbox
    hold: "<= 20"
    tolerance: 5

blocks:
  worker:
    type: program
    goal: inbox-short
    until: "<= 15"
    run: ls inbox | head -5 > .batch; (cd inbox && xargs rm -f < ../.batch); wc -l < .batch
    out: flow.processed

  drop:
    type: program
    run: mkdir -p inbox; for i in 1 2 3; do mktemp inbox/job.XXXXXX > /dev/null; done; echo 3
    every: 5s
    out: flow.arrivals
```

The threshold lives once, in the goal. The worker only works: ergostat runs it while the goal is
off (through the implied `keep-inbox-short`), once per reading, until the inbox is back to 15.
Written out, the implied block is an `onoff` with `goal: inbox-short`, `until: "<= 15"` and
`out: block.worker`; the long form is still valid, and is needed when the controller is something
other than on/off. No machine is shared, so there is
no `agents:` section.

### Production: observed autoscaling, a cron job ergostat now controls, a missing loop

```yaml
name: checkout

sources:
  prom:
    type: prometheus
    url: http://prometheus:9090

stocks:
  queue:
    unit: jobs
    sensor:
      query:
        source: prom
        promql: 'sum(queue_depth{app="checkout"})'
      every: 30s
  logs:
    unit: MB
    sensor:
      run: du -sm /var/log/app | cut -f1
      every: 1m
  disk:
    unit: "%"
    limit: 100
    sensor:
      query:
        source: prom
        promql: 'node_filesystem_used_pct{mount="/data"}'
      every: 1m

flows:
  requests:
    to: queue
  served:
    from: queue
  logging:
    to: logs
  rotated:
    from: logs
  writes:
    to: disk

goals:
  queue-short:
    stock: queue
    hold: "<= 500"
    critical: true
  logs-small:
    stock: logs
    hold: "<= 500"
  disk-headroom:                 # nothing serves it: missing feedback
    stock: disk
    hold: "<= 80"
    critical: true

blocks:
  autoscaling:
    type: external
    agent: hpa
    in: goal.queue-short
    out: flow.served

  rotate-when-big:
    type: onoff
    goal: logs-small
    until: "<= 300"
    out: block.rotate

  rotate:
    type: program
    run: logrotate -f /etc/logrotate.d/app
    in: block.rotate-when-big
    out: flow.rotated

agents:
  hpa:
    external: true
```

### Triage: an AI controller serving three goals

```yaml
name: triage

stocks:
  tickets:
    unit: tickets
    sensor:
      run: ./count-tickets.sh
      every: 1m
  alerts:
    unit: alerts
    sensor:
      run: ./count-alerts.sh
      every: 30s
  spend:
    unit: USD
    sensor:
      run: ./spend-this-hour.sh
      every: 1m

flows:
  filed:
    to: tickets
  fired:
    to: alerts
  resolved:
    from: tickets
  acked:
    from: alerts
  used:
    to: spend

goals:
  few-tickets:
    stock: tickets
    hold: "<= 10"
  alerts-acked:
    stock: alerts
    hold: "<= 2"
    critical: true
  within-budget:
    stock: spend
    hold: "<= 20"
    critical: true

blocks:
  triage:
    type: ai
    agent: claude
    prompt: prompts/triage.md
    in: [goal.few-tickets.error, goal.alerts-acked.error, goal.within-budget.error]
    out:
      tickets: block.ticket-worker
      alerts: block.alert-worker
    every: 2m

  ticket-worker:
    type: ai
    agent: claude
    prompt: prompts/resolve.md
    in: block.triage.tickets
    out: flow.resolved
    max: 5

  alert-worker:
    type: program
    run: ./ack-duplicates.sh
    in: block.triage.alerts
    out: flow.acked

agents:
  claude:
    kind: ai
    model: claude-opus-5-5
    at-once: 2                   # triage and the ticket worker share it
```

### Cascade: an outer goal sets an inner one

```yaml
blocks:
  backlog-to-workers:            # the outer loop: how many workers the backlog needs
    type: expr
    in:
      backlog: stock.backlog
    expr: min(50, max(5, backlog / 20))
    out: goal.enough-workers     # sets the inner goal's setpoint
```

## 14. From the TOML format

| TOML | YAML |
|---|---|
| `[[stock]]` | `stocks:` |
| `[[sensor]]` with `agent` | a sensor inside its stock (`run:` is the agent's command for that sensor) |
| `[[flow]]` | `flows:` |
| `[[disturbance]]` | a flow no block sets (its `rate` as before); its `agent` becomes a block (often `external`) whose `out` is the flow |
| `[[controller]]` | a goal (its `holds` and `setpoint`) and a block serving it; `open_loop` becomes a machine block on a schedule with no controller |
| `[[valve]]` with `agent` | a machine block whose `out` is the flow |
| `[[agent]]` | its `run`, `every`, `parse` move onto the blocks it ran; an `agents:` entry only when it is shared, external, a person, or has limits |
| `[[system]]` | `systems:` |

`ergostat convert` writes an existing `ergostat.toml` as `ergostat.yaml` (`--stdout` to look first).
A controller that held a stock through a valve becomes a goal, and the valve's block names it
(`goal:`), so the loop that the TOML only watched is closed. What needs a person (a program that
measured and acted in one run) is listed at the top of the file.

## 15. Open questions

1. *Decided:* `goal:` stays on `onoff` and `proportional`, and a machine block may name its goal
   too (section 9.3).
2. Should a sensor be allowed to run on a remote host (`host:`), or only through sources?
3. Arbitration when two controllers command one block. *For now:* the largest command wins, and
   `check` reports the competing commands; a `select` in front says otherwise (`pick: min`,
   `first`). A key on the block (`arbitrate: latest`, `priority`) is still open.
4. *Decided:* a person reports with `ergostat block NAME --done N` (or the MCP tool
   `report_done`); ergostat records `person.asked` when the command rises, and one not answered
   within an hour is a finding (`not-answering`). Whether the hour should be a key on the block is
   open.
5. The built-in set: is it the right first twelve?
