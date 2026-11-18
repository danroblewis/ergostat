# ergostat

ergostat closes control loops around scheduled work. You write down what accumulates (a queue, a
disk, a backlog), the goal you hold it to, how it is measured, and the job that moves it; ergostat
reads the sensors, decides when the goal is off, runs the job with a command, records what was
commanded and what was moved, and draws the system. It also finds what is missing: goals nothing
serves, stocks heading for a limit, loops that answer more slowly than they did, and feedback that
already exists in production but was never written down.

It shows each system from two perspectives, each drawn the way its discipline draws it: **Dynamics**,
a System Dynamics stock-and-flow diagram (what is), and **Blocks**, a control block diagram (what we
control); plus **Process**, how the work really moved: a process map per kind of item, from the record.

New here: [docs/QUICKSTART.md](docs/QUICKSTART.md) (ten minutes, from install to your own model),
[docs/WHY.md](docs/WHY.md) (why model systems this way, for a team deciding whether to),
[docs/DISCIPLINES.md](docs/DISCIPLINES.md) (every discipline and diagram one file gives you) and
[docs/MODEL-TOOLS.md](docs/MODEL-TOOLS.md) (every tool for testing, improving, projecting and tuning a model,
where each shows up and what it needs; the web page's **Model** page starts with what is available).

The terms are in [NOTES.md](NOTES.md), the design in [docs/DESIGN.md](docs/DESIGN.md), and the rules for
working on it in [CLAUDE.md](CLAUDE.md).

## Start

```bash
uv tool install git+ssh://git@github.com/danroblewis/ergostat   # private: needs your GitHub SSH key
# (update later with: uv tool upgrade ergostat)
cd <your repository>
$EDITOR ergostat.yaml          # the model (below); examples/first-loop is the smallest whole one
ergostat check                 # errors with file:line, then findings (missing feedback, ...)
ergostat run                   # in the background, with the web page
ergostat                       # what needs attention
ergostat explain               # the model in sentences
```

An `ergostat.toml` from before still runs; `ergostat convert` writes it as `ergostat.yaml`, closing
the loops it only watched.

## The model: `ergostat.yaml`

Four kinds of thing, and a fifth when it says something: **stocks** (what accumulates, with the
sensors that measure it), **flows** (what fills and drains them), **goals** (what you want of a stock
or a flow), **blocks** (functions: ergostat's own built-ins, or programs, AI prompts and people it
runs), and **agents** (only for a machine several blocks share). Valves, controllers, disturbances
and loops are worked out from these, never written. The format: [docs/SPEC.md](docs/SPEC.md) and its
[JSON Schema](schema/ergostat.schema.json).

```yaml
name: host

stocks:
  disk:
    unit: "%"
    limit: 100                    # where it fails: ergostat says how long until it gets there
    sensor:
      run: df -P /data | awk 'NR==2 {print $5+0}'
      every: 1m

flows:
  writes:                         # the services' logs: a disturbance (nothing here sets it)
    to: disk
  cleaned:
    from: disk

goals:
  disk-headroom:
    stock: disk
    hold: "<= 80"
    tolerance: 2
    critical: true
    owner: platform

blocks:
  clean:                          # runs while disk-headroom is off, until the disk is back to 70
    type: program
    goal: disk-headroom
    until: "<= 70"
    run: ./clean-oldest.sh        # prints how many % it freed
    out: flow.cleaned
    max: 15                       # the most one run may free: its commands are clamped to it
```

Bigger models split into files (`include: [systems/*.yaml]`); a name defined twice is an error that
names both places.

The common small shapes are **templates**, used with one entry each: the loop above is

```yaml
uses:
  disk:
    use: keep-under
    with: {unit: "%", limit: 80, until: "<= 70", fails-at: 100,
           measure: "df -P /data | awk 'NR==2 {print $5+0}'", act: ./clean-oldest.sh}
```

and `respond-to`, `re-ping`, `daily-report`, `steps` and `collect` are the others; each runs on free stand-ins
until it is given the real thing. [docs/ADDING.md](docs/ADDING.md): "Adding a small control system".

## What a block's program does

A sensor's command prints its reading: a number (`du -sm logs | cut -f1`), or `{"value": n}`. A
block's command gets JSON on stdin (its command, its inputs, its goals' values and errors) and
prints what it moved: a number for its one output, or JSON lines:

```
{"out": "flow.cleaned", "moved": 12}
{"out": "block.writer", "command": 3}                  # a controller commanding another block
{"decision": "12 waiting: process them", "why": "over the goal by 12"}
{"event": "backup.verified", "item": "nightly"}
```

ergostat runs a commanded block once per fresh reading while its command holds, never twice at
once (a command that arrives meanwhile is held, not queued), clamps the command to the block's
`max`, and reads its stocks again right after it moves them. The built-in blocks (`onoff`,
`compare`, `proportional`, `limit`, `delay`, `schedule`, `lookup`, `select`, `expr`, `timer`,
`counter`, `alarm`) are computed by ergostat itself. An `ai` block's prompt goes to `claude -p`
(or `$ERGOSTAT_AI`); a `person` block asks, and the person answers with
`ergostat block NAME --done N`; an `external` block is something ergostat only observes (an
autoscaler, a team), judged by what its flow's sensors show.

## The command line

```
ergostat                     what needs attention (--watch to keep it on screen; --exit-code for cron)
ergostat check               errors (file:line), then findings; --json for agents and CI
ergostat explain [PART]      the model, or one goal, block, stock or flow, in sentences, with what it is doing
ergostat findings            missing feedback, limits ahead (time to failure), saturation, people not
                             answering, a critical goal decaying
ergostat block [NAME]        the blocks: type, role, what each reads and commands (--done N, --approve)
ergostat discover loops      loops in the record: flows that follow their stock, written down or not
ergostat discover prometheus --url URL [--match RE]   a draft model from a Prometheus's series
ergostat convert             ergostat.toml written as ergostat.yaml
ergostat run [--stop]        run it, in the background, with the web page (--foreground, --no-web)
ergostat mcp                 ergostat for an AI agent, over MCP: claude mcp add ergostat -- ergostat -C DIR mcp
ergostat system [NAME]       draw a system (--all, --around loop/NAME, --blocks, --wiring, --list, --open)
ergostat loop [NAME]         the loops, or one part by part
ergostat event [--follow]    the raw record;  ergostat item [NAME]: events folded by id, each a changeset
ergostat item NAME --history every change to each field, with the event that made it (--at: as it stood then)
ergostat sensor STOCK.SENSOR --read V    a person's reading of a manual sensor
ergostat snapshot            the page, as of now, in one HTML file that opens offline
ergostat message "TEXT"      tell the work in flight something (--about ITEM|PART); routed to what it concerns,
                             delivered to a running session as its next turn; ergostat messages: what became of each
ergostat projects            every project on this machine, which are running, and their pages
ergostat run --service       a launchd agent or systemd unit that keeps it running across reboots (printed only)
```

Every topic takes `-s SYSTEM`, `--since 1h`, `--at 30m` (as it was then: `30m` ago, `07:30`) and
`--json`.

## For AI agents

**Setting up ergostat for someone? Start with [docs/AGENT-GUIDE.md](docs/AGENT-GUIDE.md):** how to turn a
described workflow into a model of the right shape (one connected chain per kind of work, a collector,
a block per step), then check it and look at both diagrams before calling it done. Then
[docs/MODELLING-WELL.md](docs/MODELLING-WELL.md) (`ergostat help modelling-well`): the craft beyond correctness, so
that the Dynamics, Blocks and Process views each look as a professional in that discipline would draw them, with
good and poor models side by side.

`ergostat mcp` serves the tools an agent needs to work on a system: `spec` (the format), `check`
(after every edit), `explain`, `status`, `findings`, `events`, and `report_done` and `read_sensor`
for the work and readings a person block or a manual sensor waits for. Every call reads the files
afresh.

To add a small control system from a request in plain words ("remind them until they answer", "keep the cache
under 20 GB", "report every morning"), the MCP tools `templates`, `add_use`, `scaffold`, `try_use` and
`where_drawn`, with the skill [`docs/skills/ergostat-author/SKILL.md`](docs/skills/ergostat-author/SKILL.md),
build it from a template, try it on a scratch copy, and show the owner the diagram and the diff before it is
written: [docs/ADDING.md](docs/ADDING.md), "Adding a small control system".

To review a model, an agent has a skill shipped with ergostat,
[`ergostat/skills/improve-model/SKILL.md`](ergostat/skills/improve-model/SKILL.md) (a Claude Code
skill: copy its folder into `.claude/skills/` to use it there). It runs `check`, reads the findings
and the `residuals`, walks the checklist of [docs/MODELLING.md](docs/MODELLING.md), and proposes
specific YAML edits with their reasons, applying none without the owner's approval. Over MCP the
tool `improve_model` returns it with the guidelines; on the command line, `ergostat help
improve-model` and `ergostat help modelling`.

## More

The model tools (fit, checks, the review queue, calibration, replay, projection, what-if, loop dominance,
identification, margins, tuning, step tests), each with where it shows up and what it needs:
[docs/MODEL-TOOLS.md](docs/MODEL-TOOLS.md).

Telling running work something mid-way (a message routed to the items and sessions it concerns, delivered to a
running Claude Code session as its next turn, followed up on finished work, and measured):
[docs/MESSAGES.md](docs/MESSAGES.md), "Messages and interruptions".

Improving a model, for someone new to system dynamics: [docs/MODELLING.md](docs/MODELLING.md) (the
tells of a wrong structure, what `check`'s structure findings and the Model page are evidence
of, and what to write instead, each with its source in Sterman's *Business Dynamics* or Forrester).

The ideas: [docs/CONCEPTS.md](docs/CONCEPTS.md) (the factory as a control system), why controllers
and valves are separate ([docs/controllers-and-valves.md](docs/controllers-and-valves.md)),
multi-agent patterns ([docs/patterns.md](docs/patterns.md)), and the vocabularies of system dynamics
and control engineering compared ([docs/vocabulary.md](docs/vocabulary.md)).

## The record

What happened (events) and what the sensors read (measurements), in `~/.ergostat/<name>-<hash>/`,
with no services: the events in an append-only log of compressed segments (or SQLite), the readings
in SQLite. Under a long, heavy load it stays bounded: an item's events older than a week are rolled
up into one snapshot event (its state as of then; the originals archived, compressed, behind the
item page's "Show the full history"), readings older than two days are kept as 1-minute, 10-minute and
hourly buckets, and nothing older than `keep:` (30 days) is kept. The engine does this hourly;
`ergostat compact` does it now. VictoriaMetrics can hold the readings instead. The `storage:`
section ([SPEC §4b](docs/SPEC.md)) sets all of it; `scripts/loadtest.py` measures it on the demos run
for days.

## The web page

`ergostat run` serves it at http://127.0.0.1:8781 (the next free port when taken); each page is its own
address (`/items`, `/item/ticket%2F7`, `/diagram?view=blocks`), to open in a new tab, copy or reload. It opens on the
control diagram, laid out by ELK: stocks as tanks, flows as pipes through valves (a bow tie) or
disturbances (a diamond), sensors as gauges, controllers as boxes with their setpoint and status,
each part tagged with the agent that fills it (a lettered dot by its kind, and its schedule). Loops are coloured by status;
systems are drawn as outlines that may overlap; an open loop (a timer) has a clock where a feedback
controller has its Σ; a chain of loops in series folds into rows where one feeds the next. The blocks view draws each loop as a classic
negative-feedback block diagram (r, Σ, e, C, u, the actuator, the disturbance d joining at the
plant, y, the sensor H feeding ym back, and feedforward when a controller measures d itself);
`ergostat system --blocks` prints the same in text.
The Export menu's "SVG" and "PNG" write the diagram as a standalone file, with a header and a legend; "Design SVG" writes only
the structure (parts, flows, roles and schedules, no live values or status), for a design document. `ergostat snapshot` writes the whole page, with
what it shows now, to one HTML file that opens anywhere with no ergostat running (every view, page and part, as of then). The process view draws the process map of each
kind of item from the record (a directly-follows graph: states or events, how often, what came next, rework), and where work on one kind caused work on another. Loops, Agents (by rung), Items, Record, Model and Check show
what the command line shows; the Guide steps through tiny models, drawn by the same renderers, that introduce system dynamics and control, then shows your own model both ways. The header's "Last 1h" menu sets the window and looks at any past moment; "Back to live"
returns.

## Examples

[`examples/`](examples/) holds twelve whole systems, each in its own folder with a README: start with
`first-loop` (an inbox kept short, written by hand), then `plain-crontab` (cron one-liners) and
`talking-scripts` (scripts that print sentences); the rest show loops in series, people filling
roles, AI agents on the ladder, events between agents, systems at scale, and this machine measured
for real. `cd examples/<name> && ergostat run` runs one; `scripts/demos.sh start` runs them all, and
`scripts/demo_check.py` runs a fresh copy of each and checks its pages.

## Develop

```bash
uv sync
uv run python -m pytest -q
uv run ruff check
```

The diagram is tested in a real browser (it drives the Chrome on this machine): every example, in
every view, must draw no line through a part, none on top of another, none far round, and lay out
in time, as must a generated model of about 500 lines. After any change to the diagram:

```bash
uv run --with playwright python -m pytest tests/test_diagram_rendering.py -s
```
