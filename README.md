# ergostat

ergostat keeps work going. You describe the control system around some work (what accumulates,
what moves it, what measures it, what decides and what acts) and ergostat runs the agents that fill
those roles, records what they do, estimates the state, and draws the system.

![The control diagram of the ops demo: stocks as tanks, flows as pipes through valves and
disturbances, sensors, controllers with their setpoints, each part tagged with its agent, systems as
outlines](docs/screenshots/control.png)

The same system as classic feedback block diagrams, one loop per row:

![Block diagrams: r, Σ, e, C, u, the actuator, d, the plant, y, and the sensor H feeding ym
back](docs/screenshots/blocks.png)

More: [the design picture, for a document](docs/screenshots/design.png),
[a chain of loops, folded where one feeds the next](docs/screenshots/chain.png),
[the agents and how they reach each other](docs/screenshots/wiring.png),
[the ladder](docs/screenshots/ladder.png), [a loop's detail with its trend](docs/screenshots/loop-detail.png),
[dark, two cron one-liners](docs/screenshots/plain-crontab-dark.png).

The ideas behind it, the parts of a control system and how agents fit in as the factory's machines:
[docs/CONCEPTS.md](docs/CONCEPTS.md); the draft of the next configuration format, in YAML:
[docs/SPEC.md](docs/SPEC.md) with its [JSON Schema](schema/ergostat.schema.json) (and why controllers and valves are separate:
[docs/controllers-and-valves.md](docs/controllers-and-valves.md)).

What was built on 2026-11-14, and what is left to decide: [docs/REPORT-2026-11-14.md](docs/REPORT-2026-11-14.md).

The terms are in [NOTES.md](NOTES.md), the design in [docs/DESIGN.md](docs/DESIGN.md), and the rules for
working on it in [CLAUDE.md](CLAUDE.md).

## Start

```bash
uv tool install git+ssh://git@github.com/danroblewis/ergostat   # private: needs your GitHub SSH key
# (from a clone: uv tool install --force ./ergostat; update later with: uv tool upgrade ergostat)
cd <your repository>
ergostat check --example cron > ergostat.toml   # two one-liners that run as they are
                                           # (--example: one program to write; or ergostat chat, the Supervisor)
ergostat check                             # is the model whole?
ergostat run                               # the agents, in the background, and the web page
ergostat                                   # what needs attention
```

## Try the demos

```bash
scripts/demos.sh start        # every example in examples/, each with its own page
scripts/demos.sh list         # which run, which loops are off, and their pages
scripts/demos.sh stop
```

## The model: `ergostat.toml`

```toml
keep = "30d"     # how long the record is kept (the default)

[[stock]]        # what accumulates
name = "disk-used"
unit = "%"
systems = ["host"]

[[disturbance]]  # a flow no valve controls
name = "logs-written"
into = "disk-used"
# agent = "app"  # optional: the agent whose doing it is (a load), drawn on it; not a role

[[flow]]         # what moves a stock; an end left out is outside the boundary
name = "cleaned"
from = "disk-used"

[[sensor]]       # measures a stock or a flow
name = "disk-usage"
measures = "disk-used"
agent = "disk-cleaner"

[[controller]]   # holds a stock at a setpoint: this is a loop
name = "disk-under-80"
holds = "disk-used"
setpoint = "<= 80"
reads = ["disk-usage"]
drives = ["delete-old-files"]
agent = "disk-cleaner"
# open_loop = true  # a timer: acts on its schedule and reads nothing; leave out reads

[[valve]]        # where an agent acts: on one flow
name = "delete-old-files"
flow = "cleaned"
agent = "disk-cleaner"
mode = "auto"    # or advise, or manual (the default when a person fills it)
# max = 15       # optional: the most one opening can move (its limit: saturation is then exact)

[[agent]]        # fills roles: person, ai, narrow-ai, decision, program or rule
name = "disk-cleaner"
kind = "program"
command = "./clean.sh"
every = "5m"     # or: cron = "0 3 * * *", or: on = ["loop.off", "backup.requested"]
```

Names are unique across all parts (a sensor may not share its stock's name: `disk-usage` measures
`disk-used`). Every amount is in its stock's unit: a valve on a stock in KB says how many KB it
moved, not how many files; a reading of a flow is its rate per hour in that unit. Give a flow or
a sensor its own `unit` and `check` warns when it is not its stock's.

## What an agent's program does

It gets a JSON object on stdin (its roles, the state, its controllers' setpoints and errors, and the
event that triggered it) and prints one JSON object per line, naming the part each line is for:

```
{"sensor": "disk-usage", "value": 71}
{"controller": "disk-under-80", "decision": "under 80: nothing to do"}
{"valve": "delete-old-files", "amount": 3.1}          # what it moved; "position": 4 says how far open it stands
{"event": "backup.requested", "item": "database", "data": {}}
```

A job that fills one sensor or one valve may print just a number instead: `du -k app.log | cut -f1`
is a sensor, `find tmp -mmin +60 -delete -print | wc -l` is a valve; a script that prints a sentence
keeps it, with `parse = "cleaned up (\\d+)"` on its agent. A line naming a part the agent does not fill is refused. A person filling a role records it from the
command line (`ergostat valve NAME --opened N`). How to write one, in shell or Python, and
try it (`ergostat agent NAME --now`): [docs/writing-agents.md](docs/writing-agents.md). An AI agent
filling a controller, with `claude -p`: [docs/ai-agents.md](docs/ai-agents.md). When a loop crosses its setpoint ergostat
records `loop.off` or `loop.holding`, which other agents can listen for (`on`).

## The command line

```
ergostat                     what needs attention (--watch to keep it on screen; --exit-code for cron)
ergostat system [NAME]       draw a system (--all, --around loop/NAME, --blocks, --wiring, --list, --open)
ergostat loop [NAME]         the loops, or one part by part
ergostat agent [NAME]        who fills which roles, at what rung
ergostat event [--follow]    the raw record;  ergostat item [NAME]: events folded by id
ergostat residual            what the model can't explain
ergostat stock|flow|valve|sensor|controller|disturbance [NAME]
ergostat check | run | web | chat
ergostat projects            every project on this machine, which are running, and their pages
ergostat help agents         how to write an agent (also: help ai-agents)
ergostat valve NAME --opened N    a person records what they did (also sensor --read, controller --decided)
ergostat sensor NAME --forget-above V   set wrong readings aside (also --forget-below); the record says so
ergostat snapshot            the page, as of now, in one HTML file that opens offline
ergostat run --service       a launchd agent or systemd unit that keeps it running across reboots (printed only)
```

Every topic takes `-s SYSTEM`, `--since 1h`, `--at 30m` (as it was then: `30m` ago, `07:30`) and
`--json`.

## The web page

`ergostat run` serves it at http://127.0.0.1:8781 (the next free port when taken). It opens on the
control diagram, laid out by ELK: stocks as tanks, flows as pipes through valves (a bow tie) or
disturbances (a diamond), sensors as gauges, controllers as boxes with their setpoint and status,
each part tagged with the agent that fills it (a lettered dot by its kind, and its schedule). Loops are coloured by status;
systems are drawn as outlines that may overlap; an open loop (a timer) has a clock where a feedback
controller has its Σ; a chain of loops in series folds into rows where one feeds the next. The blocks view draws each loop as a classic
negative-feedback block diagram (r, Σ, e, C, u, the actuator, the disturbance d joining at the
plant, y, the sensor H feeding ym back, and feedforward when a controller measures d itself);
`ergostat system --blocks` prints the same in text.
"save SVG" and "PNG" write the diagram as a standalone file, with a header and a legend; "design SVG" writes only
the structure (parts, flows, roles and schedules, no live values or status), for a design document. `ergostat snapshot` writes the whole page, with
what it shows now, to one HTML file that opens anywhere with no ergostat running (every view, page and part, as of then). The wiring view draws the agents and how each
one's output reaches another, and lists the cycles among them, declared as loops or not. Loops, Agents (the ladder), Parts, Record, Residuals and Check show
what the command line shows; the Guide explains the ideas with the system's own parts as examples. The slider in the header looks at any past moment; "back to live"
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
