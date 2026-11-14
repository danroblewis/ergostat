# ergostat

ergostat keeps work going. You describe the control system around some work (what accumulates,
what moves it, what measures it, what decides and what acts) and ergostat runs the agents that fill
those roles, records what they do, estimates the state, and draws the system.

The terms are in [NOTES.md](NOTES.md); the rules for working on it in [CLAUDE.md](CLAUDE.md).

## Start

```bash
uv tool install --force ~/ergostat         # or: uv run ergostat ... from this folder
cd <your repository>
ergostat check --example > ergostat.toml   # or: ergostat chat, and describe it to the Supervisor
ergostat check                             # is the model whole?
ergostat run                               # the agents, in the background, and the web page
ergostat                                   # what needs attention
```

## The model: `ergostat.toml`

```toml
[[stock]]        # what accumulates
name = "disk-used"
unit = "%"
systems = ["host"]

[[disturbance]]  # a flow no valve controls
name = "logs-written"
into = "disk-used"

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

[[valve]]        # where an agent acts: on one flow
name = "delete-old-files"
flow = "cleaned"
agent = "disk-cleaner"

[[agent]]        # fills roles: person, ai, narrow-ai, decision, program or rule
name = "disk-cleaner"
kind = "program"
command = "./clean.sh"
every = "5m"     # or: on = ["loop.off", "backup.requested"]
```

## What an agent's program does

It gets a JSON object on stdin (its roles, the state, its controllers' setpoints and errors, and the
event that triggered it) and prints one JSON object per line, naming the part each line is for:

```
{"sensor": "disk-usage", "value": 71}
{"controller": "disk-under-80", "decision": "under 80: nothing to do"}
{"valve": "delete-old-files", "amount": 3.1}
{"event": "backup.requested", "item": "database", "data": {}}
```

A line naming a part the agent does not fill is refused. When a loop crosses its setpoint ergostat
records `loop.off` or `loop.holding`, which other agents can listen for (`on`).

## The command line

```
ergostat                     what needs attention
ergostat system [NAME]       draw a system (--all, --around loop/NAME, --wiring, --list, --open)
ergostat loop [NAME]         the loops, or one part by part
ergostat agent [NAME]        who fills which roles, at what rung
ergostat event [--follow]    the raw record;  ergostat item [NAME]: events folded by id
ergostat residual            what the model can't explain
ergostat stock|flow|valve|sensor|controller|disturbance [NAME]
ergostat check | run | web | chat
```

Every topic takes `-s SYSTEM`, `--since 1h` and `--json`.

## The web page

`ergostat run` serves it at http://127.0.0.1:8781 (the next free port when taken). It opens on the
control diagram, laid out by ELK: stocks as tanks, flows as pipes through valves (a bow tie) or
disturbances (a diamond), sensors as gauges, controllers as boxes with their setpoint and status,
each part tagged with the agent that fills it, coloured by its rung. Loops are coloured by status;
systems are drawn as outlines that may overlap. The wiring view draws the agents and how each
one's output reaches another. Loops, Agents (the ladder), Record, Residuals and Check show what the
command line shows.

## Demos

`~/ergostat-demos/` holds five repositories: `disk-space`, `backups`, `docs-fresh`, `deps` and
`ops` (all of them together). `scripts/demo_check.py` runs each one and checks its pages.

## Develop

```bash
uv sync
uv run python -m pytest -q
uv run ruff check
```
