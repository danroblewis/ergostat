# Quickstart

Ten minutes: install, watch an example run, read it from both perspectives, then write a model of
your own and point it at metrics you already have.

## 1. Install

```bash
uv tool install git+ssh://git@github.com/danroblewis/ergostat.git   # private: needs your GitHub SSH key
uv tool upgrade ergostat                                             # later, to update
```

## 2. Watch an example

Work on a copy: examples write their own state into the folder.

```bash
git clone git@github.com:danroblewis/ergostat.git ~/ergostat      # the examples live in the repository
cp -r ~/ergostat/examples/the-job /tmp/job && cd /tmp/job
ergostat run                                                     # prints the page's address
```

`the-job` is a senior engineer's job as a running system: reviews, alerts, flag ramps, secrets,
documents, customer tickets, each watched, prepared for, and decided. It is simulated (no accounts,
nothing is written anywhere) at one working day a minute. Other examples: `image-squeeze` (a
service and an AI lab that improves it), `software-factory`, `first-loop` (the smallest).

To start over: `ergostat run --stop`, `ergostat reset --yes`, `rm -rf run outbox`.

## 3. Read it two ways

The **Diagram** page has three views of the same model:

- **Dynamics**: the system as a System Dynamics stock-and-flow diagram. Boxes are **stocks**
  (what accumulates: reviews waiting, alerts without a comment), pipes with a bowtie **valve** are
  **flows** (what fills and drains them), clouds are outside the model, thin curved arrows are
  causes with their sign (+ or −), and R/B markers are the feedback loops (reinforcing, balancing).
  It answers *what is*.
- **Blocks**: the same system as a control engineer's block diagram: controllers, actuators,
  processes and sensors, summing junctions, signals r, e, u, y. It answers *what we control*.
- **Wiring**: what actually passed between the machines, from the record.

Click anything: the side panel says what it is, charts it over the time window (a stock with its
inflows and outflows; a loop's setpoint, measurement, action and error), and links what it touches.
Closed systems open in place (**Open**) or drawn alone (**Into**). The **⋯** menu opens or closes
everything, hides the loop markers, colours each part to match its counterparts in the other view
(or hold **C**), unpins what you dragged.

**Items** lists what moves through the system (each review, alert, PR) with its states and history.
In the-job, **Items → day** holds each morning's brief and each evening's ledger, rendered.

**Loops** lists every goal, holding or off. **Model** says what the model can do with the record
(test it, improve it, project it, identify and tune its loops) and what each tool still needs.
**Check** says what is missing from the model.
**Guide** is a two-minute illustrated introduction to both disciplines.

## 4. Write your own

In your repository, an `ergostat.yaml`: what accumulates, how it is measured, the goal you hold it
to, and the job that moves it.

```yaml
name: my-service

stocks:
  queue:
    unit: jobs
    sensor:
      run: ./bin/queue-depth            # any command printing a number
      every: 30s

flows:
  arrivals: {to: queue}                 # from outside: the load
  processed: {from: queue}              # what the worker moves

goals:
  queue-short:
    stock: queue
    hold: "<= 100"

blocks:
  worker:
    type: program
    goal: queue-short                   # runs while the goal is off
    run: ./bin/drain-some               # prints how many it moved
    out: flow.processed
```

```bash
ergostat check       # errors with file:line, then what the model is missing
ergostat run         # the loop runs; the page draws it
ergostat explain     # the model in sentences
```

## 5. Point it at metrics you already have

ergostat reads; it does not replace your monitoring. Anything that answers PromQL (Prometheus,
Chronosphere, Grafana Mimir, Google Cloud's managed Prometheus) is a source:

```yaml
sources:
  prom: {type: prometheus, url: https://your-prometheus}

stocks:
  queue:
    unit: jobs
    sensor:
      query: {source: prom, promql: 'sum(queue_depth{service="checkout"})'}
      every: 30s
```

A command can be a source too (`run:`), so anything with a CLI can be read. Control systems that
already run elsewhere (a Kubernetes autoscaler, an alert rule) can be modelled as **observed
controllers**: blocks ergostat reads but does not run (`type: external`); see
[proposals/external-systems.md](proposals/external-systems.md) for where that is going.

## 6. Improve the model

- `ergostat check` names structural problems with their fix (a rate driven by a rate hides a
  delay; a stock nothing drains; units that don't match).
- The **Model** page starts with **What's available**: each loop and what would identify it, each
  parameter to estimate and whether the record is long enough, and a link to the panel of each tool.
  Below it, the changes ergostat proposes (review, simulate, accept) and how well the model fits.
- [MODEL-TOOLS.md](MODEL-TOOLS.md): every tool (fit, checks, calibration, replay, projection, what-if,
  loop dominance, identification, margins, tuning, step tests), where it is and what it needs.
- [MODELLING.md](MODELLING.md) is the guide: the tells, the System Dynamics reason, the YAML fix.
- For an AI agent: `ergostat help improve-model` (also an MCP tool) reviews a model and proposes
  edits, never applying one without you.

## 7. Let it do work

Blocks can be programs, AI agents (`type: ai`, a prompt and the tools it may use) or people
(`type: person`: ergostat asks, never acts). ergostat runs them when their goal is off, records what
each did, and measures whether it helped. See [writing-agents.md](writing-agents.md) and
[ai-agents.md](ai-agents.md).

## Where next

- [WHY.md](WHY.md): why model systems this way, for a team deciding whether to.
- [SPEC.md](SPEC.md): the whole format.
- [MODELLING.md](MODELLING.md): making a model better.
- [MODEL-TOOLS.md](MODEL-TOOLS.md): the model tools, where each shows up and what it needs.
