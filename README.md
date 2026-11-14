# ergostat

ergostat keeps work going. You describe the control system around some work (what accumulates,
what moves it, what measures it, what decides and what acts) and ergostat runs the agents that fill
those roles, records what they do, estimates the state, and draws the system.

The terms are in [NOTES.md](NOTES.md), the design in [docs/DESIGN.md](docs/DESIGN.md), and the rules for
working on it in [CLAUDE.md](CLAUDE.md).

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
every = "5m"     # or: cron = "0 3 * * *", or: on = ["loop.off", "backup.requested"]
```

## What an agent's program does

It gets a JSON object on stdin (its roles, the state, its controllers' setpoints and errors, and the
event that triggered it) and prints one JSON object per line, naming the part each line is for:

```
{"sensor": "disk-usage", "value": 71}
{"controller": "disk-under-80", "decision": "under 80: nothing to do"}
{"valve": "delete-old-files", "amount": 3.1}          # what it moved; "position": 4 says how far open it stands
{"event": "backup.requested", "item": "database", "data": {}}
```

A line naming a part the agent does not fill is refused. When a loop crosses its setpoint ergostat
records `loop.off` or `loop.holding`, which other agents can listen for (`on`).

## The command line

```
ergostat                     what needs attention
ergostat system [NAME]       draw a system (--all, --around loop/NAME, --blocks, --wiring, --list, --open)
ergostat loop [NAME]         the loops, or one part by part
ergostat agent [NAME]        who fills which roles, at what rung
ergostat event [--follow]    the raw record;  ergostat item [NAME]: events folded by id
ergostat residual            what the model can't explain
ergostat stock|flow|valve|sensor|controller|disturbance [NAME]
ergostat check | run | web | chat
```

Every topic takes `-s SYSTEM`, `--since 1h`, `--at 30m` (as it was then: `30m` ago, `07:30`) and
`--json`.

## The web page

`ergostat run` serves it at http://127.0.0.1:8781 (the next free port when taken). It opens on the
control diagram, laid out by ELK: stocks as tanks, flows as pipes through valves (a bow tie) or
disturbances (a diamond), sensors as gauges, controllers as boxes with their setpoint and status,
each part tagged with the agent that fills it, coloured by its rung. Loops are coloured by status;
systems are drawn as outlines that may overlap. The blocks view draws each loop as a classic
negative-feedback block diagram (r, Σ, e, C, u, the actuator, the disturbance d joining at the
plant, y, and the sensor H feeding ym back); `ergostat system --blocks` prints the same in text.
"save SVG" writes the diagram as a standalone file. The wiring view draws the agents and how each
one's output reaches another. Loops, Agents (the ladder), Parts, Record, Residuals and Check show
what the command line shows. The slider in the header looks at any past moment; "back to live"
returns.

## Demos

`~/ergostat-demos/` holds six repositories:

- `disk-space`: one program measures, decides and cleans (one agent, three roles).
- `backups`: a sensor program, a rule that listens for `loop.off`, a job that runs on an event, and
  a second loop for the off-site copies.
- `docs-fresh`: an AI agent (simulated), a decision, and a program; a disturbance that is measured.
- `deps`: a person as a controller and valve, falling behind: the loop is off, and the merges they
  make outside the valve show up as a residual.
- `file-queue`: plain shell scripts on real files; an archiver on cron; an agent that fills no role
  and acts as a disturbance.
- `ops`: several systems together, overlapping.

`scripts/demo_check.py` runs each one and checks its pages.

## Develop

```bash
uv sync
uv run python -m pytest -q
uv run ruff check
```
