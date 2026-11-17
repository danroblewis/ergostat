# The ergostat model: specification (draft)

This specifies the configuration format: the files people and AI agents write to describe a
system. It replaces the TOML format. The ideas behind it are in `docs/CONCEPTS.md`, the names
come from `docs/vocabulary.md`, and `schema/ergostat.schema.json` is the machine-checkable form
of this document.

**Status: draft for review, implemented.** `ergostat check`, `convert` and `run` follow this document
(`ergostat/spec/`). Where building it settled a question, the decision is marked *Decided*.

## 1. Principles

1. **Four kinds of thing are written, and more when they say something.** Stocks, flows, goals
   and blocks; auxiliaries, for quantities without memory; parameters, the numbers equations name
   (section 7b); and agents, only for machines shared
   by several blocks. (Kinds of item, section 5a, say how to read the record, not what the system
   is.) Valves, controllers, disturbances, errors, loops and diagrams are worked out from them,
   never declared.
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

## 1a. One model, two perspectives

There is one model, and two ways of looking at it, each true to its own discipline:

- **System dynamics** (what is): stocks, flows, auxiliaries and the influences between them, and
  the feedback loops they make, each reinforcing (R) or balancing (B). For product managers and
  sales; the language of Sterman's *Business Dynamics*, Vensim and Stella.
- **Control** (what is controlled): goals, sensors, controllers and actuators, the error each
  controller acts on, and the loop it closes. For engineers; classical block diagrams.

Neither is derived from the other: both are read from the same stocks, flows, auxiliaries, goals
and blocks. A kind of quantity (stock, auxiliary) belongs to the model; a role in a loop (process
variable, manipulated variable, controller, actuator) belongs to the control view, and is worked
out, never written.

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
sections (a stock and a goal both called `inbox`), but it is discouraged. Parameters (section 7b) are
named by their bare name in equations, so a parameter may not take a function's name (`min`, `delay1`).

**References** point at a thing, or at one port of it:

| Reference | Means |
|---|---|
| `stock.inbox` | The stock's measured level (its current best reading) |
| `stock.inbox.count` | The reading of one of its sensors, `count` |
| `auxiliary.quality` | An auxiliary's value (as an output: what a block sets it to) |
| `flow.processed` | As an input: the flow's measured rate. As an output: what a block moves along this flow |
| `goal.inbox-short` | The goal's setpoint (r) |
| `goal.inbox-short.error` | The goal's error, e = r − y |
| `goal.inbox-short.off` | 1 while the goal is off, 0 while it holds |
| `block.decide` | A block's output (its only output, or its output named `out`) |
| `block.decide.urgent` | A block's output port `urgent` |

A `driven-by` reference may carry a sign, its **polarity**: `+stock.improvements` (it rises when
that rises), `-auxiliary.price` (it falls when that rises). Unsigned means not known. No other
reference carries a sign.

*Renamed:* `variable.x` is the old spelling of `auxiliary.x`, and `variables:` of `auxiliaries:`;
both are still read, with a `deprecated-name` finding saying what to rename.

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
parameters:                     # optional: the numbers equations name (section 7b)
  ...
auxiliaries:                    # optional: quantities without memory (section 7a)
  ...
goals:
  ...
blocks:
  ...
agents:                         # optional: machines shared by several blocks
  ...
loops:                          # optional: names for feedback loops (section 12a)
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
| `show` | stock, flow or auxiliary references | its goals' | The measures its box shows when it is drawn as one part: its control panel |

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

A quantity with memory: its value persists when nothing happens, and changes only through its
flows. What accumulates (a queue, a disk, a backlog), and also what is held at a level by equal
inflow and outflow, and a setting a controller steps (it stays where it was last moved: section
7a). Its reading may come from a script and may change suddenly; a sudden drop is a large outflow,
some process removing what was there. Real, measured, trusted.

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
| `cumulative` | bool | false | A running total that by its nature never drains (spent so far, kept so far): no outflow is missing, and `check` does not ask for one (**stock-without-outflow**) |
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
only files inside the project and its state directory, at `/file/PATH` (a path, so a Markdown file's
relative links open the files beside it: opened in the browser, a Markdown file is shown rendered). A file is kept apart from the record: the
record holds what happened, the file what was said.

Items are counted by sensors (section 6): a stock may be the number of items in some states, and
a flow the rate at which items enter or leave one. The record is then the instrument: what is
counted is what the events say, so a stock counted from items is only as true as the events
reporting them.

## 6. Sensors

An instrument: it measures one stock or one flow, and nothing else. It never decides or acts. It
is written inside the stock or flow it measures. Exactly one of `run`, `query`, `manual`, `items`
or `changes`:

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
| `changes` | `rises`, `falls` or `net` | | On a flow into or out of one stock: its rate from that stock's own successive readings, how much they rose (an inflow), fell (an outflow), or both, net, in the flow's direction (a `two-way` flow), per hour over `over` |
| `over` | duration | `1h` | On a flow: the window the rate is taken over |
| `averages` | duration | none | On a flow's `run`, `query` or `manual` sensor: its reading is the average rate over this window before it (a count of the last ten minutes, per hour: `averages: 10m`). The model's rate is read through the same window before it is compared (section 12b) |
| `where` | map of field → value (or list) | | Only items whose fields match |
| `every` | duration | `1m` | How often it reads (`run`, `query`) |
| `cron` | cron expression | | Instead of `every` |
| `timeout` | duration | `30s` | |
| `parse` | regex with one group | | Takes the number from a line of text |
| `unit` | string | the stock's | Must equal the stock's (or the flow's rate unit) |

On a flow, a sensor's reading is a rate per hour; on a `two-way` flow it may be negative (it ran
back).

`changes` measures a flow by what it did to its stock: a benchmark's score rising with a release
is its inflow, a sudden fall its outflow. It is how a stock read by a script gets measured flows
without a second instrument (the flows are then only as true as the stock's readings, and see only
the net change between two readings).

A `run` sensor may also print what it observed about items, one JSON line each, beside its number:
`{"event": "case.met", "item": "case/logo-3", "data": {...}}` (a benchmark that records each case
it measured). These are recorded as events from the sensor (`benchmark-score.main`) and fold into
the items like any other. An observation records what was seen, never a command: it must name an
item (an id with a `/`), may not use ergostat's own types, and a sensor has no outputs. A measured
value is shown as measured by its sensor; an auxiliary a block sets is shown as set by that block.

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
| `driven-by` | flow, stock or auxiliary references, each optionally signed | none | What its rate follows: an influence from elsewhere in the system (see below) |
| `two-way` | bool | false | It may run either way (system dynamics' biflow): a block may move it by a negative amount, and its sensor may read a negative rate |
| `system`, `description` | | | |

**`driven-by`: an influence, not a pipe.** Some flows are moved by nothing in the model, yet follow
something that is: a deploy (`flow.deployed`) is what fixes the product's broken features
(`flow.fixed`), though nothing pipes one into the other. `driven-by: [flow.deployed]` says so. It
is a claim about how the system works, drawn as a dashed arrow; nothing checks it against the
record yet. It also lets a loop close the long way (section 12).
It never says who moves the flow. Each reference may be signed (`+flow.deployed`,
`-stock.bugs-live`): the influence's polarity, used to find which feedback loops reinforce and which
balance (section 12a).

**A connector acts at once.** In system dynamics a link between two variables is instantaneous: a
flow driven by another flow says its rate now depends on the other's rate now. When the cause acts
over time (a flag ramped without review breaks something hours later, if at all), what the first
flow moves accumulates in a stock, and the second follows that stock: the delay is the stock
(`check` reports a flow driven by a flow as **rate-driven-by-rate**). Where the dependence really is
immediate (a release fixes what it fixes as it goes live; the next document is needed the moment the
last is approved), the link says so, written out:

```yaml
flows:
  fixes:
    from: bugs-live
    driven-by:
      - +stock.bugs-live                       # it takes a share of what is there
      - cause: +flow.deployed
        instant: true                          # as the release goes live: nothing between
        description: a release fixes what it fixes when it is deployed
```

| Key | Type | Meaning |
|---|---|---|
| `cause` | a reference, optionally signed | What it follows, as in the short form |
| `instant` | bool | The effect follows the cause in the same moment, with no stock between; `explain` says "at once" |
| `description` | string | |

A flow that follows a flow of something else (alerts following ramps) moves so many of its own units
for each of the other's: a **coflow** (Sterman, ch. 12). The ratio is an auxiliary
(`unit: alerts/ramp`, `exogenous: true` while it is not measured), and the flow is driven by both;
or, for an outflow, by the stock it takes from (`check`: **units-mismatch**).

**Polarity of structure.** A flow is + on the stock it fills and − on the stock it drains; a
two-way flow is the same, counted in its direction (from `from` to `to`).

**Two-way flows.** A flow runs one way: what a block moves along it is 0 or more, and a negative
amount is refused. `two-way: true` lets it run back: a setting a controller steps up and down, a
window of measurements whose level rises and falls as what it holds turns over.

What sets a flow is the block whose `out` names it (at most one). Seen from a goal's loop:

- a flow set by a block that the loop's controller commands is that loop's **valve**;
- any other flow on the goal's stock is a **disturbance** to that loop: set by nothing in the
  model (its rate declared, measured, or estimated from what the stock does that the other flows
  do not explain), by an `external` block (something known, not run by ergostat), or by a block
  no controller of this loop commands.

## 7a. Auxiliaries

A quantity without memory: determined at each moment by others, through an equation (written, section
7b, or else measured). System dynamics calls it an auxiliary (or converter). A ratio of two
stocks, a difference between two builds measured on the same images, a share that is a function of
the clock. Nothing flows into it, and it keeps nothing between moments.

Memory decides the kind, not how something is measured or what it is used for. What persists when
nothing happens and changes only through some process is a stock (section 5), even when it is a
setting, a score or a statistic over a window of what is served; what is a momentary function of
other things is an auxiliary. *Process variable* and *manipulated variable* are not kinds: they are
roles a part plays in a control loop (what its goal holds; what its controller turns), said by
`explain` and the page, never written.

```yaml
auxiliaries:
  quality-change:
    unit: ssim
    description: how much better the candidate looks than production, on the same images
    sensor:
      run: python3 world/read.py quality-change
      every: 8s
    driven-by: +stock.candidate-offset          # what it follows, and which way
  flat-share:
    unit: share
    exogenous: true                             # from outside the model: nothing in it drives it
    description: how much of the mix is flat images, a function of the clock
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `unit`, `system`, `description` | | | |
| `sensors` / `sensor` | | none | How it is measured (section 6), as a stock is |
| `driven-by` | references, each optionally signed | none | What it follows (flows, stocks, auxiliaries): an influence, as on a flow |
| `exogenous` | bool | false | An input from outside the model (system dynamics' exogenous input); it then has no `driven-by` |

A block may set an auxiliary by naming it in `out:` (`out: auxiliary.flat-share`) and printing its
whole value each run (`{"out": "auxiliary.flat-share", "value": 0.3}`, or a bare number); what it
set is the auxiliary's reading, as if a sensor named `set` had read it, and is recorded as
`auxiliary.set`. One block sets an auxiliary. *Decided:* this is kept only for what is genuinely
memoryless, a value the block states afresh from what it reads now (a proportional controller's
output, a schedule, the world's mix brought in from outside). A controller whose output is its
last output plus a step (integral action) keeps memory: what it turns is a stock, and it moves it
through a two-way flow (`out: flow.quality-steps`, `{"moved": -2.5}`).

```yaml
stocks:
  quality-setting:                              # a setting the tuner steps: a stock
    unit: q
    sensor:
      run: python3 world/read.py quality-setting
flows:
  quality-steps:
    to: quality-setting
    two-way: true
blocks:
  tuner:
    type: program
    run: python3 bin/tune.py                    # prints {"out": "flow.quality-steps", "moved": <the step>}
    in: goal.quality-held.error
    out: flow.quality-steps
```

A goal may be about an auxiliary (`auxiliary: quality-change`), and its loop closes when what the
controller moves reaches it: directly, or through what it drives (a stock the controller steps,
then the auxiliary or the flow that follows it).

A stock no flow fills or drains is reported (`stock-without-flows`): give it its flows, or, if it
has no memory, make it an auxiliary.

## 7b. Equations and parameters

A flow's rate and an auxiliary's value may be written as an **equation**, the way Vensim and Stella
write them, in the model's own names; the numbers it names are **parameters**. A stock needs none:
it is the integral of its flows, exactly. Without an equation a flow or an auxiliary is what its
sensor reads, or what the block that sets it says.

```yaml
parameters:
  workdays-per-hour:
    value: 60
    unit: workdays/h
  alerts-base:
    value: 1.2
    unit: alerts/workday
    estimate: true                              # fitted from the record (section 12b)
  alerts-per-outage:
    value: 4
    unit: alerts/outage
  window-time:
    value: 19.2s                                # a duration, read in hours
  effect-of-load:
    table: [[0, 1], [10, 0.5], [20, 0.2]]       # a lookup: linear between its points
  k: 0.45                                       # short for value: 0.45
flows:
  alerts-fired:
    to: alerts-to-draft
    driven-by: [{cause: +flow.outages-noticed, instant: true}]
    equation: workdays-per-hour * alerts-base + alerts-per-outage * flow.outages-noticed   # a coflow
  quality-turnover:
    to: quality
    two-way: true
    driven-by: [+auxiliary.batch-quality, -stock.quality]
    equation: (auxiliary.batch-quality - stock.quality) / window-time   # first-order smoothing
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `equation` | expression | none | On a flow: its rate per hour; on an auxiliary: its value. Not with `rate:` on the same flow |
| a parameter's `value` | number or duration | none (not known) | What it is believed to be; a duration (`40s`, `2h`) is read in hours, the model's time |
| `unit` | string | none | Its unit, products and quotients of words (`alerts/ramp/workday`, `1/h`); `share` and `1` are pure numbers. Time is counted in hours: a unit counting it in `s`, `min`, `d` or `week` is an error (*decided*: 30 with `unit: min` would be read as 30 hours), so a time is written as a duration and a rate per hour; a model's own clock (`workdays`, with `workdays-per-hour`) is a word like any other |
| `estimate` | bool | false | Fitted from the record (section 12b): the estimate is kept apart and proposed, never written here until it is accepted |
| `table` | points | none | A lookup, called like a function: `effect-of-load(stock.queue)` |
| `system`, `description` | | | |

**Expressions.** Numbers; parameters by their bare name; parts by reference (`stock.x`, `flow.x`,
`auxiliary.x`: a flow is its rate per hour); `+ - * / ^` and brackets; `MIN`, `MAX`, `ABS`, `EXP`,
`LN`, `SQRT`, `ZIDZ(a, b)` and `XIDZ(a, b, x)` (a / b, or 0, or x, where b is 0); and system dynamics' delays: `DELAY1(x, T)` and `DELAY3(x, T)`, material delays of
the first and third order (what goes in comes out after `T` on average, and nothing is lost), and
`SMOOTH(x, T)` and `SMOOTH3(x, T)`, information delays (exponential smoothing toward `x` over `T`).
Each delay keeps hidden stocks of its own, starting in equilibrium with its input. Names have
hyphens in them, so subtraction is written with spaces: `a - b`. Nothing that fails is hidden: a
division by 0 written with `/`, the logarithm or square root of a number out of range, a negative
number to a fractional power and an overflow are each taken as 0 and counted, and the run's notes
say which equation did it how often (write `ZIDZ(a, b)` where 0 is meant); a value past 10¹² is
clamped and makes the run not valid.

**Every number says where it comes from**, its **provenance**: *declared* (its value is written
here), *estimated* (fitted from the record, with how well, from how many points, and when: kept in
the state directory, section 12b), or *unknown* (no value yet). The page and `ergostat explain`
show each beside the equation; the replay uses only what is declared, so nothing estimated changes
the model until the owner accepts it.

**Checks.** Errors: an equation that does not read; a bare name that is not a parameter (with the
hint to write `a - b` when `a-b` was meant); a reference to a part that does not exist, or to the
part itself (what it was a moment ago is a stock); a flow with both `rate:` and `equation:`; an
`exogenous` auxiliary whose equation names parts of the model; equations that need each other at
once with no stock or delay between (an algebraic loop); a lookup used as a number. Findings:

- **equation-units**: where units are written, an equation must add like things and come out in
  its part's unit (a flow's per hour); a number written in it takes the unit it needs, and anything
  whose unit is not written is not checked;
- **equation-sign**: a `driven-by` written with a sign the equation contradicts. A link's polarity is
  the sign of the partial derivative (Sterman ch. 5.2), so each is worked out by finite differences
  across a range of operating points (every part at 0.25 to 50, the parameters at their values,
  each delay in equilibrium): the other sign wherever it was tried, or a sign that changes across
  the range, is said, since every loop drawn through the link would have the wrong polarity;
- **size-unknown**: a `driven-by` the equation does not use: the link is drawn, with its sign, and
  its size is not known (the equation says it has none);
- **equation-not-drawn**: a part the equation uses that `driven-by` does not name, so the diagram
  draws no connector for it and no loop runs through it;
- **parameter-unknown**: a parameter with no value that is not to be estimated; equations using it
  are left out of the replay (their parts are taken as measured);
- **parameter-unused**: a parameter no equation uses.

## 8. Goals

What we want. Each goal is about exactly one stock (its level), one flow (its rate) or one auxiliary
(its value).

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
| `stock`, `flow` or `auxiliary` | name | required, exactly one | What it is about: a stock's level, a flow's rate, or an auxiliary's value (`variable:`, its old name, is still read) |
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
| `in` | reference, list, or map of port → reference | Its inputs. On a machine block, a stock, flow or auxiliary read may carry its sign, as a `driven-by` does: `+stock.x` (it does more as x rises), `-stock.x` (less); see §12a |
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

An integral controller closes the same way, through one stock: it steps a setting (a two-way flow
into a stock that keeps its value between steps), and what its goal holds is driven by that
setting. `explain` says so: the setting is the loop's manipulated variable, and the loop settles
where the error is 0.

**Errors** (the model is refused until fixed; each names the file and line):

- a reference to something that does not exist, or of the wrong kind;
- a name defined twice;
- a flow with neither `from` nor `to`;
- a goal without exactly one of `stock`, `flow` and `auxiliary`, without `hold`, or with a
  setpoint that does not parse;
- a sensor with none or more than one of `run`, `query`, `manual`, `items`, `changes` (or
  `changes` on a flow between two stocks, `rises` on an outflow, `falls` on an inflow, `net` on a
  one-way flow);
- a negative amount moved along a flow that is not `two-way` (refused when the block reports it);
- an `exogenous` auxiliary that is also `driven-by` something;
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
- **critical goal decaying**: answering more slowly, saturating more often, its machine changed;
- **deprecated name**: `variables:`, `variable.x` or a goal's `variable:`, still read; rename to
  `auxiliaries:`, `auxiliary.x`, `auxiliary:`.

**Structure** (findings, the tests system dynamics makes of a model's structure before its
behaviour: Sterman, *Business Dynamics*, ch. 21, structure assessment, dimensional consistency and
extreme conditions; each says its fix and the YAML that writes it; `docs/MODELLING.md` explains
them for someone new to system dynamics):

- **rate-driven-by-rate**: a flow `driven-by` another flow. A connector acts at once, so a cause
  acting over time goes through a stock: what the first moves accumulates, and the second follows
  that stock. Silenced by `instant: true` on the link (section 7) where it really is immediate;
- **stock-without-outflow**: flows fill a stock and none drains it (no outflow, no two-way flow),
  so in the model it can only grow. Give it the outflow, or say it is a running total
  (`cumulative: true`, section 5);
- **units-mismatch**: a flow driven by a flow in another unit (both declared; counts compared with
  any per-hour taken off; shares, percentages and compound units left alone), with no auxiliary
  among its causes to convert, and not driven by the stock it drains. Name the ratio as an auxiliary;
- **outflow-ignores-stock**: an outflow nothing sets, `driven-by` things that are not its stock (nor
  an auxiliary driven by it): with the stock empty it would still run and take it below zero (the
  extreme-conditions test). Drive it from the stock as well;
- **auxiliary-without-causes**: an auxiliary nothing drives, nothing sets and not `exogenous`: the
  model cannot say why it changes. Name its causes, or mark it `exogenous: true`.

## 12a. Feedback loops (system dynamics)

Worked out, never written: every cycle of cause and effect through stocks, flows, auxiliaries,
goals and blocks (`ergostat/spec/causal.py`; `explain` lists them, and the graph API gives each
one's members, polarity and name). Each link has a sign:

| Link | Sign |
|---|---|
| a flow → the stock it fills / drains | + / − |
| a `driven-by` | as written; unsigned: not known |
| what a goal is about → the goal's error, e = r − y | − |
| a goal → a block reading its error | + (a controller acts on its error: that is what serving a goal means) |
| a goal → a block acting while it is off (`.off`, an `onoff` or `proportional` on it, the goal itself) | + for a floor (`>=`), − for a ceiling (`<=`), not known for `==` |
| a block → the block it commands | + for a machine block; a built-in's own sign (`compare below` and a falling `lookup` −, `expr` not known) |
| a block → what it moves, sets or commands (a setpoint it sets raises the error) | + |
| a stock, flow or auxiliary → a machine block that reads it | as written on the read (`in: +stock.x`); unsigned, as the gap of a goal the block serves that is about that very quantity says (+ for a ceiling, − for a floor, not known for `==`), else not known |

A block **serves** the goals it names (`goal:`, or reading `goal.x`); one that names none serves the
goals whose loop closes with it as a controller or an actuator (section 12). So a block reading a
stock its own goal keeps down acts the more, the higher the stock: `rollout` reading `failures`
for `no-failures ≤ 0` is +. A link whose sign is still not known is reported by `check`
(**unsigned-link**, one finding per block or flow, naming each read or `driven-by`): every loop
through it is of unknown polarity until it is signed. An exogenous input is in no loop, so its
unsigned influence is not reported.

A loop is **R** (reinforcing) when the product of its signs is +, **B** (balancing) when −, and of
unknown polarity when any sign along it is not known. A goal-seeking loop whose links are all known
comes out balancing, as it should; one that comes out reinforcing is a controller pushing the wrong
way.

**Names.** A loop's name is how system dynamics people talk about it ("rework", "word of mouth"),
so the model may give it one:

```yaml
loops:
  rework:                        # the shortest loop through every part named
    through: [flow.rejected, stock.backlog]
    description: rejected work goes back to the backlog
  quality:                       # or the shortest loop that seeks this goal
    goal: quality-held
```

| Key | Type | Meaning |
|---|---|---|
| `through` | list of references | The parts it runs through (any of them, in any order); the shortest loop through all of them takes the name |
| `goal` | goal name | The shortest loop through this goal takes the name |
| `description` | | |

One of `through` and `goal`; a reference that does not exist is an error. A loop the model does
not name takes its **head**: the goal it seeks (the first, by name, when it seeks several), else the
first stock it runs through. The shortest loop with a head takes it bare (`backlog-clear`); every
other loop with that head is the head "via" the fewest of its members no sibling loop has, flows
first, then stocks, auxiliaries, goals and blocks (`backlog-clear via rejected`). Never numbered,
never a list of everything in it.

**Drawn** (the dynamics view, `ergostat/dynamics.py`): each loop is labelled as Sterman numbers them,
R1, B1 (the shortest first, the ones the model names before others of their length), with its name
beneath. Only loops of known polarity are marked on the diagram, each inside the loop as drawn; the
others are one entry beside it, "+N of unknown polarity", that opens to list them. A goal is drawn
as a desired level (a value: `desired backlog = 0`) and the discrepancy that drives the correction +:
for a ceiling the **excess** (actual − desired), for a floor or a level held the **gap** (desired −
actual); when the decisions serving it switch (on while backlog > 0, off once it is ≤ 0), the panel
says so. A line between two parts both drawn, in open systems or not, is drawn as itself; only
where its other end is not on the canvas is it cut: a connector out of a closed module into an
open system comes from a shadow variable `<x>` inside the receiving system, and a shadow is an
input only, so a connector out to a part not drawn ends at a stub naming what it drives, and a
pipe out ends in a cloud with the part beyond named under it. An
open system is a sector, a light tint with its name at the top left; a closed one is a module, its
connection points named on its edge. The view's panels use system dynamics' words only. A flow's
valve (the bowtie) opens as the **valve**: the rate of the flow, its inputs (the connectors into it,
each with its sign) and its equation: written (section 7b), drawn in MathML with each parameter's
value and provenance and any proposal for it, with Accept; else a constant declared (`rate:`), the
decision that sets it, or "not known yet: a declared cause with a sign, its size not estimated"
(and which causes act at once). An auxiliary's panel shows its equation the same way. The causes
strip draws the model's replay dashed over the measured line, and its projection past now dashed
and lighter (section 12b). Its pipe opens as the **flow**: what moves (its unit and
description), from which stock, to which.

## 12b. Replay, projection, fit and proposals

**What is compared** (`ergostat/numbers/observe.py`): the record on a grid of equal buckets, and how
each part's record was made, so the model can be read the same way (Oliva 2003: fit the model's
output to the data through the same aggregation; Ljung ch. 4: an output-error predictor includes
the measurement). A **level** (a stock, an auxiliary) is its last reading in each bucket, and is
compared with the model at that reading's moment. A **counted** flow (items entering or leaving a
state, a valve's openings, a stock's own changes) is the amounts at the times they moved: it drives
the replay as it happened, and an equation for it is compared bucket by bucket with what it moved,
the model's own integral over the same bucket on the other side. A flow **read** as a rate is its
readings' mean in each bucket, compared with the model's rate averaged over the window the sensor
says its readings average over (`averages:`). The fit and the estimates look at the **reference
window**, the last day of record at most, in buckets of at least ten seconds, whatever window the
page shows (*decided*: a fit that changed with the page's window was not a fit of the model).

**Replay** (`ergostat/numbers/simulate.py`): the model run over the record, as system dynamics
calibrates a model (Oliva 2003; Homer 2012, partial-model testing). Each stock starts at its first
reading, at that reading's moment, and is integrated from its flows; each flow and auxiliary with an
equation is worked out from it; every other input (a flow a block moves, a rate a sensor reads, an
auxiliary from outside) is driven by what was measured, a counted flow by what moved when it moved.
So a stock whose flows are all counted replays its own readings exactly, and the replay tests
exactly the equations the model writes. With no stock integrated, every input is as measured: the
**partial-model test** of each equation. **The step** follows the model's dynamics, never its units
(Sterman app. A): at each bucket, how fast each stock answers itself and the others (|∂net/∂stock|
by finite differences of the compiled equations at the operating point, bounded by Gershgorin's
circles), a step a quarter of the fastest; a delay whose stages (T/order) are faster is stepped
through each step in smaller steps of its own, so what leaves its stages is what its flow moves.
Past 256 steps a bucket a stock's own drain is integrated implicitly (stable, settled at once) and
the notes say so; a run that hit the clamp, or whose stocks drive each other faster than its step,
is not valid, and is neither fitted nor shown as a fit.

**Projection**: open loop (*decided*, until the blocks' laws are simulated): from the state now
(each stock the mean of its last few readings, each delay as the replay left it), the inputs held
where they were (or carried on along their recent trend), the controllers held, for a horizon of
three of the slowest time constant the replay met, within a twentieth and a quarter of the window.
What a flow a block sets moves (that flow, its stocks, and what follows from them) is left out of
the projection, and the chart says so.

**Fit** (`ergostat fit`, the Fit page), by Sterman's measures (*Business Dynamics* ch. 21;
"Appropriate summary statistics for evaluating the historical fit of system dynamics models",
1984): **R²** (the squared correlation: how much of the measured variation the replay moves with),
**MAPE** (the mean absolute error as a share of what was measured; where a reading is near 0 or
they cross it, the mean absolute error as a share of their mean or range instead), and **Theil's
inequality statistics**, which split the mean squared error into **U_M**, bias, **U_S**, unequal
variation and **U_C**, unequal covariation; they sum to 1, and a good fit's error is mostly U_C. A
large error (past a tenth of the readings' size) with U_M or U_S past 0.1 is said in words (runs
high, swings less than the record). Three tables: the **model fit**, the stocks an equation moves,
which alone make the total (R² and MAPE averaged, Theil's shares from each stock's squared error
over its own size) and its history; the **equations**, each with its inputs as measured (the
partial-model test, the sharpest test of one equation) and replayed; and **accounting**, the stocks
moved only by measured flows, which test no equation (their error is a measurement's or a missing
flow's: the residuals). A flow measured only by its stock's `changes:` is judged by its stock's
replay, not against its own differenced readings. A series is judged only on ten points or more,
over at least three of the slowest time constant the replay met in it; else it says "too little
record". Each **version** of the model (a hash of its structure and the numbers written in it) has
its fit recorded with the span it covered (`<state>/fit/history.jsonl`, at most every five minutes
a version).

**Estimates** (`ergostat/numbers/estimate.py`): every `estimate: true` parameter is given the value
that makes what it touches fit best: each equation using it in the partial-model test, and every
stock its flows move, replayed; weighted least squares, each series' errors over its own spread
(the readings' standard deviation, at least 1% of their mean). Parameters that share an equation or
a stock are fitted together (Nelder–Mead, on their logarithm when they start positive, within a
factor of a thousand of the value written), on the record but its last fifth, which is held out.
Each estimate has a standard error, and those fitted together their correlations, from the Jacobian
of the weighted errors at the optimum (Gauss–Newton, Ljung ch. 9), widened for errors that run
together in time. An estimate is data: kept in `<state>/estimates/<structure>.json`, keyed by the
model's **structure** (a hash of what moves what: stocks, flows, links, equations, parameters' names
and units, not their values), so a value accepted keeps its estimates, and a changed structure
starts afresh.

**Proposals** (`ergostat proposals`, `ergostat accept ID`, `ergostat proposals --dismiss ID`, and an
Accept beside the part on the page): each a concrete change with its reason, the fit before and
after, and the smallest edit to the YAML that makes it, made on the file's text so its comments and
order stay. Two kinds so far. A **parameter** set to its estimate, only when the record supports it:
it is fitted on forty points or more spanning three of the slowest time constant the parameter touches (for a stock that only integrates, the time things stay in it, by Little's law), its errors hold at least ten independent points where the fit leaves a material error (n(1 − ρ)/(1 + ρ), ρ their lag-one autocorrelation), the estimate is not at its
bound (one there is a question of structure), the record tells it apart, it is more than two
standard errors and 2% from the value written, and it fits the record held out better; otherwise it
is kept with why, shown beside the parameter and on the Fit page, and proposes nothing. Its reason
and the numbers first shown are those of the objective it minimised, on the record fitted and the
record held out. An **equation** for a flow that has declared causes and none, a coefficient for
each cause by least squares on what was measured, proposed when it explains half or more of the
variation in the flow's readings (R² as 1 − SSE/SST) and agrees with every declared sign: an
outflow is first-order in its stock, written with the time things stay (`stock.x / time-in-x`), and
is proposed only when it names its stock as a cause; a one-way flow never gets a constant below 0
and never runs backwards (`MAX(0, …)`); a flow and a cause in a loop a controller closes carry the
warning that a regression there is biased (Ljung ch. 13). Nothing is applied by itself. Accepting
applies the edit, refuses it (and puts the file back) if `check` would then find an error, and
records `model.accepted` with the change, the versions before and after, and the fit of each on the
same record; a dismissed proposal is not made again for that structure.

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
